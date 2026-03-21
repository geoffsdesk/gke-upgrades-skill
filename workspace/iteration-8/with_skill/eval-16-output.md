# Urgent Fix: Admission Webhook Blocking Pod Creation After GKE Upgrade

## Immediate diagnosis

First, identify the problematic webhook:

```bash
# Check all admission webhooks
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Look for cert-manager webhooks specifically
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Examine the webhook configuration
kubectl describe validatingwebhookconfigurations cert-manager-webhook
kubectl describe mutatingwebhookconfigurations cert-manager-webhook
```

Check recent events for webhook failures:
```bash
kubectl get events -A --field-selector reason=FailedCreate,reason=AdmissionWebhookConfigurationFailure --sort-by='.lastTimestamp'
```

## Emergency fix options (choose one)

### Option 1: Temporarily disable the webhook (fastest)
```bash
# Back up the webhook config first
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Delete the problematic webhook temporarily
kubectl delete validatingwebhookconfigurations cert-manager-webhook

# If there's also a mutating webhook:
kubectl get mutatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-mutating-webhook-backup.yaml
kubectl delete mutatingwebhookconfigurations cert-manager-webhook
```

This immediately unblocks pod creation. **Downside:** cert-manager validation is disabled until you restore it.

### Option 2: Add failure policy (safer but may not work if webhook is completely broken)
```bash
# Patch the webhook to ignore failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

## Verify pod creation is unblocked
```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"

# Check pending pods can now schedule
kubectl get pods -A | grep Pending
```

## Root cause: cert-manager compatibility with K8s 1.32

This is likely a **cert-manager version compatibility issue**. Kubernetes 1.32 introduced API changes that break older cert-manager versions.

Check your cert-manager version:
```bash
kubectl get pods -n cert-manager -l app.kubernetes.io/name=cert-manager
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'
```

**Known issue:** cert-manager versions < 1.15.x have compatibility problems with Kubernetes 1.32+ due to:
- Deprecated API versions being removed
- Changes in admission webhook behavior
- TLS certificate validation changes

## Permanent fix: Upgrade cert-manager

Once pod creation is unblocked, upgrade cert-manager to a 1.32-compatible version:

```bash
# Check latest compatible version
# cert-manager 1.15.x+ supports Kubernetes 1.32

# Upgrade cert-manager (example using Helm)
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3 \
  --set installCRDs=true

# Or using kubectl (replace with latest version)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
```

## Restore webhook after cert-manager upgrade

Once cert-manager is upgraded and healthy:

```bash
# Check cert-manager pods are running
kubectl get pods -n cert-manager

# Check webhook service is ready
kubectl get svc -n cert-manager cert-manager-webhook

# If you deleted the webhook configs, restore them:
kubectl apply -f cert-manager-webhook-backup.yaml
kubectl apply -f cert-manager-mutating-webhook-backup.yaml
```

## Validation

Test that everything works:
```bash
# Test certificate creation
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-cert
  namespace: default
spec:
  secretName: test-cert-secret
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  commonName: test.example.com
EOF

# Clean up test
kubectl delete certificate test-cert
```

## Prevention for future upgrades

This could have been prevented by:

1. **Testing in staging first** — always upgrade a staging cluster with the same operators before production
2. **Checking compatibility matrices** — verify all third-party operators support the target Kubernetes version
3. **Using maintenance exclusions** — apply "no minor upgrades" exclusion until you've validated operator compatibility

Add this to your pre-upgrade checklist:
```
- [ ] cert-manager version supports target Kubernetes version
- [ ] All admission webhooks tested against target version in staging
```

## If the upgrade is part of a larger node pool upgrade

If your node pool upgrade is also stuck due to this webhook issue, the fix above will unblock it. Monitor:

```bash
# Check if node pool upgrade resumes
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1

# Monitor node upgrade progress
watch 'kubectl get nodes -o wide'
```

The webhook fix should allow the node pool upgrade to continue automatically.
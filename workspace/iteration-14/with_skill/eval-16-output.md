# Admission Webhook Failure After Control Plane Upgrade

This is a common issue after control plane upgrades. The cert-manager webhook is likely incompatible with Kubernetes 1.32 or has stale certificates.

## Immediate Mitigation (5 minutes)

First, temporarily disable the problematic webhook to restore pod creation:

```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Temporarily set it to ignore failures (don't block pod creation)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Test pod creation works
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass successful"
```

## Permanent Fix (15-20 minutes)

Now upgrade cert-manager to a version compatible with Kubernetes 1.32:

```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Check what versions support K8s 1.32
# Visit: https://cert-manager.io/docs/releases/
# For K8s 1.32, you need cert-manager v1.15.0+

# Upgrade via Helm (most common)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.0 \
  --set crds.enabled=true

# Or if using manifests directly
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.0/cert-manager.yaml

# Wait for rollout
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

## Validation

```bash
# Test certificate creation still works
kubectl create -f - <<EOF
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
  dnsNames:
  - test.example.com
EOF

# Verify webhook is healthy
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook --tail=10

# Test normal pod creation
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Normal pod creation works"
```

## Restore Full Webhook Protection

Once cert-manager is upgraded and working:

```bash
# Re-enable strict webhook validation
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Root Cause Prevention

Add this to your upgrade checklist:
- [ ] Verify all admission webhook operators support target Kubernetes version BEFORE upgrading control plane
- [ ] Test webhook compatibility in staging environment first
- [ ] Document webhook versions and K8s compatibility matrix

## If cert-manager upgrade fails

If you can't upgrade cert-manager immediately, you can temporarily remove the webhook entirely:

```bash
# Nuclear option - remove webhook completely
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# This allows pods to create but disables certificate validation
# Restore after fixing cert-manager
```

The issue is that cert-manager's webhook validates certificate resources and pod configurations, but the webhook itself needs to be compatible with the new Kubernetes API server version (1.32). The temporary `failurePolicy: Ignore` lets pods create while you fix the underlying compatibility issue.
# Cert-Manager Webhook Failure - Urgent Fix

This is a common post-upgrade issue where cert-manager's admission webhook fails to update certificates for the new Kubernetes API version, blocking all pod creation.

## Immediate Mitigation (5 minutes)

**Step 1 - Temporarily disable webhook validation:**
```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch to ignore failures (allows pods to create)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Step 2 - Verify pod creation works:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

Your workloads should now be able to create pods again.

## Permanent Fix (15-30 minutes)

**Step 1 - Check cert-manager version compatibility:**
```bash
# Check current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it supports Kubernetes 1.32
helm repo update jetstack
helm search repo jetstack/cert-manager --versions | head -5
```

**Step 2 - Upgrade cert-manager to compatible version:**
```bash
# Backup current config
kubectl get -o yaml \
  --all-namespaces \
  issuer,clusterissuer,certificates > cert-manager-backup.yaml

# Upgrade cert-manager (adjust version as needed)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.0 \
  --set installCRDs=true
```

**Step 3 - Wait for webhook to be healthy:**
```bash
# Monitor cert-manager pods
kubectl get pods -n cert-manager -w

# Check webhook endpoint
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep caBundle
```

**Step 4 - Restore webhook validation:**
```bash
# Re-enable strict validation
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

**Step 5 - Final validation:**
```bash
# Test certificate creation
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind Certificate
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

kubectl describe certificate test-cert
kubectl delete certificate test-cert
```

## Prevention for Next Time

**Before future control plane upgrades:**

1. **Check compatibility matrix** - Verify cert-manager version supports target Kubernetes version
2. **Upgrade operators first** - Update cert-manager BEFORE upgrading control plane
3. **Test in staging** - Always validate the upgrade path in a non-production environment

**Add this to your pre-upgrade checklist:**
```
- [ ] cert-manager version compatible with target K8s version
- [ ] All admission webhook operators tested against target version
- [ ] Webhook failurePolicy=Ignore staged as emergency mitigation
```

## Root Cause

Cert-manager's admission webhook uses certificates that are signed for specific Kubernetes API server identities. When the control plane upgrades, the API server identity changes, but cert-manager's webhook certificates don't automatically update, causing validation failures.

The temporary `failurePolicy=Ignore` lets pods create while you upgrade cert-manager to a version that properly handles the new API server certificates.

Your immediate issue should be resolved within 5 minutes with the temporary fix, then permanently resolved within 30 minutes.
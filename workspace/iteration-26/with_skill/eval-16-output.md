This is a common post-upgrade issue where admission webhooks fail after control plane upgrades. Here's the urgent fix:

## Immediate Mitigation (Temporary - 5 minutes)

**Option 1: Set webhook to ignore failures temporarily**
```bash
# Find the problematic webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch it to ignore failures (allows pod creation to proceed)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Option 2: If multiple webhooks are affected**
```bash
# List all cert-manager webhooks
kubectl get validatingwebhookconfigurations -o name | grep cert-manager
kubectl get mutatingwebhookconfigurations -o name | grep cert-manager

# Patch each one
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test immediately:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "webhook test"
```

## Root Cause & Permanent Fix

**Check cert-manager version compatibility:**
```bash
kubectl get pods -n cert-manager -o wide
kubectl get deployment -n cert-manager cert-manager-webhook -o yaml | grep image:
```

Cert-manager versions have specific Kubernetes compatibility:
- Kubernetes 1.32 requires cert-manager v1.13+ 
- Check [cert-manager compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/)

**Upgrade cert-manager to compatible version:**
```bash
# If using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.0 \
  --set installCRDs=true

# Wait for rollout
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

**Verify and restore webhook policy:**
```bash
# Test pod creation still works
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "test after upgrade"

# Restore strict failure policy
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# Final test
kubectl run test-pod-3 --image=nginx --rm -it --restart=Never -- echo "final test"
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```bash
# Before upgrading control plane, check operator compatibility
kubectl get pods -A -o wide | grep -E "(cert-manager|istio|gatekeeper)"

# Verify webhook configurations
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Test webhook operators support target Kubernetes version
# Check operator docs/release notes before upgrading
```

## If cert-manager upgrade fails

**Emergency bypass (use sparingly):**
```bash
# Temporarily delete the webhook entirely
kubectl delete validatingwebhookconfigurations cert-manager-webhook

# This allows pods to create without cert-manager validation
# You'll lose certificate management until it's restored
```

The `failurePolicy: Ignore` approach is safer as it keeps cert-manager running while allowing pod creation to proceed. The permanent fix is upgrading cert-manager to a version that supports Kubernetes 1.32.

**Time estimate:** 
- Immediate mitigation: 2-3 minutes
- Permanent fix: 10-15 minutes  
- Total recovery: Under 20 minutes

This pattern applies to other operators too (Istio, Gatekeeper, etc.) - the webhook becomes incompatible with the new API server version and needs upgrading.
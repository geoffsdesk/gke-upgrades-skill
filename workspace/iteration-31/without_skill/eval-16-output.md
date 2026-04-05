This is a common issue when upgrading Kubernetes versions - admission webhooks can break due to API version changes or compatibility issues. Here's how to resolve this urgently:

## Immediate Emergency Fix

**Option 1: Temporarily disable the webhook**
```bash
# Find the ValidatingAdmissionWebhook
kubectl get validatingadmissionwebhooks | grep cert-manager

# Delete or disable it temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook
```

**Option 2: Patch the webhook to fail open**
```bash
# Make the webhook fail open (allow requests if webhook is unavailable)
kubectl patch validatingadmissionwebhook cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'
```

## Diagnostic Steps

**Check webhook status:**
```bash
# Check if cert-manager pods are running
kubectl get pods -n cert-manager

# Check webhook configuration
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml

# Check webhook endpoint
kubectl get svc -n cert-manager
```

**Check webhook logs:**
```bash
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

## Permanent Fix

**1. Upgrade cert-manager to compatible version:**
```bash
# Check current version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to K8s 1.32 compatible version
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1  # or latest compatible version
```

**2. If upgrade isn't immediately possible, fix webhook configuration:**
```bash
# Check if webhook certificate is valid
kubectl get secret cert-manager-webhook-ca -n cert-manager -o yaml

# Restart cert-manager to regenerate certificates
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
```

## Quick Validation

**Test pod creation:**
```bash
# Try creating a test pod
kubectl run test-pod --image=nginx --dry-run=server
```

**Re-enable webhook (if disabled):**
```bash
# Once cert-manager is fixed, re-enable webhook if you disabled it
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --reuse-values
```

## Prevention for Future Upgrades

1. **Check compatibility matrix** before upgrading
2. **Test in staging** environment first
3. **Have webhook bypass procedures** documented
4. **Monitor webhook health** after upgrades

The most likely cause is that cert-manager needs to be updated to a version compatible with K8s 1.32. The temporary webhook disabling will get your workloads running immediately while you perform the proper upgrade.
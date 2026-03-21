This is a common issue when upgrading Kubernetes - the cert-manager webhook may be incompatible with K8s 1.32 or its certificates may have expired. Here's how to fix it urgently:

## Immediate Fix (Temporary)

**Option 1: Bypass the webhook temporarily**
```bash
# Delete the validating admission webhook
kubectl delete validatingadmissionwebhook cert-manager-webhook

# Delete the mutating admission webhook  
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

This will allow pods to be created immediately while you fix the root cause.

## Root Cause Fixes

**Option 2: Upgrade cert-manager**
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager

# Upgrade to a version compatible with K8s 1.32
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1 \  # or latest compatible version
  --set crds.enabled=true
```

**Option 3: Restart cert-manager components**
```bash
# Sometimes a simple restart fixes webhook registration issues
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for rollout to complete
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

**Option 4: Check webhook certificates**
```bash
# Check if webhook certificates are expired
kubectl get secret cert-manager-webhook-ca -n cert-manager -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates

# If expired, delete the secret to force regeneration
kubectl delete secret cert-manager-webhook-ca -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
```

## Verify the Fix

```bash
# Check webhook status
kubectl get validatingadmissionwebhooks cert-manager-webhook
kubectl get mutatingadmissionwebhooks cert-manager-webhook

# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server
```

## Prevention for Next Time

1. **Check compatibility matrix** before upgrading
2. **Upgrade operators first** in a staging environment
3. **Set up monitoring** for admission webhook failures

**Recommendation**: Use Option 1 for immediate relief, then implement Option 2 (upgrade cert-manager) for the permanent fix. The webhook bypass is safe short-term but removes cert-manager's validation capabilities.
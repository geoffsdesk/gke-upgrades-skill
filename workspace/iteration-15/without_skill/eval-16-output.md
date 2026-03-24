This is a common issue after Kubernetes upgrades due to API version deprecations or webhook compatibility problems. Here's how to resolve it urgently:

## Immediate Fixes (Choose Based on Your Situation)

### 1. Check Webhook Status First
```bash
# Check if cert-manager is running
kubectl get pods -n cert-manager

# Check webhook configuration
kubectl get validatingadmissionwebhooks | grep cert-manager
kubectl get mutatingadmissionwebhooks | grep cert-manager
```

### 2. Quick Fix: Temporarily Disable the Webhook
```bash
# Delete the problematic webhook temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook

# This will allow pods to be created immediately
```

### 3. Upgrade cert-manager (Recommended Long-term Fix)
```bash
# Check current version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest version (adjust version as needed)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# Or using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager -n cert-manager
```

### 4. Fix Webhook Configuration Issues
```bash
# Check webhook endpoints
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml

# If service endpoint is wrong, patch it:
kubectl patch validatingadmissionwebhook cert-manager-webhook \
  --type='json' -p='[{"op": "replace", "path": "/webhooks/0/clientConfig/service/name", "value": "cert-manager-webhook"}]'
```

### 5. Restart cert-manager Components
```bash
# Restart all cert-manager pods
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for rollout
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

## Root Cause Investigation

### Check API Version Compatibility
```bash
# Check what API versions the webhook is trying to use
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml | grep -A 10 admissionReviewVersions

# Should include "v1" for k8s 1.32
```

### Check Webhook Logs
```bash
kubectl logs -n cert-manager deployment/cert-manager-webhook --tail=100
```

## Prevention for Future Upgrades

### 1. Version Compatibility Matrix
Before upgrading Kubernetes, check:
- [cert-manager Kubernetes compatibility](https://cert-manager.io/docs/installation/supported-releases/)
- Ensure cert-manager version supports k8s 1.32

### 2. Test in Staging
```bash
# Always test webhook compatibility in staging first
kubectl auth can-i create pods --as=system:serviceaccount:default:default
```

## Emergency Rollback (If Nothing Else Works)

If you need immediate relief and can't fix cert-manager:

```bash
# Scale down cert-manager temporarily
kubectl scale deployment cert-manager-webhook -n cert-manager --replicas=0

# Remove webhook configurations
kubectl delete validatingadmissionwebhook cert-manager-webhook --ignore-not-found
kubectl delete mutatingadmissionwebhook cert-manager-webhook --ignore-not-found
```

## Quick Verification

After applying fixes:
```bash
# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server
kubectl delete pod test-pod --ignore-not-found

# Check webhook is responding
kubectl get validatingadmissionwebhooks cert-manager-webhook -o jsonpath='{.webhooks[0].clientConfig.service}'
```

## Most Likely Solution

For k8s 1.31→1.32 upgrade, the issue is probably:
1. **cert-manager version incompatibility** - upgrade cert-manager to v1.13+ 
2. **admissionReviewVersions** - older versions don't support v1 admission review

**Immediate action**: Upgrade cert-manager to the latest version that supports k8s 1.32, which should resolve the webhook compatibility issues.
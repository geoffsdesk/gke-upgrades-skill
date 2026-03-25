This is a common issue when upgrading Kubernetes versions - webhook compatibility problems. Here's how to resolve this urgently:

## Immediate Fix Options (Choose One)

### Option 1: Bypass the Webhook Temporarily
```bash
# Find the failing webhook
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Delete the problematic webhook temporarily
kubectl delete validatingadmissionwebhook <webhook-name>
# or
kubectl delete mutatingadmissionwebhook <webhook-name>
```

### Option 2: Disable Webhook for Specific Namespaces
```bash
# Edit the webhook to exclude critical namespaces
kubectl edit validatingadmissionwebhook <webhook-name>

# Add namespaceSelector to exclude specific namespaces:
spec:
  namespaceSelector:
    matchExpressions:
    - key: name
      operator: NotIn
      values: ["kube-system", "your-critical-namespace"]
```

## Root Cause Fix

### 1. Upgrade cert-manager
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o wide

# Upgrade to latest compatible version
helm repo add jetstack https://charts.jetstack.io
helm repo update

# Upgrade cert-manager (adjust version as needed)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.x \
  --set installCRDs=true
```

### 2. Check Webhook Configuration
```bash
# Check if webhook is responding
kubectl get validatingadmissionwebhooks -o yaml | grep -A5 -B5 cert-manager

# Test webhook endpoint directly
kubectl get endpoints -n cert-manager
```

### 3. Restart cert-manager Components
```bash
# Restart cert-manager pods
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=300s
```

## Verification Steps

### 1. Check Webhook Status
```bash
# Verify webhook is working
kubectl get validatingadmissionwebhooks cert-manager-webhook -o jsonpath='{.webhooks[0].clientConfig.service}'

# Check webhook pod logs
kubectl logs -n cert-manager -l app.kubernetes.io/component=webhook
```

### 2. Test Pod Creation
```bash
# Try creating a test pod
kubectl run test-pod --image=nginx --dry-run=server
```

## Prevention for Future Upgrades

### 1. Check Compatibility Matrix
```bash
# Before upgrading, check cert-manager compatibility
# Refer to: https://cert-manager.io/docs/installation/supported-releases/
```

### 2. Set Failure Policy
```bash
# Edit webhook to fail open during issues
kubectl patch validatingadmissionwebhook cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'
```

## Emergency Rollback (If Nothing Else Works)

### Temporarily Disable All Admission Webhooks
```bash
# This is DANGEROUS - only use in extreme emergencies
# Edit kube-apiserver manifest
sudo vim /etc/kubernetes/manifests/kube-apiserver.yaml

# Add to command args:
- --disable-admission-plugins=ValidatingAdmissionWebhook,MutatingAdmissionWebhook
```

## Quick Diagnosis Commands
```bash
# Check what's failing
kubectl describe validatingadmissionwebhook cert-manager-webhook
kubectl get events --sort-by='.lastTimestamp' | grep -i admission
kubectl logs -n cert-manager -l app=webhook --tail=50
```

**Start with Option 1 or 2 for immediate relief, then work on the root cause fix. The cert-manager upgrade is most likely needed for Kubernetes 1.32 compatibility.**

Would you like me to help you with any specific error messages you're seeing?
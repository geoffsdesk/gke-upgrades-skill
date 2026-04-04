This is a common issue after Kubernetes upgrades where admission webhooks become incompatible or fail. Here's how to fix it urgently:

## Immediate Troubleshooting Steps

### 1. Check Webhook Status
```bash
# List all admission webhooks
kubectl get validatingadmissionwebhooks,mutatingadmissionwebhooks

# Check cert-manager webhook specifically
kubectl get validatingadmissionwebhooks cert-manager-webhook
kubectl describe validatingadmissionwebhooks cert-manager-webhook
```

### 2. Check cert-manager Pod Status
```bash
# Check if cert-manager pods are running
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

## Quick Fixes (in order of preference)

### Option 1: Upgrade cert-manager (Recommended)
```bash
# Check current version
kubectl get deployment -n cert-manager cert-manager -o yaml | grep image:

# Upgrade to compatible version (check cert-manager compatibility matrix)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

### Option 2: Temporarily Disable Webhook (EMERGENCY ONLY)
⚠️ **Only use this as a last resort for emergency pod creation**

```bash
# Backup the webhook first
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Temporarily disable by removing the webhook
kubectl delete validatingadmissionwebhooks cert-manager-webhook

# Re-enable after fixing cert-manager
kubectl apply -f cert-manager-webhook-backup.yaml
```

### Option 3: Update Webhook Configuration
If the webhook exists but has wrong endpoints:

```bash
# Check webhook configuration
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml

# Update webhook to use correct service
kubectl patch validatingadmissionwebhooks cert-manager-webhook --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/clientConfig/service/namespace", "value": "cert-manager"}]'
```

### Option 4: Restart cert-manager Components
```bash
# Restart cert-manager pods
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for rollout
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

## Verification Steps

### Test Pod Creation
```bash
# Try creating a test pod
kubectl run test-pod --image=nginx --dry-run=server
```

### Check Webhook Logs
```bash
# Monitor webhook logs during pod creation
kubectl logs -n cert-manager deployment/cert-manager-webhook -f
```

## Prevention for Future Upgrades

### 1. Check Compatibility Matrix
Before upgrading, verify cert-manager compatibility:
- Kubernetes 1.32 requires cert-manager v1.13+ 

### 2. Upgrade Operators First
```bash
# Always upgrade operators before or immediately after K8s upgrade
helm repo update
helm upgrade cert-manager jetstack/cert-manager -n cert-manager
```

### 3. Test in Staging
Always test the upgrade path in a non-production environment first.

## Additional Debugging

If the above doesn't work, check:

```bash
# Check API server logs for webhook errors
kubectl logs -n kube-system kube-apiserver-<node-name>

# Check webhook certificate validity
kubectl get secret -n cert-manager cert-manager-webhook-ca -o yaml
```

**Most likely solution**: Upgrade cert-manager to a version compatible with Kubernetes 1.32. The temporary webhook disable should only be used if you need immediate pod creation capability while preparing the proper fix.
This is a common issue after Kubernetes upgrades due to API version changes or webhook compatibility problems. Here's how to fix it urgently:

## Immediate Fix (Choose One)

### Option 1: Temporarily Disable the Webhook
```bash
# Find the validating admission webhook
kubectl get validatingadmissionwebhooks | grep cert-manager

# Delete or patch to disable temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook
# OR
kubectl get mutatingadmissionwebhooks | grep cert-manager
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

### Option 2: Add Failure Policy (Less Disruptive)
```bash
# Patch the webhook to ignore failures
kubectl patch validatingadmissionwebhook cert-manager-webhook -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Do the same for mutating webhook if exists
kubectl patch mutatingadmissionwebhook cert-manager-webhook -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

## Root Cause Fix

### 1. Upgrade cert-manager
```bash
# Check current version
kubectl get pods -n cert-manager -o yaml | grep image:

# Upgrade to version compatible with K8s 1.32
# Check cert-manager compatibility matrix first
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1  # Use latest compatible version
```

### 2. Check Webhook Service Health
```bash
# Verify cert-manager pods are running
kubectl get pods -n cert-manager

# Check webhook service
kubectl get svc -n cert-manager cert-manager-webhook

# Check webhook endpoints
kubectl get endpoints -n cert-manager cert-manager-webhook

# Test webhook connectivity
kubectl get --raw /api/v1/namespaces/cert-manager/services/cert-manager-webhook:https:webhook/proxy/
```

### 3. Verify API Versions
```bash
# Check if cert-manager is using deprecated APIs
kubectl get apiservices | grep cert-manager

# Check certificate CRDs
kubectl get crd | grep cert-manager
```

## Troubleshooting Commands

```bash
# Check admission controller logs
kubectl logs -n kube-system -l component=kube-apiserver | grep admission

# Check cert-manager webhook logs
kubectl logs -n cert-manager -l app=webhook

# Test webhook directly
kubectl auth can-i create certificates.cert-manager.io

# Check webhook configuration
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml
```

## Prevention Steps

1. **Test in staging first** - Always upgrade control plane in non-prod
2. **Check compatibility matrix** - Verify operator versions support new K8s version
3. **Monitor admission webhooks** - Set up alerts for webhook failures
4. **Use failure policies** - Configure `failurePolicy: Ignore` for non-critical webhooks during upgrades

## If Still Failing

If the above doesn't work immediately:

```bash
# Nuclear option - remove all cert-manager webhooks temporarily
kubectl delete validatingadmissionwebhook --all -l app.kubernetes.io/name=cert-manager
kubectl delete mutatingadmissionwebhook --all -l app.kubernetes.io/name=cert-manager

# Then reinstall cert-manager completely
kubectl delete namespace cert-manager
# Reinstall with latest version
```

**Critical**: After the immediate fix, ensure you properly upgrade cert-manager to a K8s 1.32 compatible version to restore full functionality.

Would you like me to help you check the specific error messages or cert-manager version compatibility?
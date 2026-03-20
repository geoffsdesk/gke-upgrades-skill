This is a common issue when upgrading Kubernetes versions due to API changes and webhook compatibility. Here's an urgent troubleshooting guide:

## Immediate Actions

### 1. Check Webhook Status
```bash
# Check if cert-manager pods are running
kubectl get pods -n cert-manager

# Check webhook configuration
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Look for cert-manager webhooks specifically
kubectl get validatingwebhookconfigurations -o yaml | grep -A 10 -B 5 cert-manager
```

### 2. Check Cert-Manager Version Compatibility
```bash
# Check current cert-manager version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'
```

Kubernetes 1.30 requires cert-manager v1.13.0 or later. If you're running an older version, this is likely your issue.

## Quick Fixes (in order of preference)

### Option 1: Upgrade Cert-Manager (Recommended)
```bash
# Upgrade to latest compatible version
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# Or using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager --namespace cert-manager --version v1.13.3
```

### Option 2: Temporary Webhook Bypass (URGENT ONLY)
⚠️ **Only use this as a last resort for immediate pod creation**

```bash
# Temporarily disable cert-manager webhooks
kubectl patch validatingwebhookconfigurations cert-manager-webhook --type='merge' -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there are mutating webhooks
kubectl get mutatingwebhookconfigurations | grep cert-manager
kubectl patch mutatingwebhookconfigurations cert-manager-webhook --type='merge' -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

### Option 3: Restart Cert-Manager Components
```bash
# Restart cert-manager pods
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for rollout
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

## Verify the Fix

```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "success"

# Check webhook logs for errors
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Verify webhook endpoints are reachable
kubectl get endpoints -n cert-manager
```

## Root Cause Analysis

Check for these common issues:

```bash
# 1. API version compatibility
kubectl api-versions | grep admissionregistration

# 2. Certificate issues
kubectl describe validatingwebhookconfigurations cert-manager-webhook

# 3. Network policies blocking webhook
kubectl get networkpolicies -A

# 4. DNS resolution issues
kubectl run debug --image=busybox -it --rm --restart=Never -- nslookup cert-manager-webhook.cert-manager.svc.cluster.local
```

## If Nothing Works - Emergency Cleanup

```bash
# Remove webhook configurations entirely (allows pod creation)
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# Reinstall cert-manager completely
kubectl delete namespace cert-manager
# Wait for namespace deletion, then reinstall with compatible version
```

## Post-Fix Actions

1. **Re-enable webhooks** if you disabled them temporarily
2. **Test certificate operations** to ensure cert-manager is fully functional
3. **Update your upgrade procedures** to check operator compatibility before K8s upgrades

The most likely fix is upgrading cert-manager to a 1.30-compatible version. Let me know what you find with the version check and I can provide more specific guidance!
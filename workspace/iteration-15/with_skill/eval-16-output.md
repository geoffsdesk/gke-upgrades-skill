# Urgent Fix: Admission Webhook Blocking Pod Creation After GKE Upgrade

## Immediate Mitigation (5 minutes)

First, temporarily disable the failing webhook to restore pod creation:

```bash
# List all validating webhooks to find cert-manager ones
kubectl get validatingwebhookconfigurations

# Temporarily set cert-manager webhooks to ignore failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there are multiple cert-manager webhooks, patch each one
kubectl get validatingwebhookconfigurations -o name | grep cert-manager | \
  xargs -I {} kubectl patch {} -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Test pod creation immediately
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Root Cause & Permanent Fix

**What happened:** cert-manager's admission webhook wasn't updated to support Kubernetes 1.32 APIs, causing it to reject pod creation requests from the upgraded control plane.

### 1. Check cert-manager version compatibility
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -l app=cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Check webhook configuration
kubectl describe validatingwebhookconfigurations cert-manager-webhook
```

### 2. Upgrade cert-manager to 1.32-compatible version
```bash
# If using Helm (most common):
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3 \
  --set installCRDs=true

# Wait for cert-manager pods to be ready
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=300s

# Verify webhook is healthy
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep caBundle
```

### 3. Test and restore webhook enforcement
```bash
# Test pod creation with updated cert-manager
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Testing with updated cert-manager"

# If successful, restore webhook failure policy to "Fail"
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# Final test
kubectl run test-pod-3 --image=nginx --rm -it --restart=Never -- echo "Webhook enforcement restored"
```

## Verification Checklist
- [ ] Pods can be created successfully
- [ ] cert-manager pods are all Running
- [ ] Webhook configuration shows valid caBundle
- [ ] Certificate issuance still working
- [ ] No webhook rejection errors in events

## Prevention for Next Upgrade

Before your next GKE upgrade:
1. **Check operator compatibility** - Verify cert-manager and other operators support the target Kubernetes version
2. **Test in staging** - Run the same cert-manager version in a staging cluster upgraded to the target version
3. **Update operators first** - Upgrade operators to compatible versions before upgrading GKE

## If cert-manager upgrade fails

If the Helm upgrade fails, you may need to manually update the webhook configuration:

```bash
# Generate new webhook certificates
kubectl delete secret cert-manager-webhook-ca -n cert-manager
kubectl rollout restart deployment cert-manager-webhook -n cert-manager

# Or temporarily remove the webhook entirely (last resort)
kubectl delete validatingwebhookconfigurations cert-manager-webhook
# Then reinstall cert-manager from scratch
```

Your pod creation should be working within 5 minutes of applying the immediate mitigation. The permanent fix ensures this won't happen again and maintains cert-manager functionality.
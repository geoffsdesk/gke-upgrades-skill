# Urgent: Admission Webhook Blocking Pod Creation After GKE 1.32 Upgrade

This is a common post-upgrade issue where cert-manager's webhook isn't compatible with the new Kubernetes API server version. Here's the immediate fix:

## Emergency Resolution

### 1. Identify the problematic webhook
```bash
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check which webhook is failing
kubectl get events -A --field-selector reason=FailedCreate | grep webhook
```

### 2. Temporarily disable the webhook to restore pod creation
```bash
# Get current webhook config for backup
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Add failure policy to allow pod creation when webhook fails
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Alternative emergency approach** - temporarily delete the webhook entirely:
```bash
kubectl delete validatingwebhookconfigurations cert-manager-webhook
# Pods should now create successfully
```

### 3. Verify pod creation is working
```bash
kubectl get pods -A | grep Pending
# Should see fewer/no pending pods

# Test creating a simple pod
kubectl run test-pod --image=nginx --rm -it -- echo "Pod creation working"
```

## Root Cause Fix

The webhook is likely running an older cert-manager version incompatible with GKE 1.32's API server changes.

### 1. Check cert-manager version
```bash
kubectl get pods -n cert-manager -o wide
kubectl get deployment -n cert-manager cert-manager-webhook -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### 2. Upgrade cert-manager to a 1.32-compatible version
```bash
# Check current version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest stable (1.13.x+ recommended for GKE 1.32)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# Wait for rollout
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

### 3. Restore original webhook configuration
```bash
# Only if you temporarily disabled it - restore the original failurePolicy
kubectl apply -f cert-manager-webhook-backup.yaml

# Or if you deleted it, the cert-manager upgrade should have recreated it
kubectl get validatingwebhookconfigurations cert-manager-webhook
```

## Validation

```bash
# Confirm webhook is healthy
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Test certificate creation still works
kubectl get certificates -A
kubectl get certificaterequests -A

# Verify no more admission failures
kubectl get events -A --field-selector reason=FailedCreate | grep webhook
# Should show no recent webhook failures
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```markdown
- [ ] cert-manager version compatibility verified with target GKE version
- [ ] All admission webhooks tested against target Kubernetes API version
- [ ] Webhook failurePolicy set to "Ignore" for non-critical webhooks during upgrade windows
```

**Key insight:** Admission webhooks can completely block cluster operations post-upgrade. Always verify third-party operator compatibility BEFORE upgrading the control plane, and have webhook bypass procedures ready for emergencies.

The temporary `failurePolicy: Ignore` gives you breathing room to upgrade the operator properly without blocking all pod creation in your cluster.
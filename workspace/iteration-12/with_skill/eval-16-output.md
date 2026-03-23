# Urgent Fix: Admission Webhook Blocking Pod Creation After GKE Upgrade

## Immediate Diagnosis

Check the webhook configuration and recent failures:

```bash
# Check validating webhooks (most common culprit)
kubectl get validatingwebhookconfigurations
kubectl describe validatingwebhookconfigurations cert-manager-webhook

# Check mutating webhooks too
kubectl get mutatingwebhookconfigurations
kubectl describe mutatingwebhookconfigurations cert-manager-webhook

# Look for recent admission failures
kubectl get events -A --field-selector reason=FailedCreate,reason=AdmissionWebhookConfigurationFailure --sort-by='.lastTimestamp'
```

## Root Cause (likely)

Cert-manager's admission webhook is probably incompatible with Kubernetes 1.32 API changes or the webhook service itself is unhealthy after the control plane upgrade.

## Immediate Fix Options (in order of preference)

### Option 1: Temporarily disable the webhook (fastest recovery)

```bash
# Backup the webhook config first
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Add failure policy to ignore webhook failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Or completely remove it temporarily (more aggressive)
kubectl delete validatingwebhookconfigurations cert-manager-webhook
```

### Option 2: Check if cert-manager pods are healthy

```bash
# Check cert-manager components
kubectl get pods -n cert-manager
kubectl logs -n cert-manager -l app=webhook --tail=50

# If webhook pod is crashlooping, restart it
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
```

### Option 3: Update cert-manager to 1.32-compatible version

```bash
# Check current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o yaml | grep image:

# Upgrade to latest (check cert-manager docs for 1.32 compatibility)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

## Validation

```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation works"

# Check webhook is responding (if you kept it enabled)
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep failurePolicy

# Monitor for new admission errors
kubectl get events -A --field-selector reason=FailedCreate --watch
```

## Recovery Steps

1. **Immediate relief:** Patch the webhook with `failurePolicy: Ignore` or delete it temporarily
2. **Fix the root cause:** Upgrade cert-manager to a version compatible with K8s 1.32
3. **Restore protection:** Re-enable the webhook once cert-manager is healthy

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```
- [ ] Third-party operators (cert-manager, Istio, etc.) tested against target K8s version
- [ ] Admission webhooks have failurePolicy: Ignore for non-critical validation
- [ ] Webhook health monitoring in place
```

**Time estimate:** Option 1 should restore pod creation within 2-3 minutes. Full cert-manager upgrade may take 10-15 minutes.

The key insight: admission webhooks are a common failure point during K8s upgrades because they intercept ALL pod creation. When in doubt, disable them first to restore service, then fix the underlying issue.
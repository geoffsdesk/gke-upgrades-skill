# Urgent Fix: Cert-Manager Admission Webhook Blocking Pod Creation

Your cert-manager admission webhook is likely incompatible with GKE 1.30. This is a common issue during minor version upgrades when third-party operators haven't been updated to handle new Kubernetes API versions.

## Immediate Fix (Choose One)

### Option A: Temporarily disable the webhook (fastest)
```bash
# List cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily delete the problematic webhook
kubectl delete validatingwebhookconfigurations cert-manager-webhook
# If there's also a mutating webhook:
kubectl delete mutatingwebhookconfigurations cert-manager-webhook
```

This immediately unblocks pod creation. You'll lose certificate validation temporarily but existing certs continue working.

### Option B: Add failure policy (safer)
```bash
# Patch webhook to ignore failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

This allows pods to be created even when the webhook fails, maintaining some protection.

## Validate the fix
```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation works"

# Check for pending pods
kubectl get pods -A | grep Pending

# Monitor events for webhook errors
kubectl get events -A --field-selector reason=FailedCreate
```

## Root Cause Analysis
```bash
# Check cert-manager version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Check webhook configuration
kubectl describe validatingwebhookconfigurations cert-manager-webhook

# Look for API version issues in logs
kubectl logs -n cert-manager deployment/cert-manager-webhook --tail=50
```

## Permanent Fix

1. **Upgrade cert-manager** to a version compatible with Kubernetes 1.30:
```bash
# Check current version
helm list -n cert-manager

# Upgrade to latest (assuming Helm deployment)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.4  # Or latest stable
```

2. **If webhook was manually deleted, reinstall it** after cert-manager upgrade:
```bash
# The webhook should be recreated automatically by the cert-manager upgrade
kubectl get validatingwebhookconfigurations cert-manager-webhook
```

## Prevention for Next Time

Before upgrading control plane:
- Check operator compatibility matrices
- Test in staging with the target GKE version
- Have rollback procedures for third-party operators

## If cert-manager upgrade fails

Worst case scenario - you can temporarily manage certificates manually:
```bash
# Disable cert-manager entirely
kubectl scale deployment cert-manager --replicas=0 -n cert-manager
kubectl scale deployment cert-manager-webhook --replicas=0 -n cert-manager
kubectl scale deployment cert-manager-cainjector --replicas=0 -n cert-manager
```

Then manually renew any expiring certificates until you can get cert-manager working on 1.30.

**Next steps:** Once pods are creating successfully, upgrade cert-manager to a 1.30-compatible version and monitor for any certificate renewal issues.
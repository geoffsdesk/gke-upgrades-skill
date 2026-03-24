This is a common issue after control plane upgrades - cert-manager webhook certificates often become incompatible with the new API server version. Here's the urgent fix:

## Immediate Mitigation (Temporary)

First, allow pod creation by setting the webhook to "Ignore" failures:

```bash
# Find cert-manager webhook configurations
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily disable validation (example webhook name)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Test pod creation immediately
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation works"
```

## Permanent Fix

The root cause is cert-manager version incompatibility with Kubernetes 1.32. Fix it properly:

```bash
# 1. Check current cert-manager version
kubectl get pods -n cert-manager -o wide
kubectl describe pod -n cert-manager -l app=cert-manager | grep Image:

# 2. Upgrade cert-manager to a 1.32-compatible version
# Check compatibility matrix first: https://cert-manager.io/docs/installation/supported-releases/
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1 \
  --set crds.enabled=true

# 3. Wait for cert-manager pods to be ready
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=300s

# 4. Verify webhook is working
kubectl get certificaterequests -A
kubectl logs -n cert-manager -l app=cert-manager --tail=50

# 5. Test pod creation again
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook working"
```

## Revert Temporary Fix

Once cert-manager is upgraded and working:

```bash
# Restore webhook to "Fail" policy
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Next Time

Before your next control plane upgrade:

```bash
# Pre-upgrade checklist addition:
# - [ ] Verify cert-manager version supports target Kubernetes version
# - [ ] Check all admission webhook operators for compatibility
# - [ ] Test webhook functionality in staging cluster first

# Check webhook compatibility before upgrading
kubectl get validatingwebhookconfigurations -o yaml | grep -A 10 "admissionReviewVersions"
```

## If cert-manager upgrade fails

Fallback plan if the cert-manager upgrade has issues:

```bash
# Completely remove cert-manager webhook temporarily
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# This allows pods to create while you troubleshoot cert-manager
# Reinstall/reconfigure cert-manager when ready
```

Your pods should be able to create immediately after the first step. The permanent fix ensures this doesn't happen again on future upgrades.

**Key lesson:** Always check admission controller compatibility (cert-manager, policy controllers, service mesh operators) before upgrading the control plane. They often need updates to work with new Kubernetes API versions.
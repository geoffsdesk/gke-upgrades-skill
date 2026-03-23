# Urgent Fix for Post-Upgrade Webhook Issues

This is a common issue after GKE control plane upgrades - the cert-manager webhook certificates may be invalid for the new API server. Here's the immediate fix:

## Emergency Resolution (Choose Option A or B)

### Option A: Temporarily disable the failing webhook
```bash
# Identify the problematic webhook
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check which one is failing (look for cert-manager-webhook)
kubectl describe validatingwebhookconfigurations cert-manager-webhook

# Temporarily disable it by setting failurePolicy to Ignore
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

### Option B: Restart cert-manager (often resolves certificate issues)
```bash
# Restart cert-manager pods to refresh certificates
kubectl rollout restart deployment cert-manager -n cert-manager
kubectl rollout restart deployment cert-manager-webhook -n cert-manager
kubectl rollout restart deployment cert-manager-cainjector -n cert-manager

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=120s
```

## Verification
```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "webhook test"

# Check webhook status
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep failurePolicy
```

## Root Cause & Permanent Fix

The issue is likely that cert-manager's webhook certificates became invalid after the control plane upgrade. This happens because:
1. The API server's CA bundle changed during the upgrade
2. cert-manager's webhook certificates were issued for the old API server

**Permanent resolution:**
```bash
# Delete the webhook secret to force regeneration
kubectl delete secret cert-manager-webhook-ca -n cert-manager

# Restart cert-manager to regenerate certificates
kubectl rollout restart deployment cert-manager-webhook -n cert-manager

# Re-enable webhook if you used Option A
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Monitoring
```bash
# Watch for successful pod creation
kubectl get events --field-selector reason=Failed -w

# Check cert-manager logs
kubectl logs -f deployment/cert-manager-webhook -n cert-manager
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:
- [ ] Document all admission webhooks: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
- [ ] Plan to restart webhook-dependent operators post-upgrade
- [ ] Consider webhook `failurePolicy: Ignore` during maintenance windows for non-critical webhooks

**Time to resolution:** 2-5 minutes for the emergency fix, 5-10 minutes for the permanent solution.

The restart approach (Option B) is usually the cleanest fix as it addresses the root cause without temporarily weakening security posture.
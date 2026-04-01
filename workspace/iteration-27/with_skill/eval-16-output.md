This is a common post-upgrade issue where admission webhooks fail after Kubernetes version changes. Here's the immediate fix:

## Immediate Mitigation (Emergency Fix)

First, temporarily disable the failing webhook to restore pod creation:

```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch it to ignore failures temporarily
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

Test that pods can now be created:
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass working"
```

## Root Cause & Permanent Fix

**Root cause:** cert-manager's webhook certificates likely weren't updated for the new Kubernetes 1.32 API server, causing validation failures.

**Permanent fix steps:**

1. **Check cert-manager version compatibility:**
```bash
kubectl get deployment -n cert-manager cert-manager -o yaml | grep image:
```

2. **Upgrade cert-manager to a version supporting Kubernetes 1.32:**
```bash
# Check current cert-manager version
helm list -A | grep cert-manager

# Upgrade to latest version (check cert-manager docs for 1.32 compatibility)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.13.3 \
  --reuse-values
```

3. **Wait for cert-manager pods to be ready:**
```bash
kubectl get pods -n cert-manager
kubectl rollout status deployment/cert-manager -n cert-manager
```

4. **Test that the webhook works properly:**
```bash
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook functioning"
```

5. **Re-enable webhook failure policy (remove temporary bypass):**
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:
- [ ] Verify all admission webhook operators support target Kubernetes version
- [ ] Test webhook compatibility in staging before production upgrade
- [ ] Have webhook bypass commands ready for emergency use

## Alternative if cert-manager upgrade fails

If the cert-manager upgrade doesn't resolve it, you may need to:

1. **Completely remove and reinstall cert-manager:**
```bash
# Back up certificates first
kubectl get certificates -A -o yaml > cert-backup.yaml

# Remove cert-manager
helm uninstall cert-manager -n cert-manager

# Reinstall with K8s 1.32-compatible version
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.13.3 \
  --set installCRDs=true
```

2. **Restore certificates from backup if needed**

This should resolve your immediate pod creation issues. The webhook bypass gives you breathing room to properly fix cert-manager compatibility.
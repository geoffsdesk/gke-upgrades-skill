# Urgent Fix: cert-manager Webhook Blocking Pod Creation After 1.31→1.32 Upgrade

## Immediate Mitigation (Apply Now)

**Step 1: Temporarily disable the failing webhook**
```bash
# Check which cert-manager webhook is failing
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily set failure policy to "Ignore" (allows pods to create)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's also a mutating webhook:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Step 2: Verify pod creation works**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pods can create again"
```

## Root Cause & Permanent Fix

The issue is cert-manager's webhook certificates are incompatible with the new Kubernetes 1.32 API server. This is common after control plane upgrades.

**Step 3: Check cert-manager version compatibility**
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o wide
helm list -n cert-manager  # if installed via Helm

# Check if your version supports Kubernetes 1.32
# Cert-manager 1.13+ supports Kubernetes 1.32
```

**Step 4: Upgrade cert-manager to compatible version**
```bash
# If using Helm:
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.0 \  # Latest stable supporting K8s 1.32
  --set installCRDs=true

# If using kubectl/manifests:
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.0/cert-manager.yaml
```

**Step 5: Wait for cert-manager to reconcile**
```bash
# Monitor cert-manager pods restart and become ready
kubectl get pods -n cert-manager -w

# Check webhook is healthy
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep caBundle
```

**Step 6: Restore webhook security**
```bash
# Re-enable strict failure policy
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# Test pod creation still works with strict policy
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook working correctly"
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```bash
# Before control plane upgrade, check webhook compatibility:
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# For each third-party operator:
# 1. Verify operator version supports target Kubernetes version
# 2. Upgrade operators BEFORE upgrading control plane
# 3. Test pod creation in staging with the new versions
```

## If cert-manager Upgrade Fails

**Fallback: Temporarily remove webhook entirely**
```bash
# Delete webhook configs (cert-manager will recreate them)
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# Wait 2-3 minutes for cert-manager to recreate with fresh certificates
kubectl get validatingwebhookconfigurations cert-manager-webhook
```

**Your pods should be creating normally now.** The temporary "Ignore" policy allows workloads to function while you upgrade cert-manager to a 1.32-compatible version.

**Time to resolution: ~10-15 minutes** (immediate mitigation + permanent fix)
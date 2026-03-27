# Cert-Manager Webhook Failure After GKE 1.31→1.32 Upgrade

This is a common issue when the cert-manager version doesn't support the new Kubernetes API version. Here's the immediate fix and permanent solution:

## Immediate Mitigation (5 minutes)

**Temporarily disable webhook validation to restore pod creation:**

```bash
# Find the cert-manager webhook configurations
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily set failurePolicy to Ignore (allows pod creation to proceed)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's a mutating webhook too:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test that pods can now be created:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Permanent Fix (15-30 minutes)

**1. Check cert-manager version compatibility:**
```bash
# Current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it supports Kubernetes 1.32
# Cert-manager 1.13+ supports K8s 1.28-1.32
# Cert-manager 1.14+ recommended for K8s 1.32
```

**2. Upgrade cert-manager to a compatible version:**
```bash
# If installed via Helm:
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.2 \
  --set crds.enabled=true

# If installed via kubectl/manifests:
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

**3. Wait for cert-manager to be ready:**
```bash
kubectl wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=300s
kubectl wait --for=condition=Available deployment/cert-manager-cainjector -n cert-manager --timeout=300s
kubectl wait --for=condition=Available deployment/cert-manager-webhook -n cert-manager --timeout=300s
```

**4. Restore webhook validation:**
```bash
# Re-enable strict validation
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

**5. Final validation:**
```bash
# Test that certificates still work
kubectl get certificates -A
kubectl get certificaterequests -A

# Create a test pod to confirm webhook is working properly
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook validation restored"
```

## Root Cause & Prevention

**Why this happened:** Cert-manager's admission webhook validates certificate resources against the Kubernetes API. When GKE upgraded from 1.31→1.32, the API server changed, but cert-manager's webhook was still using API patterns compatible with 1.31.

**Prevention checklist for future upgrades:**
- [ ] Check operator compatibility matrix before control plane upgrades
- [ ] Test webhook operators in dev/staging clusters first
- [ ] Keep cert-manager on recent versions (within 2-3 releases of latest)
- [ ] Subscribe to cert-manager release notes for K8s compatibility updates

## If Helm Upgrade Fails

If the Helm upgrade fails due to CRD conflicts:
```bash
# Check current CRDs
kubectl get crds | grep cert-manager

# Manual CRD upgrade if needed
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.crds.yaml

# Then retry Helm upgrade
helm upgrade cert-manager jetstack/cert-manager --namespace cert-manager --version v1.16.2
```

This should restore pod creation immediately with the temporary fix, then provide a permanent solution within 30 minutes.
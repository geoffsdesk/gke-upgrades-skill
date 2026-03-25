# Urgent Fix for Cert-Manager Webhook Failures After GKE Upgrade

## Immediate Mitigation (Temporary)

First, let's bypass the failing webhook to restore pod creation:

```bash
# Check which cert-manager webhooks are configured
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily set failurePolicy to Ignore (allows pod creation to proceed)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's a mutating webhook too:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test immediately:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Root Cause

Cert-manager's admission webhook certificates are likely incompatible with the new Kubernetes 1.32 API server. This is common when the cert-manager version predates support for your target Kubernetes version.

## Permanent Fix

### 1. Check cert-manager version compatibility
```bash
# Current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}'

# Check cert-manager pods
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

### 2. Upgrade cert-manager to a version supporting Kubernetes 1.32

```bash
# Check your current Helm release
helm list -n cert-manager

# Upgrade to latest cert-manager (supports K8s 1.32)
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3 \
  --set installCRDs=true
```

### 3. Verify the fix
```bash
# Wait for cert-manager pods to be ready
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=300s

# Test pod creation works
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook fixed"

# Check webhook is responding correctly
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep failurePolicy
```

### 4. Restore webhook failurePolicy to "Fail"
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Alternative: Quick Cert-Manager Reinstall

If Helm upgrade fails, you can reinstall cert-manager:

```bash
# Back up any custom ClusterIssuers first
kubectl get clusterissuers -o yaml > clusterissuers-backup.yaml

# Uninstall old cert-manager
helm uninstall cert-manager -n cert-manager

# Install latest version
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.15.3 \
  --set installCRDs=true

# Restore ClusterIssuers
kubectl apply -f clusterissuers-backup.yaml
```

## Prevention for Future Upgrades

**Pre-Upgrade Checklist Addition:**
- [ ] Verify cert-manager version supports target Kubernetes version
- [ ] Check [cert-manager supported releases](https://cert-manager.io/docs/installation/supported-releases/) before GKE control plane upgrades
- [ ] Test admission webhook compatibility in a staging cluster first

**Cert-Manager Compatibility Matrix:**
- Kubernetes 1.32: cert-manager v1.13+ required
- Kubernetes 1.31: cert-manager v1.12+ required  
- Kubernetes 1.30: cert-manager v1.11+ required

The temporary failurePolicy bypass gives you breathing room to fix the root cause without blocking deployments. Always test the permanent fix in staging first for future upgrades.
This is a classic post-upgrade admission webhook compatibility issue. Here's the immediate fix and permanent solution:

## Immediate Fix (Temporary)

First, identify the problematic webhook and temporarily disable it:

```bash
# Find cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily set webhook to ignore failures (allows pod creation)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's a mutating webhook too:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test pod creation immediately:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass working"
```

## Permanent Fix

The root cause is cert-manager's webhook certificates are incompatible with the new API server version (1.32). Fix by upgrading cert-manager:

```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o wide

# Check what cert-manager versions support Kubernetes 1.32
# (Generally need cert-manager 1.13+ for K8s 1.32 support)

# Upgrade cert-manager via Helm (most common method)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3 \
  --set installCRDs=true
```

**Or if using kubectl/manifests:**
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
```

## Verification & Cleanup

```bash
# Wait for cert-manager pods to be ready
kubectl get pods -n cert-manager
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=300s

# Test certificate issuance
kubectl get certificates -A
kubectl describe certificate YOUR_CERT_NAME -n NAMESPACE

# Verify pod creation works normally
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Normal webhook validation working"

# Revert the temporary failurePolicy to "Fail" (restore normal validation)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:
- [ ] Verify cert-manager version supports target Kubernetes version
- [ ] Check [cert-manager compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/)
- [ ] Test webhook operators in staging cluster before production upgrade

## Root Cause

Kubernetes 1.32 introduced API changes that older cert-manager versions can't handle. The webhook tries to validate certificates against the new API schema but fails, blocking all pod creation. This is why we see the issue immediately after control plane upgrade - even though nodes are still on 1.31, the API server (webhooks) is now 1.32.

The temporary `failurePolicy: Ignore` bypasses webhook validation entirely, allowing pods to create while you upgrade cert-manager to a compatible version.
# Cert-manager Webhook Failure After GKE 1.31→1.32 Upgrade

This is a common post-upgrade issue. The cert-manager webhook is likely rejecting pod creation because it hasn't updated its certificates for the new API server version.

## Immediate Fix (Temporary)

**Step 1: Identify the failing webhook**
```bash
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager
```

**Step 2: Temporarily disable webhook validation**
```bash
# For validating webhook (most common)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's also a mutating webhook
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Step 3: Test pod creation**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "test"
# Should work now
```

## Permanent Fix

**Step 4: Check cert-manager version compatibility**
```bash
kubectl get deployment cert-manager -n cert-manager -o yaml | grep image:
```

**Step 5: Upgrade cert-manager to a version supporting K8s 1.32**
```bash
# If using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.0  # or latest version supporting 1.32

# If using kubectl/manifests
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml
```

**Step 6: Wait for cert-manager to restart and issue new certificates**
```bash
kubectl get pods -n cert-manager
# Wait for all pods to be Running
```

**Step 7: Restore webhook security**
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

**Step 8: Final validation**
```bash
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "final test"
kubectl delete pod test-pod-2  # if it was created
```

## Root Cause & Prevention

**What happened:** Cert-manager's admission webhook validates certificate-related resources. After the control plane upgrade to 1.32, the webhook's TLS certificate became invalid for the new API server version, causing all pod creation to fail.

**Prevention for future upgrades:**
1. Before upgrading control plane, verify all third-party operators support the target K8s version
2. Check the [cert-manager compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/)
3. Upgrade operators BEFORE upgrading GKE when possible

## If cert-manager upgrade fails

If the cert-manager upgrade itself fails due to webhook validation:

```bash
# Temporarily delete the webhook entirely
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# Upgrade cert-manager
helm upgrade cert-manager jetstack/cert-manager --version v1.14.0

# The new version will recreate the webhooks automatically
```

This should restore pod creation immediately. The temporary `failurePolicy: Ignore` is safe for a few minutes while you upgrade cert-manager.
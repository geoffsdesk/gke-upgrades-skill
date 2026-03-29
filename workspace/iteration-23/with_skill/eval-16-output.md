# Cert-Manager Admission Webhook Fix After GKE 1.31→1.32 Upgrade

## Immediate Mitigation (5 minutes)

First, identify the failing webhook and temporarily set it to `Ignore` failures:

```bash
# Find cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily disable validation (CHOOSE ONE based on what's failing)
# For validating webhook:
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# For mutating webhook:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test pod creation immediately:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass test"
```

If that works, your workloads can now deploy while we fix the root cause.

## Root Cause Analysis

Check cert-manager compatibility with Kubernetes 1.32:

```bash
# Check current cert-manager version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check webhook certificate status
kubectl get certificate -n cert-manager cert-manager-webhook-ca
kubectl describe certificate -n cert-manager cert-manager-webhook-ca

# Check webhook pods for errors
kubectl logs -n cert-manager -l app=webhook --tail=50
```

**Common issue:** Cert-manager versions prior to v1.13.x may not fully support Kubernetes 1.32's API changes.

## Permanent Fix

### Option 1: Upgrade cert-manager (Recommended)

```bash
# Check your current Helm chart version first
helm list -n cert-manager

# Upgrade to a 1.32-compatible version (v1.13.x or later)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.13.3 \
  --set installCRDs=true

# Wait for rollout
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager

# Verify webhook is healthy
kubectl get pods -n cert-manager
```

### Option 2: Restart cert-manager components

If you can't upgrade immediately:

```bash
# Restart cert-manager components to refresh webhook certificates
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager

# Wait for readiness
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

## Restore Security

Once cert-manager is fixed, restore the webhook's failure policy:

```bash
# Re-enable webhook validation
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# Test that webhook works properly
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Webhook validation test"
```

## Verification Checklist

- [ ] Pods can be created without admission errors
- [ ] Cert-manager webhook pods are Running and Ready
- [ ] Certificate resources are being processed normally
- [ ] Webhook failure policy restored to "Fail"
- [ ] New TLS certificates can be issued

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```bash
# Before upgrading GKE control plane, check webhook operator compatibility
kubectl get validatingwebhookconfigurations -o json | \
  jq -r '.items[] | select(.webhooks[].clientConfig.service != null) | .metadata.name'

# Verify each webhook operator supports the target Kubernetes version
# Update operators BEFORE upgrading the control plane
```

**Key lesson:** Third-party operators (cert-manager, service mesh, policy engines) often lag behind Kubernetes releases. Always verify operator compatibility before GKE control plane upgrades.

This pattern applies to other webhook operators too - Istio, OPA Gatekeeper, Falco, etc. The temporary `failurePolicy: Ignore` mitigation works for any admission webhook blocking your workloads post-upgrade.
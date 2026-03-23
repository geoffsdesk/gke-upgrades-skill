# GKE Upgrade Incident: Admission Webhook Blocking Pod Creation

## Immediate Fix (Emergency Bypass)

The cert-manager admission webhook is likely rejecting pods due to version compatibility issues. Here's the urgent fix:

### 1. Identify the problematic webhook
```bash
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager
```

### 2. Emergency bypass - Add failure policy
```bash
# Back up the webhook first
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Patch to ignore failures temporarily
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

This allows pod creation to proceed even if the webhook fails.

### 3. Verify pods can be created
```bash
# Try creating a test pod
kubectl run test-pod --image=nginx --rm -i --tty
```

## Root Cause Analysis

### Check cert-manager compatibility
```bash
# Check cert-manager version
kubectl get pods -n cert-manager -o wide
kubectl describe deployment cert-manager -n cert-manager | grep Image

# Check webhook pod logs
kubectl logs -n cert-manager -l app=webhook --tail=50
```

Cert-manager versions prior to v1.13 may have compatibility issues with Kubernetes 1.32. The webhook might be:
- Using deprecated APIs that changed behavior in 1.32
- Having TLS certificate validation issues with the new API server
- Experiencing timeout issues with the admission review process

## Permanent Fix Options

### Option 1: Upgrade cert-manager (Recommended)
```bash
# Check current cert-manager version
helm list -n cert-manager

# Upgrade to latest version (1.14+ supports K8s 1.32)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.2 \
  --set installCRDs=true
```

### Option 2: Downgrade webhook to warn-only temporarily
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore","admissionReviewVersions":["v1","v1beta1"]}]}'
```

### Option 3: Temporarily disable the webhook entirely
```bash
# Only if other options fail - this removes certificate validation
kubectl delete validatingwebhookconfigurations cert-manager-webhook
```

## Validation Steps

After applying the fix:

```bash
# Confirm pods can be created
kubectl get pods -A | grep Pending | wc -l
# Should return 0

# Check webhook is responding (after upgrade)
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep failurePolicy

# Verify cert-manager functionality
kubectl get certificates -A
kubectl describe certificate YOUR_CERT_NAME -n NAMESPACE
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```markdown
- [ ] Third-party operator compatibility verified against target K8s version
- [ ] Cert-manager version supports target Kubernetes version (check compatibility matrix)
- [ ] Admission webhook failure policies set to "Ignore" for non-critical webhooks during upgrades
- [ ] Staging cluster tested with same operator versions
```

## Compatibility Reference

| cert-manager version | Kubernetes support |
|---------------------|-------------------|
| v1.14+ | 1.28-1.32 |
| v1.13 | 1.28-1.31 |
| v1.12 | 1.27-1.30 |

**Next steps:** Once pods are creating successfully, plan to upgrade cert-manager to v1.14+ during your next maintenance window to ensure full K8s 1.32 compatibility.

The emergency bypass should restore service immediately. The webhook failure policy change allows workloads to deploy while you plan the proper cert-manager upgrade.
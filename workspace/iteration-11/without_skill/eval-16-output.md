This is a critical issue likely caused by API version compatibility changes in Kubernetes 1.32. Here's how to fix it urgently:

## Immediate Emergency Fix (Choose One)

### Option 1: Bypass the webhook temporarily
```bash
# Check which webhook is failing
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Temporarily delete the problematic webhook (EMERGENCY ONLY)
kubectl delete validatingadmissionwebhook <webhook-name>
# or
kubectl delete mutatingadmissionwebhook <webhook-name>
```

### Option 2: Disable webhook temporarily
```bash
# Edit the webhook and set failurePolicy to Ignore
kubectl patch validatingadmissionwebhook <webhook-name> -p '{"webhooks":[{"name":"<webhook-name>","failurePolicy":"Ignore"}]}'
```

## Proper Fix: Update cert-manager

### 1. Check current cert-manager version
```bash
kubectl get pods -n cert-manager
kubectl get deployment -n cert-manager cert-manager -o yaml | grep image:
```

### 2. Upgrade to compatible version
```bash
# Upgrade to latest cert-manager (supports k8s 1.32)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml

# Or if using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3
```

### 3. Verify the fix
```bash
# Check cert-manager pods are running
kubectl get pods -n cert-manager

# Test webhook connectivity
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml

# Try creating a test pod
kubectl run test-pod --image=nginx --dry-run=server -o yaml
```

## Root Cause Analysis

### Check webhook configuration
```bash
# Look for API version mismatches
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml | grep -A 10 -B 10 "apiVersion\|admissionReviewVersions"

# Check webhook endpoint health
kubectl get endpoints -n cert-manager cert-manager-webhook
```

### Check cert-manager logs
```bash
kubectl logs -n cert-manager deployment/cert-manager-webhook --tail=100
kubectl logs -n cert-manager deployment/cert-manager --tail=100
```

## Prevention for Future Upgrades

### 1. Version compatibility matrix
```bash
# Always check compatibility before upgrading
# cert-manager 1.13+ supports Kubernetes 1.28-1.32
# cert-manager 1.12 supports Kubernetes 1.25-1.29
```

### 2. Staging environment testing
```bash
# Test webhook functionality after control plane upgrade
kubectl auth can-i create pods --as=system:serviceaccount:default:default
```

## If cert-manager won't start

### Rollback approach
```bash
# Get previous working version from your records, then:
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.7/cert-manager.yaml

# Or restore from backup if available
```

The most likely cause is that cert-manager's admission webhook doesn't support the `admissionregistration.k8s.io/v1` API changes in Kubernetes 1.32. Upgrading cert-manager to v1.15+ should resolve this immediately.

**Priority**: Fix the webhook first (Option 1 or 2 above), then properly upgrade cert-manager to prevent future issues.
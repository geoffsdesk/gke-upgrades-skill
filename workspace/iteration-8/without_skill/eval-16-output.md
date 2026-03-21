This is a common issue when upgrading Kubernetes versions - the webhook configurations may be incompatible with the new API server. Here are immediate steps to resolve this:

## Immediate Fix (Get workloads running)

### Option 1: Temporarily disable the problematic webhook
```bash
# Find the failing webhook
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Temporarily disable cert-manager webhook
kubectl patch validatingadmissionwebhook cert-manager-webhook --type='merge' -p='{"webhooks":[{"name":"webhook.cert-manager.io","admissionReviewVersions":["v1","v1beta1"],"failurePolicy":"Ignore"}]}'
```

### Option 2: Delete the webhook temporarily
```bash
# List webhooks to find cert-manager ones
kubectl get validatingadmissionwebhooks | grep cert-manager
kubectl get mutatingadmissionwebhooks | grep cert-manager

# Delete them temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

## Permanent Fix

### 1. Upgrade cert-manager
```bash
# Check current version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Upgrade to latest version compatible with k8s 1.32
helm repo update
helm upgrade cert-manager jetstack/cert-manager --namespace cert-manager --version v1.15.0 # or latest
```

### 2. If upgrade isn't immediately possible, patch the webhook
```bash
# Update admissionReviewVersions to include both v1 and v1beta1
kubectl patch validatingadmissionwebhook cert-manager-webhook --type='json' -p='[{"op": "replace", "path": "/webhooks/0/admissionReviewVersions", "value": ["v1", "v1beta1"]}]'
```

## Diagnostic Commands

Check what's failing:
```bash
# Check webhook status
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml
kubectl get mutatingadmissionwebhooks cert-manager-webhook -o yaml

# Check cert-manager pods
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server
```

## Root Cause
Kubernetes 1.32 likely deprecated `admissionregistration.k8s.io/v1beta1` in favor of `v1`. The cert-manager webhook configuration needs to support the newer API version.

## Prevention
- Always check operator compatibility matrices before K8s upgrades
- Test upgrades in staging first
- Keep operators updated regularly

Try Option 1 first as it's the safest immediate fix. Let me know if you need help with any of these steps!
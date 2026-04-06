This is a common issue during Kubernetes upgrades when webhook configurations become incompatible. Here's how to resolve it urgently:

## Immediate Fix Options

### Option 1: Temporarily Disable the Webhook (Fastest)
```bash
# List admission webhooks to identify cert-manager ones
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Temporarily disable cert-manager webhooks
kubectl patch validatingadmissionwebhook cert-manager-webhook --type='merge' -p='{"webhooks":[{"name":"webhook.cert-manager.io","admissionReviewVersions":["v1","v1beta1"],"failurePolicy":"Ignore"}]}'

kubectl patch mutatingadmissionwebhook cert-manager-webhook --type='merge' -p='{"webhooks":[{"name":"webhook.cert-manager.io","admissionReviewVersions":["v1","v1beta1"],"failurePolicy":"Ignore"}]}'
```

### Option 2: Delete Webhook Configurations (If patching fails)
```bash
# Only if absolutely necessary - this will disable cert validation temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

## Permanent Fix

### Upgrade cert-manager
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o wide

# Upgrade to latest compatible version
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.13.3 \
  --set installCRDs=true
```

Or using kubectl:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

## Verify the Fix

```bash
# Check webhook status
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml
kubectl get mutatingadmissionwebhooks cert-manager-webhook -o yaml

# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "success"

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

## Root Cause Analysis

The issue likely stems from:
1. **AdmissionReview API version changes** in K8s 1.32
2. **Deprecated webhook configurations** not supported
3. **TLS/certificate issues** with the webhook endpoint

## Prevention for Future Upgrades

```bash
# Always check compatibility before upgrading
kubectl get validatingadmissionwebhooks -o json | jq '.items[].webhooks[].admissionReviewVersions'
kubectl get mutatingadmissionwebhooks -o json | jq '.items[].webhooks[].admissionReviewVersions'
```

## If Webhook Endpoint is Unreachable

```bash
# Check webhook service
kubectl get svc -n cert-manager cert-manager-webhook

# Check webhook pod status
kubectl get pods -n cert-manager -l app.kubernetes.io/component=webhook

# Restart webhook if needed
kubectl rollout restart deployment cert-manager-webhook -n cert-manager
```

Start with Option 1 (patching) as it's the safest immediate fix, then proceed with the cert-manager upgrade for a permanent solution.
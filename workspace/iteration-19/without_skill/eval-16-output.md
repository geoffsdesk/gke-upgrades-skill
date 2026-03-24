This is a critical issue likely caused by API version compatibility problems with cert-manager's admission webhook after the Kubernetes upgrade. Here's how to resolve it urgently:

## Immediate Emergency Fix (if pods are completely blocked)

**Option 1: Temporarily disable the webhook**
```bash
# List admission webhooks to identify cert-manager ones
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Temporarily disable cert-manager webhooks
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

**Option 2: Scale down cert-manager webhook temporarily**
```bash
kubectl -n cert-manager scale deployment cert-manager-webhook --replicas=0
```

## Proper Fix Steps

### 1. Check cert-manager version compatibility
```bash
# Check current cert-manager version
kubectl -n cert-manager get deployment cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it supports Kubernetes 1.32
# Refer to cert-manager compatibility matrix
```

### 2. Upgrade cert-manager to compatible version
```bash
# For cert-manager v1.14+ (supports K8s 1.32)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml

# Or if using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.4
```

### 3. If webhook certificate has expired or is invalid
```bash
# Check webhook configuration
kubectl get validatingadmissionwebhook cert-manager-webhook -o yaml

# Restart cert-manager to regenerate webhook certificates
kubectl -n cert-manager rollout restart deployment cert-manager
kubectl -n cert-manager rollout restart deployment cert-manager-webhook
kubectl -n cert-manager rollout restart deployment cert-manager-cainjector

# Wait for rollout
kubectl -n cert-manager rollout status deployment cert-manager-webhook
```

### 4. Check webhook service and endpoints
```bash
# Verify webhook service is accessible
kubectl -n cert-manager get svc cert-manager-webhook
kubectl -n cert-manager get endpoints cert-manager-webhook

# Test webhook connectivity
kubectl -n cert-manager port-forward svc/cert-manager-webhook 9443:443 &
curl -k https://localhost:9443/validate
```

### 5. Recreate webhook configurations if needed
```bash
# Delete and recreate webhook configs (they'll be recreated automatically)
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook

# Restart cert-manager to recreate them
kubectl -n cert-manager rollout restart deployment cert-manager
```

## Quick Validation

```bash
# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server -o yaml

# Check webhook logs
kubectl -n cert-manager logs -l app=webhook -f

# Verify webhook is healthy
kubectl -n cert-manager get pods -l app=webhook
```

## Prevention for Future Upgrades

```bash
# Always check compatibility before upgrading
# Set up monitoring for webhook failures
# Consider webhook failure policies

# Check current failure policy
kubectl get validatingadmissionwebhook cert-manager-webhook -o jsonpath='{.webhooks[0].failurePolicy}'
```

## If the above doesn't work immediately:

1. **Check specific error messages** in the admission controller logs
2. **Verify API versions** - cert-manager might be using deprecated APIs
3. **Consider rollback** if this is production critical
4. **Update webhook failure policy** to "Ignore" temporarily if safe for your use case

The most common cause is cert-manager version incompatibility with Kubernetes 1.32. Upgrading cert-manager should resolve the issue permanently.
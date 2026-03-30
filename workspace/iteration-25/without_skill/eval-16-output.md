This is a common issue during Kubernetes upgrades due to API version changes. Here's how to resolve it urgently:

## Immediate Emergency Fix (if pods can't be created at all)

**Option 1: Temporarily disable the webhook**
```bash
# Find the webhook
kubectl get validatingadmissionwebhooks
kubectl get mutatingadmissionwebhooks

# Temporarily delete/disable cert-manager webhooks
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

## Proper Resolution Steps

### 1. Check cert-manager compatibility
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager
kubectl describe deployment cert-manager -n cert-manager

# Check webhook status
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml
kubectl get mutatingadmissionwebhooks cert-manager-webhook -o yaml
```

### 2. Upgrade cert-manager to compatible version
```bash
# For K8s 1.32, you need cert-manager v1.15.0+
# Check compatibility matrix: https://cert-manager.io/docs/installation/supported-releases/

# Upgrade cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.1/cert-manager.yaml

# Or using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.1
```

### 3. Verify webhook certificate
```bash
# Check webhook certificate validity
kubectl get secret cert-manager-webhook-ca -n cert-manager -o yaml

# Force certificate renewal if needed
kubectl delete secret cert-manager-webhook-ca -n cert-manager
kubectl rollout restart deployment cert-manager-webhook -n cert-manager
```

### 4. Check API server connectivity
```bash
# Ensure webhook service is reachable
kubectl get svc cert-manager-webhook -n cert-manager
kubectl get endpoints cert-manager-webhook -n cert-manager

# Test connectivity from API server
kubectl run test-webhook --rm -i --tty --image=curlimages/curl -- \
  curl -k https://cert-manager-webhook.cert-manager.svc.cluster.local/validate
```

## Quick Validation

```bash
# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server -o yaml

# Check webhook logs
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Verify webhook registration
kubectl get validatingadmissionwebhooks cert-manager-webhook \
  -o jsonpath='{.webhooks[0].clientConfig.service}'
```

## Prevention for Future Upgrades

1. **Check compatibility matrices** before upgrading
2. **Upgrade operators first** in a staging environment
3. **Use admission controller bypass** for emergency access:
   ```bash
   kubectl create --validate=false
   ```

The most likely cause is that your cert-manager version doesn't support Kubernetes 1.32's API changes. Upgrading cert-manager should resolve the issue permanently.

Would you like me to help you identify the specific cert-manager version you're running or walk through any of these steps?
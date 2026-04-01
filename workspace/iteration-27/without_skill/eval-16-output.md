This is a common issue after Kubernetes upgrades where admission webhooks become incompatible or fail to validate against the new API server version. Here's how to fix it urgently:

## Immediate Emergency Fix

**Option 1: Temporarily disable the problematic admission webhook**

```bash
# List all validating admission webhooks
kubectl get validatingadmissionwebhooks

# List all mutating admission webhooks  
kubectl get mutatingadmissionwebhooks

# Find cert-manager webhooks (usually named like cert-manager-webhook)
kubectl get validatingadmissionwebhooks | grep cert-manager
kubectl get mutatingadmissionwebhooks | grep cert-manager

# Temporarily disable by removing the webhook rules
kubectl patch validatingadmissionwebhook cert-manager-webhook --type='merge' -p='{"webhooks":[]}'
kubectl patch mutatingadmissionwebhook cert-manager-webhook --type='merge' -p='{"webhooks":[]}'
```

## Root Cause Analysis

**Check webhook status and logs:**

```bash
# Check cert-manager pods
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Check webhook configuration
kubectl describe validatingadmissionwebhook cert-manager-webhook
kubectl describe mutatingadmissionwebhook cert-manager-webhook

# Check if webhook endpoint is reachable
kubectl get endpoints -n cert-manager
```

## Proper Fix

**Option 1: Upgrade cert-manager to compatible version**

```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Upgrade to a version compatible with k8s 1.32
# Check cert-manager compatibility matrix: https://cert-manager.io/docs/installation/supported-releases/

helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1 \
  --set installCRDs=true
```

**Option 2: Reinstall cert-manager**

```bash
# Remove old installation
helm uninstall cert-manager -n cert-manager

# Install compatible version
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.16.1 \
  --set installCRDs=true
```

## Prevent Similar Issues

**Check webhook health:**

```bash
# Create a monitoring script
cat << 'EOF' > check-webhooks.sh
#!/bin/bash
for webhook in $(kubectl get validatingadmissionwebhooks -o name); do
  echo "Checking $webhook"
  kubectl get $webhook -o jsonpath='{.webhooks[*].clientConfig.service}' | jq .
done
EOF
chmod +x check-webhooks.sh
```

**Test webhook after fix:**

```bash
# Create a test pod to verify admission webhooks work
kubectl run test-pod --image=nginx --dry-run=server -o yaml | kubectl apply -f -
kubectl delete pod test-pod
```

## Alternative Quick Recovery

If upgrading fails, you can also:

```bash
# Scale down cert-manager temporarily
kubectl scale deployment cert-manager-webhook --replicas=0 -n cert-manager

# Remove webhook configurations
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook

# This allows pods to be created, then fix cert-manager and reinstall
```

## Verification

```bash
# Verify pods can be created
kubectl run test-nginx --image=nginx
kubectl get pods test-nginx

# Verify cert-manager is working
kubectl get certificates --all-namespaces
kubectl get certificaterequests --all-namespaces
```

The key is that Kubernetes 1.32 likely introduced stricter validation or API changes that the older cert-manager version doesn't handle. Always check the [cert-manager compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/) before upgrading Kubernetes.

Would you like me to help you with any specific error messages you're seeing?
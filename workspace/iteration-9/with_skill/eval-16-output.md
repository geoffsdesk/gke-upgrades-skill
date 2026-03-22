# Cert-Manager Admission Webhook Troubleshooting - Urgent Fix

This is a common issue after GKE control plane upgrades. The cert-manager webhook likely has version compatibility issues or certificate problems with Kubernetes 1.32.

## Immediate Diagnosis

Run these commands to identify the problem:

```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check cert-manager pods status
kubectl get pods -n cert-manager

# Look for webhook-specific errors
kubectl get events -A --field-selector reason=FailedCreate
kubectl logs -n cert-manager -l app=webhook --tail=50
```

## Quick Fix Options (in order of preference)

### Option 1: Restart cert-manager webhook (safest first attempt)

```bash
# Restart the webhook deployment
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager

# Wait for restart to complete
kubectl rollout status deployment/cert-manager-webhook -n cert-manager

# Test pod creation
kubectl run test-pod --image=nginx --dry-run=server -o yaml
```

### Option 2: Temporarily disable webhook validation (if Option 1 fails)

```bash
# Get current webhook config
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Disable webhook temporarily by setting failurePolicy to Ignore
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'

# Test that pods can now be created
kubectl run test-pod --image=nginx --rm -it -- echo "Webhook bypassed"
```

### Option 3: Delete webhook temporarily (nuclear option)

```bash
# Only if Options 1 & 2 fail - backup first
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml
kubectl get mutatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-mutating-webhook-backup.yaml

# Delete the problematic webhook
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# Verify pods can be created
kubectl run test-pod --image=nginx --rm -it -- echo "Success"
```

## Root Cause Resolution

After immediate fix, address the underlying issue:

### Check cert-manager version compatibility

```bash
# Check current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it's compatible with Kubernetes 1.32
# cert-manager 1.13+ supports Kubernetes 1.28-1.32
# cert-manager 1.12+ supports Kubernetes 1.27-1.31
```

### Upgrade cert-manager if needed

```bash
# Check latest supported version
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm search repo jetstack/cert-manager --versions

# Upgrade to compatible version (example: 1.14.x for K8s 1.32)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.4 \
  --set installCRDs=true
```

### Restore webhook configuration

After cert-manager is upgraded and healthy:

```bash
# If you used Option 2 (patch), restore original failurePolicy
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Fail"}]'

# If you used Option 3 (delete), the webhook will be recreated by the upgrade
# No action needed - verify it exists:
kubectl get validatingwebhookconfigurations cert-manager-webhook
```

## Validation

```bash
# Verify cert-manager is healthy
kubectl get pods -n cert-manager
kubectl get certificates -A
kubectl get certificaterequests -A

# Test webhook is working properly
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webhook-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: webhook-test
  template:
    metadata:
      labels:
        app: webhook-test
    spec:
      containers:
      - name: nginx
        image: nginx
EOF

# Clean up test
kubectl delete deployment webhook-test
```

## Prevention for Future Upgrades

Add to your pre-upgrade checklist:
- [ ] Check cert-manager version compatibility with target Kubernetes version
- [ ] Test cert-manager in staging environment with target GKE version first
- [ ] Have webhook bypass procedures documented
- [ ] Monitor cert-manager logs during upgrades

The cert-manager team maintains a [Kubernetes version compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/) - always verify before GKE control plane upgrades.
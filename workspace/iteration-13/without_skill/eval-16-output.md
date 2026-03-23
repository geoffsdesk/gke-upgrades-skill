This is a common issue after Kubernetes upgrades due to API version deprecations or webhook compatibility problems. Here's how to urgently resolve this:

## Immediate Emergency Fix

**Option 1: Temporarily disable the webhook**
```bash
# Find the mutating/validating webhook
kubectl get mutatingwebhookconfiguration
kubectl get validatingwebhookconfiguration

# Temporarily disable cert-manager webhooks
kubectl patch validatingwebhookconfiguration cert-manager-webhook --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/admissionReviewVersions", "value": ["v1", "v1beta1"]}]'

# Or delete temporarily (nuclear option)
kubectl delete validatingwebhookconfiguration cert-manager-webhook
```

## Quick Diagnosis

**Check webhook status:**
```bash
# Check cert-manager pods
kubectl get pods -n cert-manager

# Check webhook service and endpoints
kubectl get svc,endpoints -n cert-manager

# Check webhook configuration
kubectl describe validatingwebhookconfiguration cert-manager-webhook
```

**Check the actual error:**
```bash
# Try creating a test pod to see exact error
kubectl run test-pod --image=nginx --dry-run=server
```

## Systematic Fix

**Step 1: Update cert-manager**
```bash
# Check current version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest compatible version
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.1/cert-manager.yaml

# Or use Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager -n cert-manager
```

**Step 2: Fix webhook configuration if needed**
```bash
# Ensure webhook uses both v1 and v1beta1 API versions
kubectl patch validatingwebhookconfiguration cert-manager-webhook --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/admissionReviewVersions", "value": ["v1", "v1beta1"]}]'
```

**Step 3: Restart cert-manager components**
```bash
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager
```

## Verification

```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it -- echo "success"

# Check webhook is responding
kubectl get validatingwebhookconfiguration cert-manager-webhook -o yaml | grep -A5 clientConfig

# Verify cert-manager functionality
kubectl get certificates,certificaterequests -A
```

## Prevention for Future Upgrades

1. **Pre-upgrade checks:**
```bash
# Check webhook compatibility before upgrading
kubectl get validatingwebhookconfiguration -o yaml | grep admissionReviewVersions
```

2. **Upgrade process:**
- Always upgrade operators/webhooks before or immediately after K8s control plane
- Test in staging environment first
- Have rollback plan ready

## If cert-manager upgrade doesn't work:

**Last resort - bypass webhook temporarily:**
```bash
# Add this annotation to bypass webhook validation
kubectl annotate namespace default cert-manager.io/disable-validation="true"

# Or create pods with --validate=false (dangerous)
kubectl apply --validate=false -f your-pod.yaml
```

Start with updating cert-manager first - this resolves 90% of these issues. The k8s 1.32 upgrade likely deprecated some API versions that the old cert-manager webhook was using.
This is a common issue when upgrading Kubernetes versions - the cert-manager webhook may be incompatible with K8s 1.32 or its certificates may have expired. Here's how to fix it urgently:

## Immediate Fix (Emergency)

**Option 1: Temporarily disable the webhook**
```bash
# Find the validating webhook
kubectl get validatingadmissionwebhooks | grep cert-manager

# Disable it temporarily
kubectl delete validatingadmissionwebhook cert-manager-webhook

# Also check for mutating webhooks
kubectl get mutatingadmissionwebhooks | grep cert-manager
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

## Proper Fix

**Step 1: Check cert-manager version compatibility**
```bash
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

**Step 2: Upgrade cert-manager to a 1.32-compatible version**
```bash
# Check current version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Upgrade to latest (check cert-manager docs for 1.32 compatibility)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

**Step 3: If webhook certificates are the issue**
```bash
# Delete webhook certificates to force recreation
kubectl delete secret -n cert-manager cert-manager-webhook-ca
kubectl delete secret -n cert-manager cert-manager-webhook-tls

# Restart cert-manager
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager
```

**Step 4: Wait for webhook to be ready**
```bash
kubectl wait --for=condition=available deployment/cert-manager-webhook -n cert-manager --timeout=300s
```

**Step 5: Verify the fix**
```bash
# Test webhook is working
kubectl auth can-i create certificates.cert-manager.io

# Try creating a test pod
kubectl run test-pod --image=nginx --rm -it -- echo "success"
```

## Prevention for Future Upgrades

1. **Check compatibility matrices** before upgrading
2. **Upgrade operators first** in a staging environment
3. **Have webhook bypass procedures** documented
4. **Monitor webhook certificate expiry**

If you're still having issues, please share:
- Current cert-manager version
- Webhook error logs
- Output of `kubectl get validatingadmissionwebhooks`

Would you like me to help with any specific step?
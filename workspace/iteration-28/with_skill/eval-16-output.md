This is a common post-upgrade issue where admission webhooks fail after control plane upgrades. Here's the immediate fix:

## Immediate Mitigation (Temporary)

First, identify and temporarily disable the problematic webhook:

```bash
# Find cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily set failure policy to Ignore (allows pod creation to bypass the webhook)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's a mutating webhook too:
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

Test pod creation immediately:
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation works"
```

## Permanent Fix

The root cause is cert-manager's webhook certificates being incompatible with the new API server version. Fix this by upgrading cert-manager:

```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'

# Upgrade cert-manager to a version supporting K8s 1.32
# (Check cert-manager docs for 1.32 compatibility - typically v1.13+ supports K8s 1.32)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.0 \
  --set installCRDs=true

# Wait for rollout
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

Verify the fix:
```bash
# Test pod creation still works
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Still working"

# Check webhook is healthy
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

## Restore Security

Once cert-manager is upgraded and working, revert the temporary bypass:

```bash
# Restore failure policy to Fail (secure default)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# Test one final time
kubectl run test-pod-3 --image=nginx --rm -it --restart=Never -- echo "Final test"
```

## Prevention for Future Upgrades

Before your next control plane upgrade:
1. Check cert-manager compatibility matrix with target K8s version
2. Upgrade cert-manager BEFORE upgrading GKE control plane
3. Consider this pattern for all admission webhook operators (policy controllers, service mesh, etc.)

This should restore pod creation within minutes. The temporary bypass is safe for short periods but don't leave it in place long-term as it disables certificate validation.
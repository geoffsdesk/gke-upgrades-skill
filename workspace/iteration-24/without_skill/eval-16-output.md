This is a common issue when upgrading Kubernetes versions - the cert-manager webhook may be incompatible with K8s 1.32 or its certificates may have expired. Here's how to fix it urgently:

## Immediate Fix Options (Choose One)

### Option 1: Temporarily Disable the Webhook (Fastest)
```bash
# Identify the failing webhook
kubectl get validatingadmissionwebhooks | grep cert-manager
kubectl get mutatingadmissionwebhooks | grep cert-manager

# Temporarily disable it
kubectl delete validatingadmissionwebhook cert-manager-webhook
kubectl delete mutatingadmissionwebhook cert-manager-webhook
```

### Option 2: Fix Certificate Issues
```bash
# Check webhook certificate status
kubectl get secrets -n cert-manager | grep webhook
kubectl describe secret cert-manager-webhook-ca -n cert-manager

# Delete webhook certificates to force regeneration
kubectl delete secret cert-manager-webhook-ca -n cert-manager
kubectl delete secret cert-manager-webhook-tls -n cert-manager

# Restart cert-manager pods
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager -n cert-manager
```

## Permanent Solution

### 1. Upgrade cert-manager
```bash
# Check current version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest version compatible with K8s 1.32
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.1 \
  --set crds.enabled=true
```

### 2. If using kubectl apply:
```bash
# Apply latest CRDs
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.1/cert-manager.crds.yaml

# Apply latest manifests
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.1/cert-manager.yaml
```

## Verification Steps

```bash
# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=300s

# Verify webhook is working
kubectl get validatingadmissionwebhooks cert-manager-webhook -o yaml | grep caBundle

# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "success"
```

## Prevention for Future Upgrades

1. **Check compatibility matrix** before upgrading
2. **Test in staging** with the same K8s version
3. **Have webhook bypass procedures** documented
4. **Monitor admission webhook metrics**

## If Still Failing

```bash
# Check webhook logs
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Check API server logs for webhook failures
# Look for webhook timeout or connection errors

# Verify network policies aren't blocking webhook traffic
kubectl get networkpolicies -A
```

**Recommended approach**: Start with Option 1 to immediately restore workload creation, then implement the permanent solution during your next maintenance window.

Would you like me to help you with any specific step or troubleshoot further if these solutions don't work?
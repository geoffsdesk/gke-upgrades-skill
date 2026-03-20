This is a common issue when upgrading across Kubernetes minor versions - admission webhooks may not be compatible with the new control plane version. Here's the urgent fix:

## Immediate Fix (Restore Service)

**1. First, check which webhook is failing:**
```bash
# Look for cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check recent events for webhook failures
kubectl get events -A --sort-by='.lastTimestamp' | grep -i webhook | tail -10
```

**2. Temporarily disable the problematic webhook:**
```bash
# If it's the cert-manager webhook causing issues, temporarily disable it
kubectl delete validatingwebhookconfigurations cert-manager-webhook

# Or if it's a mutating webhook:
kubectl delete mutatingwebhookconfigurations cert-manager-webhook
```

**3. Verify pods can now be created:**
```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Root Cause Fix

**1. Upgrade cert-manager to a version compatible with K8s 1.30:**
```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o yaml | grep image: | grep cert-manager

# Upgrade to latest compatible version (check cert-manager docs for K8s 1.30 compatibility)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml

# Or if using Helm:
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.14.4
```

**2. Verify cert-manager is healthy:**
```bash
kubectl get pods -n cert-manager
kubectl get validatingwebhookconfigurations cert-manager-webhook
kubectl describe validatingwebhookconfigurations cert-manager-webhook
```

**3. Test certificate functionality:**
```bash
# Create a test certificate to ensure cert-manager is working
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-cert
  namespace: default
spec:
  secretName: test-cert-tls
  issuerRef:
    name: your-issuer-name  # Replace with your actual issuer
    kind: ClusterIssuer
  dnsNames:
  - test.example.com
EOF

kubectl describe certificate test-cert
```

## Prevention for Future Upgrades

**Add this to your pre-upgrade checklist:**

- [ ] Check cert-manager compatibility matrix with target K8s version
- [ ] Test cert-manager in staging environment with target GKE version
- [ ] Have cert-manager upgrade plan ready before control plane upgrade
- [ ] Consider upgrading cert-manager BEFORE the GKE control plane upgrade

## If cert-manager upgrade doesn't resolve it

**1. Check webhook endpoint health:**
```bash
kubectl get endpoints -n cert-manager cert-manager-webhook
kubectl describe validatingwebhookconfigurations cert-manager-webhook | grep -A 5 "Client Config"
```

**2. Restart cert-manager pods:**
```bash
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager
```

**3. Check cert-manager logs:**
```bash
kubectl logs -n cert-manager -l app=cert-manager --tail=100
kubectl logs -n cert-manager -l app=webhook --tail=100
```

The webhook deletion should restore immediate functionality, but make sure to upgrade cert-manager to maintain certificate management capabilities. Most cert-manager compatibility issues with K8s 1.30 are resolved in cert-manager v1.13+ versions.
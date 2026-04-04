This is a common post-upgrade issue. Cert-manager's admission webhook likely hasn't updated its certificates for the new Kubernetes API server version, causing validation failures.

## Immediate Fix (Emergency Mitigation)

**1. Temporarily disable the failing webhook:**
```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch it to ignore failures temporarily
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**2. Test pod creation works:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation test"
```

## Permanent Fix

**1. Check cert-manager version compatibility:**
```bash
# Current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it supports Kubernetes 1.32
```

**2. Upgrade cert-manager to a version supporting K8s 1.32:**
```bash
# Example with Helm (adjust version as needed)
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.0  # Use latest version that supports K8s 1.32
```

**3. Verify webhook is healthy:**
```bash
kubectl get pods -n cert-manager
kubectl logs deployment/cert-manager-webhook -n cert-manager

# Test certificate creation
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-cert
  namespace: default
spec:
  secretName: test-cert-secret
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  commonName: test.example.com
EOF
```

**4. Restore webhook security:**
```bash
# Remove the temporary failurePolicy override
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Root Cause Prevention

For future upgrades, **before** upgrading the control plane:

1. **Check operator compatibility matrix** - verify cert-manager version supports target K8s version
2. **Test in staging** - upgrade a staging cluster first and validate all webhooks
3. **Upgrade operators first** - update cert-manager, Istio, policy controllers before K8s upgrade

## If Cert-Manager Upgrade Fails

If the cert-manager upgrade itself fails due to webhook issues:

```bash
# Temporarily delete the webhook entirely
kubectl delete validatingwebhookconfigurations cert-manager-webhook

# Upgrade cert-manager
helm upgrade cert-manager jetstack/cert-manager --version v1.15.0

# The webhook will be recreated automatically
```

## Verification

```bash
# Confirm webhook is working
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml

# Test normal pod creation
kubectl run verification-pod --image=nginx --dry-run=server

# Check cert-manager logs for errors
kubectl logs deployment/cert-manager -n cert-manager
kubectl logs deployment/cert-manager-webhook -n cert-manager
```

The temporary `failurePolicy: Ignore` gives you breathing room to upgrade cert-manager properly. This is the fastest path to restore service while maintaining security once the permanent fix is in place.
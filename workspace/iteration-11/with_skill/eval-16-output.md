This is a common issue during GKE upgrades - admission webhooks can break when the Kubernetes API version changes. Here's how to fix it urgently:

## Immediate Fix (Restore Service)

**Option 1: Temporarily disable the webhook (fastest)**
```bash
# List validating webhooks to find cert-manager's webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Temporarily delete the problematic webhook
kubectl delete validatingwebhookconfigurations cert-manager-webhook

# Test pod creation now works
kubectl run test-pod --image=nginx --rm -it -- echo "test"
```

**Option 2: Add failure policy to ignore webhook failures**
```bash
# Edit the webhook configuration
kubectl edit validatingwebhookconfigurations cert-manager-webhook

# Add this to each webhook rule:
# failurePolicy: Ignore  # Instead of Fail
```

## Root Cause Fix

The issue is likely that cert-manager's webhook TLS certificate is invalid for the new Kubernetes API server version, or the webhook service itself is down.

**Check webhook service status:**
```bash
# Verify cert-manager pods are running
kubectl get pods -n cert-manager

# If pods are failing, check logs
kubectl logs -n cert-manager deployment/cert-manager-webhook

# Check webhook service endpoints
kubectl get endpoints -n cert-manager cert-manager-webhook
```

**Upgrade cert-manager to a 1.32-compatible version:**
```bash
# Check current cert-manager version
kubectl get deployment -n cert-manager cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest compatible version (example)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

## Validation

```bash
# Verify webhook is working
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml

# Test certificate creation
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-cert
  namespace: default
spec:
  secretName: test-cert-tls
  issuerRef:
    name: test-issuer
    kind: ClusterIssuer
  commonName: test.example.com
EOF

# Clean up test
kubectl delete certificate test-cert
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```markdown
- [ ] Third-party operators tested against target GKE version
- [ ] Admission webhook compatibility verified
- [ ] Webhook failure policies set to "Ignore" for non-critical validations
- [ ] Cert-manager/other operators upgraded BEFORE control plane upgrade
```

## If cert-manager upgrade doesn't work immediately

```bash
# Restart cert-manager components to refresh certificates
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout restart deployment/cert-manager-cainjector -n cert-manager  
kubectl rollout restart deployment/cert-manager-webhook -n cert-manager

# Wait for rollout to complete
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

The temporary webhook deletion (Option 1) should restore pod creation immediately. Then you can fix cert-manager properly and re-enable the webhook validation.
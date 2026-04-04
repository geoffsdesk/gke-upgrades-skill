This is a common post-upgrade issue. The cert-manager webhook likely hasn't updated its certificates for the new Kubernetes 1.32 API server, causing validation failures.

## Immediate Fix (Emergency Mitigation)

**Temporarily disable the failing webhook:**

```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch it to ignore failures temporarily
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test pod creation immediately:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass working"
```

This allows pods to create while you fix the root cause.

## Permanent Fix

**1. Check cert-manager version compatibility:**
```bash
kubectl get pods -n cert-manager
helm list -n cert-manager  # if installed via Helm
```

**2. Upgrade cert-manager to a version supporting Kubernetes 1.32:**
```bash
# Check current and required versions at:
# https://cert-manager.io/docs/installation/supported-releases/

# If using Helm:
helm repo update jetstack
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.0  # or latest compatible version

# If using kubectl/manifests:
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.0/cert-manager.yaml
```

**3. Wait for cert-manager to restart and regenerate certificates:**
```bash
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

**4. Verify webhook is working properly:**
```bash
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml
# Check that certificates are fresh and webhook endpoints are ready

# Test certificate creation
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: test-cert
  namespace: default
spec:
  secretName: test-cert-tls
  dnsNames:
  - test.example.com
  issuerRef:
    name: letsencrypt-staging
    kind: ClusterIssuer
EOF
```

**5. Restore original webhook failure policy:**
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

Add this to your pre-upgrade checklist:

```markdown
- [ ] Verify cert-manager version supports target Kubernetes version
- [ ] Check all admission webhook operators for compatibility
- [ ] Test webhook functionality in staging cluster first
- [ ] Have webhook bypass procedure documented for emergencies
```

## If cert-manager upgrade fails

**Alternative emergency fix - delete the webhook temporarily:**
```bash
kubectl delete validatingwebhookconfigurations cert-manager-webhook
# Pods will create normally
# Reinstall cert-manager completely when ready
```

**Monitor for other webhook issues:**
```bash
kubectl get events -A --field-selector type=Warning | grep webhook
kubectl get mutatingwebhookconfigurations  # Check for other problematic webhooks
```

The key is getting pods creating again immediately with the `failurePolicy: Ignore` patch, then fixing cert-manager properly. This pattern works for any admission webhook compatibility issue post-upgrade.
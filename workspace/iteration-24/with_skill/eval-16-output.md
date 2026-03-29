# Urgent Fix for Cert-Manager Webhook Failures After GKE 1.32 Upgrade

## Immediate Mitigation (Apply Now)

**Step 1: Identify the failing webhook**
```bash
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager
```

**Step 2: Temporarily disable webhook validation** (allows pod creation to resume)
```bash
# For validating webhooks
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# For mutating webhooks (if present)
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Step 3: Verify pod creation works**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Root Cause & Permanent Fix

**The Issue:** Cert-manager's webhook certificates are likely incompatible with the new Kubernetes 1.32 API server. This is common when the cert-manager version predates GKE 1.32 support.

**Step 4: Check current cert-manager version**
```bash
kubectl get pods -n cert-manager -o jsonpath='{.items[0].spec.containers[0].image}'
```

**Step 5: Upgrade cert-manager to 1.32-compatible version**
```bash
# If using Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.13.0  # or latest version supporting K8s 1.32

# If using kubectl manifests
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

**Step 6: Wait for cert-manager pods to restart and regenerate certificates**
```bash
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

**Step 7: Test webhook functionality**
```bash
# Create a test certificate to verify webhook is working
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
  dnsNames:
  - test.example.com
EOF

kubectl describe certificate test-cert
kubectl delete certificate test-cert
```

**Step 8: Restore webhook security (CRITICAL)**
```bash
# Re-enable webhook validation
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

**Pre-upgrade checklist item to add:**
- [ ] Verify cert-manager version supports target Kubernetes version
- [ ] Check [cert-manager Kubernetes compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/)

## If Helm Upgrade Fails

**Alternative approach using kubectl:**
```bash
# Delete old cert-manager (certificates will be preserved)
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/OLD_VERSION/cert-manager.yaml

# Install new version
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

## Monitoring

**Check for similar webhook issues with other operators:**
```bash
kubectl get events -A --field-selector type=Warning | grep webhook
kubectl get pods -A | grep -E "Error|CrashLoopBackOff"
```

The temporary `failurePolicy: Ignore` fix should restore service immediately. The cert-manager upgrade provides the permanent fix. **Do not forget Step 8** — leaving webhooks disabled permanently creates a security risk.
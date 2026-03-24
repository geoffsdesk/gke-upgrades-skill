# Urgent Fix: Admission Webhook Failures After GKE Upgrade

## Immediate Mitigation (Do This First)

**Temporarily disable the failing webhook to restore pod creation:**

```bash
# Find the problematic webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Patch it to ignore failures temporarily
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test pod creation works:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Root Cause & Permanent Fix

**The issue:** cert-manager's webhook certificates weren't updated for the new Kubernetes 1.32 API server, causing validation failures.

**Check cert-manager version compatibility:**
```bash
kubectl get pods -n cert-manager
kubectl describe pod cert-manager-webhook-xxx -n cert-manager | grep Image:
```

**Fix - Upgrade cert-manager to 1.32-compatible version:**
```bash
# Check current version
helm list -n cert-manager

# Upgrade to latest (supports K8s 1.32)
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.0  # or latest stable version

# Wait for rollout
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

**Verify the fix:**
```bash
# Check webhook pods are running
kubectl get pods -n cert-manager

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
    name: letsencrypt-staging
    kind: ClusterIssuer
  dnsNames:
  - test.example.com
EOF

# Clean up test
kubectl delete certificate test-cert
```

## Restore Webhook Security

**Once cert-manager is upgraded, restore the webhook's failure policy:**
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

**Pre-upgrade checklist addition:**
- [ ] Verify cert-manager version supports target Kubernetes version
- [ ] Check [cert-manager compatibility matrix](https://cert-manager.io/docs/installation/supported-releases/)
- [ ] Test webhook functionality in staging cluster first

**If you use GitOps/Helm:**
Update your cert-manager version in your GitOps repo or CI/CD pipeline to prevent this issue on other clusters.

---

**Estimated recovery time:** 5-10 minutes for immediate mitigation, 15-20 minutes for permanent fix.

**This pattern applies to other webhook operators too** - Istio, Gatekeeper, custom admission controllers. Always check operator compatibility with your target Kubernetes version before upgrading the control plane.
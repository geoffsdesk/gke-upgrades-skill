This is a common post-upgrade issue where admission webhooks fail to work with the new Kubernetes API version. Here's the immediate fix followed by the permanent solution:

## Immediate Mitigation (Temporary Fix)

**Identify the failing webhook:**
```bash
# Find cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check recent events for webhook failures
kubectl get events -A --field-selector type=Warning | grep webhook
```

**Temporarily bypass the webhook to restore pod creation:**
```bash
# For validating webhook (most common with cert-manager)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# If there's also a mutating webhook
kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Test pod creation works:**
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypass successful"
```

## Permanent Fix

**1. Check cert-manager version compatibility:**
```bash
# Current cert-manager version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check if it supports Kubernetes 1.32
# Consult: https://cert-manager.io/docs/installation/supported-releases/
```

**2. Upgrade cert-manager to a 1.32-compatible version:**
```bash
# If installed via Helm
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --version v1.15.0 \
  --namespace cert-manager \
  --set installCRDs=true

# If installed via kubectl/manifests
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.0/cert-manager.yaml
```

**3. Wait for cert-manager to restart and verify health:**
```bash
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deployment/cert-manager-webhook
```

**4. Restore webhook failure policy to "Fail" (secure):**
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

**5. Final verification:**
```bash
# Test certificate issuance works
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Full webhook functionality restored"
```

## Prevention for Future Upgrades

**Pre-upgrade checklist addition:**
- [ ] Verify all admission webhook operators support target Kubernetes version
- [ ] Check cert-manager, policy controllers, service mesh operators compatibility
- [ ] Test webhook functionality in staging cluster with target version first

**Key insight:** GKE 1.31→1.32 changed some admission controller behavior. Cert-manager versions prior to v1.13 don't fully support K8s 1.32's webhook validation changes. Always upgrade third-party operators BEFORE or immediately after control plane upgrades.

The temporary `failurePolicy: Ignore` gets your workloads running again, but it bypasses certificate validation entirely. The permanent fix ensures proper certificate management while maintaining security.
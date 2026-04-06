This is a common post-upgrade issue where cert-manager's webhook certificates aren't compatible with the new API server version. Here's the urgent fix:

## Immediate Mitigation (Temporary - 5 minutes)

First, temporarily disable the failing webhook to restore pod creation:

```bash
# Find the cert-manager webhook
kubectl get validatingwebhookconfigurations | grep cert-manager

# Temporarily set it to ignore failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

Test pod creation works:
```bash
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"
```

## Permanent Fix (15-30 minutes)

Now fix the root cause by upgrading cert-manager to a version that supports Kubernetes 1.32:

```bash
# Check current cert-manager version
kubectl get pods -n cert-manager -o wide

# Find compatible version (cert-manager 1.13+ supports K8s 1.32)
helm repo update jetstack
helm search repo jetstack/cert-manager --versions

# Upgrade cert-manager
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.15.3 \
  --set installCRDs=true
```

Wait for cert-manager pods to be ready:
```bash
kubectl get pods -n cert-manager
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=300s
```

## Restore Normal Operation

Re-enable strict webhook validation:
```bash
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

Verify everything works:
```bash
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
    name: your-issuer
    kind: ClusterIssuer
  dnsNames:
  - test.example.com
EOF

# Test pod creation still works
kubectl run test-pod-2 --image=nginx --rm -it --restart=Never -- echo "Final test"
```

## Prevention for Next Time

Before future control plane upgrades, check operator compatibility:

```bash
# Check all admission webhooks
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Verify each operator supports the target K8s version before upgrading
```

**Key lesson**: Always verify third-party operator compatibility with the target Kubernetes version before upgrading the control plane. Cert-manager, Istio, and other operators with admission webhooks are common culprits for this type of post-upgrade failure.

Your workloads should be creating pods normally within 5-10 minutes of applying the temporary fix, and the permanent solution ensures this won't happen again.
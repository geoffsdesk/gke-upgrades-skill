# Urgent Webhook Fix for Control Plane 1.31→1.32 Upgrade

## Immediate Diagnosis

The cert-manager webhook is likely incompatible with Kubernetes 1.32. First, confirm the webhook is the root cause:

```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Check recent pod creation failures
kubectl get events -A --field-selector reason=FailedCreate | grep -i webhook
kubectl get events -A --sort-by='.firstTimestamp' | tail -20
```

## Immediate Fix Options (in priority order)

### Option 1: Temporarily disable the webhook (fastest)
```bash
# Backup current webhook config
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml > cert-manager-webhook-backup.yaml

# Add failure policy to ignore webhook failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'

# Or completely remove the webhook temporarily
kubectl delete validatingwebhookconfigurations cert-manager-webhook
```

### Option 2: Upgrade cert-manager (if compatible version exists)
```bash
# Check your current cert-manager version
kubectl get deployment -n cert-manager cert-manager -o yaml | grep image:

# Upgrade to 1.32-compatible version (check cert-manager docs for latest)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
```

### Option 3: Scale down cert-manager temporarily
```bash
# This removes the webhook entirely
kubectl scale deployment cert-manager-webhook -n cert-manager --replicas=0
kubectl scale deployment cert-manager -n cert-manager --replicas=0
```

## Verify Fix Applied

```bash
# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Pod creation working"

# Check no pending pods due to webhook
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedCreate | grep -i webhook
```

## After Pods are Creating Again

1. **If you disabled the webhook**: Research the correct cert-manager version for K8s 1.32 and upgrade properly
2. **If you scaled down cert-manager**: New certificates won't be issued until you scale back up
3. **Check cert-manager compatibility matrix** at: https://cert-manager.io/docs/installation/supported-releases/

## Restore Webhook (once compatible version is installed)

```bash
# If you patched the failure policy:
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='merge' \
  -p='{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'

# If you deleted it entirely:
kubectl apply -f cert-manager-webhook-backup.yaml

# If you scaled down:
kubectl scale deployment cert-manager -n cert-manager --replicas=1
kubectl scale deployment cert-manager-webhook -n cert-manager --replicas=1
```

## Prevention for Next Time

```bash
# Before control plane upgrades, check webhook compatibility
kubectl get validatingwebhookconfigurations -o custom-columns="NAME:.metadata.name,WEBHOOKS:.webhooks[*].name"
kubectl get mutatingwebhookconfigurations -o custom-columns="NAME:.metadata.name,WEBHOOKS:.webhooks[*].name"
```

**Most common webhook culprits with K8s version sensitivity:**
- cert-manager (check compatibility matrix)
- Istio/Linkerd service mesh
- Policy engines (OPA Gatekeeper, Kyverno)
- Custom admission controllers

The `failurePolicy: Ignore` patch is the fastest fix but reduces security - restore proper webhook function as soon as possible.
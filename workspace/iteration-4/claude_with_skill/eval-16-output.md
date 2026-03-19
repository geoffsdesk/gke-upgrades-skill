# Urgent Fix: Cert-Manager Admission Webhook Blocking Pod Creation

This is a common issue after control plane upgrades where the admission webhook configuration becomes incompatible with the new Kubernetes version.

## Immediate Fix (Choose One)

### Option 1: Temporarily Disable the Webhook (Fastest)
```bash
# List cert-manager webhooks
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager

# Temporarily delete the problematic webhook
kubectl delete validatingwebhookconfigurations cert-manager-webhook
kubectl delete mutatingwebhookconfigurations cert-manager-webhook

# Test pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Webhook bypassed"
```

### Option 2: Add Failure Policy (Safer)
```bash
# Patch webhook to ignore failures
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'

kubectl patch mutatingwebhookconfigurations cert-manager-webhook \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'
```

## Permanent Fix: Upgrade Cert-Manager

Check your cert-manager version and upgrade to one compatible with Kubernetes 1.30:

```bash
# Check current version
kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.template.spec.containers[0].image}'

# Upgrade to latest (adjust version as needed)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
```

## Validation

```bash
# Verify pods can be created
kubectl get pods -A | grep -E "Pending|ContainerCreating"

# Check webhook is working properly
kubectl get validatingwebhookconfigurations cert-manager-webhook -o yaml | grep failurePolicy

# Test certificate issuance still works
kubectl get certificates -A
kubectl get certificaterequests -A
```

## Root Cause

Cert-manager's admission webhook likely has:
- Incompatible API versions referenced in webhook configuration
- Certificate validation issues with the new control plane
- Timeout issues due to API server changes in 1.30

**Immediate action:** Use Option 1 to unblock pod creation now, then upgrade cert-manager during your next maintenance window.

**Time to resolution:** 2-5 minutes with Option 1, 10-15 minutes with Option 2 + upgrade.
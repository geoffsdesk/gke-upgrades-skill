This is a classic post-upgrade issue. When the GKE control plane is upgraded, it can lose connectivity to the webhook pods, or the webhook itself (in this case, `cert-manager`) may be incompatible with the new Kubernetes 1.32 API structures. Because the webhook's `failurePolicy` is likely set to `Fail`, the API server is aggressively rejecting any new pod creations that it cannot validate.

Here is the immediate "break-glass" fix to unblock your cluster, followed by the permanent solution.

### Phase 1: Urgent Mitigation (Unblock Pod Creation)

To immediately allow workloads to schedule, you need to temporarily remove the `cert-manager` webhook configurations. This will bypass `cert-manager`'s validation checks so your standard pods can start. 

**1. Identify the blocking webhooks:**
```bash
kubectl get validatingwebhookconfigurations | grep cert-manager
kubectl get mutatingwebhookconfigurations | grep cert-manager
```
*(Typically, this is named `cert-manager-webhook`)*

**2. Delete the webhooks to restore cluster function:**
```bash
# Replace 'cert-manager-webhook' if your output above showed a different name
kubectl delete validatingwebhookconfiguration cert-manager-webhook
kubectl delete mutatingwebhookconfiguration cert-manager-webhook
```

**3. Verify pod creation is unblocked:**
```bash
# Your pending/failing pods should now start creating
kubectl get pods -A | grep -E "ContainerCreating|Pending"
```

*Note: Deleting these webhooks means `cert-manager` won't validate new Certificate or Issuer resources momentarily, but it safely unblocks your core application workloads. The webhooks will be automatically recreated when you fix/upgrade cert-manager.*

---

### Phase 2: Permanent Fix (Resolve Root Cause)

The root cause is almost certainly that your current version of `cert-manager` is not fully compatible with Kubernetes 1.32, or its webhook pod failed to properly restart and sync its TLS certificates with the newly upgraded 1.32 API server.

**1. Check the cert-manager webhook pod status:**
```bash
kubectl get pods -n cert-manager | grep webhook
```
If it is in `CrashLoopBackOff` or `Pending`, it confirms the operator is failing against the new control plane.

**2. Upgrade cert-manager to a 1.32-compatible version:**
You must upgrade `cert-manager` to a release that supports K8s 1.32 (typically v1.16+ or the latest stable release). 

If you installed via Helm:
```bash
# Update repo
helm repo update

# Upgrade cert-manager (adjust version and namespace as needed)
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.2 \
  --set crds.enabled=true
```

If you installed via manifests:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

**3. Verify the webhooks are restored and healthy:**
Once the upgrade completes, `cert-manager` will automatically recreate the webhook configurations you deleted in Phase 1.
```bash
# Verify webhook configs exist again
kubectl get validatingwebhookconfigurations | grep cert-manager

# Verify cert-manager pods are running
kubectl get pods -n cert-manager
```

### 💡 For Your Next Upgrade (Pre-Upgrade Checklist)
To prevent this in the future, add these steps to your Standard GKE Pre-Upgrade Checklist:
1. **Check Third-Party Operators:** Always verify that critical operators (like `cert-manager`, `ingress-nginx`, or security agents) are strictly compatible with the target Kubernetes version *before* triggering the GKE control plane upgrade.
2. **Review Webhook Failure Policies:** Consider changing non-critical webhook `failurePolicy` from `Fail` to `Ignore` prior to an upgrade, or ensure you have a runbook ready to bypass them if they block the cluster.
# GKE Node Pool Upgrade Troubleshooting Guide
## Stuck Upgrade - Pods Not Draining

**Scenario:** Standard cluster in `us-east1`, upgrading nodes from Kubernetes 1.29 to 1.30, 3 of 12 nodes completed, stuck for 2+ hours with remaining pods not draining.

---

## Immediate Diagnosis Steps

### 1. Check Pod Disruption Budgets (PDBs)
PDBs are the most common cause of stuck drains. They prevent pods from being evicted if it would violate the budget.

```bash
# List all PDBs and their allowed disruptions
kubectl get pdb -A -o wide

# Look for any PDBs with ALLOWED DISRUPTIONS = 0
kubectl get pdb -A -o wide | grep ' 0 '

# Get detailed info on problematic PDBs
kubectl describe pdb <pdb-name> -n <namespace>
```

**What to look for:**
- ALLOWED DISRUPTIONS column = 0 → pods cannot be evicted
- MAX DISRUPTIONS set too conservatively (e.g., 0 pods allowed)
- Check which pods are protected by that PDB

### 2. Check for Eviction Failures
```bash
# Find eviction failures in cluster events
kubectl get events -A --field-selector reason=EvictionFailed

# Check node drain status
kubectl describe node <node-name> | grep -A 5 "Taints"

# Check which pods are preventing drain
kubectl get pods -A --field-selector=status.phase=Running -o wide | grep <node-name>
```

### 3. Check Termination Grace Period
High termination grace periods force Kubernetes to wait longer for graceful shutdown, blocking the drain.

```bash
# Find pods with long termination periods
kubectl get pods -A -o json | jq '.items[] | select(.spec.terminationGracePeriodSeconds > 60) | {name:.metadata.name, namespace:.metadata.namespace, grace:.spec.terminationGracePeriodSeconds}'

# Check specific pod details
kubectl get pod <pod-name> -n <namespace> -o yaml | grep terminationGracePeriodSeconds
```

**Context:** GKE waits up to 1 hour for pod eviction. A 5-10 minute grace period × multiple pods can cause significant delays.

### 4. Check for Extended Duration Pods
In Autopilot (not Standard), GKE skips evicting long-running pods for up to 7 days. Verify this isn't affecting you.

```bash
# Check pod creation times - look for pods running for days
kubectl get pods -A -o wide --sort-by=.metadata.creationTimestamp
```

### 5. Check Persistent Volume Attachments
Pods with PVs attached take longer to drain due to volume lifecycle management.

```bash
# Find pods with PVs
kubectl get pods -A -o json | jq '.items[] | select(.spec.volumes[]?.persistentVolumeClaim != null) | {name:.metadata.name, namespace:.metadata.namespace}'

# Check PV status
kubectl get pv -o wide
kubectl get pvc -A -o wide
```

### 6. Monitor the Upgrade Process
```bash
# Watch node status in real-time
watch kubectl get nodes -o wide

# Check GKE upgrade progress (via gcloud)
gcloud container node-pools update <pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1-b \  # or your zone
  --no-enable-autoupgrade

# View node pool details
gcloud container node-pools describe <pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1-b
```

---

## Common Root Causes & Fixes

### Issue 1: Restrictive Pod Disruption Budgets
**Symptom:** `kubectl get pdb` shows ALLOWED DISRUPTIONS = 0

**Fix Options:**

**Option A: Temporarily Relax PDB (Recommended for stuck upgrades)**
```bash
# Edit the PDB to allow disruptions
kubectl patch pdb <pdb-name> -n <namespace> --type merge \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Or edit directly
kubectl edit pdb <pdb-name> -n <namespace>
# Change: minAvailable: 1 → maxUnavailable: 100%
```

**Option B: Adjust unhealthy pod eviction policy**
```bash
# Add this to your PDB to allow eviction of unhealthy pods
kubectl patch pdb <pdb-name> -n <namespace> --type merge \
  -p '{"spec":{"unhealthyPodEvictionPolicy":"AlwaysAllow"}}'
```

### Issue 2: Long Termination Grace Periods
**Symptom:** Pods have `terminationGracePeriodSeconds: 300+`

**Fix:**
```bash
# Patch the deployment/statefulset to reduce grace period
kubectl patch deployment <deployment-name> -n <namespace> --type merge \
  -p '{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":30}}}}'

# For statefulsets
kubectl patch statefulset <statefulset-name> -n <namespace> --type merge \
  -p '{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":30}}}}'
```

### Issue 3: Persistent Volumes Blocking Drain
**Symptom:** Pods with PVs take very long to detach

**Investigation:**
```bash
# Check if PV detach is stuck
kubectl get pvc -A -o wide
gcloud compute disks list  # Check if disks are in use

# Check PV status
kubectl describe pv <pv-name>
```

**Fix (if safe for your workload):**
- Migrate stateful workloads to nodes that are already upgraded
- Or delete/migrate PVCs if they're no longer needed
- Check if node has proper permissions to detach volumes

---

## Force Drain as Last Resort

**Only use if troubleshooting confirms pods are stuck due to non-critical workloads.**

```bash
# Cordon the node (prevent new pods from scheduling)
kubectl cordon <node-name>

# Drain with ignoring daemonsets and local storage
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --timeout=5m

# Or use --disable-eviction to bypass PDB checks (nuclear option)
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --disable-eviction \
  --force \
  --timeout=5m
```

**After drain completes:**
```bash
# Resume the upgrade via GKE
gcloud container node-pools update <pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1-b
```

---

## Recommended Upgrade Strategies for Future

### 1. Pre-Upgrade Validation
```bash
# List all PDBs before upgrading
kubectl get pdb -A -o wide

# Identify risky PDB configurations
kubectl get pdb -A -o yaml | grep -E "(minAvailable|maxUnavailable)"
```

### 2. Configure Surge Upgrade
GKE's surge upgrade runs multiple nodes in parallel, reducing total upgrade time and pressure on remaining nodes.

```bash
# Update node pool with surge strategy (gcloud)
gcloud container node-pools update <pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1-b \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 1
```

### 3. Set Reasonable Defaults for PDBs
```yaml
# Example PDB that allows controlled disruptions
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: safe-pdb
  namespace: default
spec:
  maxUnavailable: 1  # Allow 1 pod disruption at a time
  selector:
    matchLabels:
      app: my-app
  unhealthyPodEvictionPolicy: AlwaysAllow  # Allow eviction of stuck pods
```

### 4. Graceful Termination Settings
```yaml
# Set reasonable grace period in deployments
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 30  # Adjust based on app needs
```

---

## Escalation Checklist

If the above steps don't resolve the issue:

- [ ] Verify node pool is in a valid state (check GKE console)
- [ ] Check GKE cluster system health (control plane status)
- [ ] Review GKE cluster events for system-level issues
- [ ] Check if nodes are experiencing disk/memory pressure
- [ ] Verify IAM permissions allow node termination
- [ ] Contact Google Cloud Support with:
  - Cluster name, zone, node pool name
  - Upgrade start time and current status
  - Output of `kubectl get nodes -o wide`
  - Output of `kubectl get pdb -A -o wide`
  - Output of `kubectl get events -A --sort-by='.lastTimestamp'`

---

## Summary

**Quick Fix Priority:**
1. **Check PDBs first** - Most common culprit: `kubectl get pdb -A -o wide | grep ' 0 '`
2. **Relax restrictive PDB** - Patch with `maxUnavailable: 100%` temporarily
3. **Check termination grace periods** - Reduce if > 60 seconds
4. **Monitor PV detachment** - If applicable to your workloads
5. **Force drain as last resort** - Only after validating safety

After fix is applied, the remaining 9 nodes should resume draining and upgrading normally.

---

## References

- [GKE Troubleshoot Cluster Upgrades](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades)
- [GKE Node Upgrade Strategies](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies)
- [Kubernetes Pod Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Pod Disruption Budget Configuration Guide](https://oneuptime.com/blog/post/2026-02-17-how-to-configure-pod-disruption-budgets-in-gke-to-maintain-availability-during-upgrades/view)
- [Kubernetes Node Drain Best Practices](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)

# GKE Spot VM Node Pool Upgrade Considerations

## Overview
Spot VMs have unique characteristics that actually make upgrades **lower risk** than on-demand instances, but require different upgrade strategies.

## Key Spot VM Upgrade Characteristics

### 1. Workload Tolerance
- **Spot workloads are preemption-tolerant by design** — they already handle sudden interruption
- Upgrade risk is inherently lower since applications must tolerate instance loss
- Standard surge upgrade concerns (pod restart during drain) are less critical

### 2. Recommended Surge Settings

**For Spot node pools:**
```bash
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 1
```

**Rationale:**
- **Higher maxSurge (5% of pool size)** vs typical 2-3% for on-demand
- **Allow some unavailability (1-2 nodes)** since workloads tolerate interruption
- Faster upgrade completion reduces exposure to preemption during upgrade window

### 3. Upgrade Sequencing Strategy

**Upgrade spot pools FIRST, then on-demand pools:**
```bash
# Phase 1: Upgrade spot pools (lower risk validation)
gcloud container node-pools upgrade spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# Phase 2: After validation, upgrade on-demand pools
gcloud container node-pools upgrade on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Benefits:**
- Spot pools validate your surge/drain settings at lower risk
- Catch any version-specific issues before touching critical on-demand workloads
- Faster feedback loop due to higher surge parallelism

## Mixed Pool Upgrade Plan for 1.31→1.32

### Pre-flight Checklist
```
- [ ] Control plane upgraded to 1.32 first
- [ ] Spot workloads have checkpointing/restart capability
- [ ] PDBs configured (even for spot workloads) to ensure orderly drain
- [ ] Monitor spot pricing during upgrade window (optional - for cost awareness)
```

### Step-by-Step Upgrade

**1. Control Plane (prerequisite):**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx
```

**2. Spot Pool Upgrade (Phase 1):**
```bash
# Configure aggressive surge settings for spot
gcloud container node-pools update spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'
```

**3. Validation (soak period):**
```bash
# Verify spot workloads healthy on 1.32 nodes
kubectl get pods -A -o wide | grep SPOT_NODE_NAMES
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

**4. On-Demand Pool Upgrade (Phase 2):**
```bash
# More conservative settings for on-demand
gcloud container node-pools update on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## Special Considerations

### 1. PDB Configuration
Even for spot workloads, configure PDBs for orderly drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  selector:
    matchLabels:
      app: batch-processing
  maxUnavailable: 25%  # Higher than typical since spot workloads tolerate disruption
```

### 2. Cluster Autoscaler Interaction
- Cluster autoscaler may create new nodes at OLD version during upgrade if it scales up
- Consider pausing autoscaler during upgrade window:
```bash
kubectl scale deployment cluster-autoscaler -n kube-system --replicas=0
# Resume after upgrade: --replicas=1
```

### 3. Cost Monitoring (Optional)
- Surge nodes temporarily increase cost
- Higher maxSurge on spot pools = more temporary instances
- Monitor during upgrade: `gcloud compute instances list --filter="name~'gke-.*'"`

## Troubleshooting Spot-Specific Issues

### Issue: Spot surge nodes get preempted during upgrade
**Symptom:** Upgrade stalls because surge spot nodes are preempted
**Fix:** Retry upgrade - GKE will provision new surge nodes
```bash
# Check for preempted nodes
kubectl get events -A --field-selector reason=Preempted
# GKE automatically retries - no manual intervention needed
```

### Issue: Workloads not draining from old spot nodes
**Symptom:** Pods stay on nodes being drained
**Fix:** Check if workloads properly handle SIGTERM
```bash
kubectl describe pod POD_NAME | grep -A5 "Events:"
# Verify terminationGracePeriodSeconds is appropriate
```

## Summary Recommendations

1. **Upgrade spot pools first** - they're lower risk and validate your settings
2. **Use higher maxSurge** (5% vs 2-3%) on spot pools since workloads tolerate disruption  
3. **Keep PDBs** even for spot workloads to ensure orderly drain
4. **Monitor both phases** - use spot upgrade results to adjust on-demand settings if needed
5. **Consider cluster autoscaler pausing** during upgrade window to avoid mixed-version scaling

This approach leverages spot VM characteristics to reduce overall upgrade risk while ensuring both pool types reach the target version safely.
# GKE Upgrade Plan: Mixed Spot and On-Demand Node Pool

## Executive Summary
Your mixed spot/on-demand node pool upgrade from 1.31→1.32 requires a tailored strategy that leverages spot instances' preemption-tolerance while protecting critical on-demand workloads.

## Key Spot VM Upgrade Considerations

### 1. Spot-First Upgrade Strategy
**Upgrade spot pools BEFORE on-demand pools** — spot workloads are already preemption-tolerant by design, making them ideal for validating your upgrade strategy with lower risk.

```bash
# If using separate pools, upgrade spot pool first:
gcloud container node-pools upgrade SPOT_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

### 2. Aggressive Surge Settings for Spot
Since spot workloads already handle interruption, you can use more aggressive upgrade settings:

**Recommended spot pool settings:**
```bash
gcloud container node-pools update SPOT_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5%  # Higher than typical 2-3%
  --max-unavailable-upgrade 2  # Allow multiple concurrent drains
```

**Conservative on-demand pool settings:**
```bash
gcloud container node-pools update ON_DEMAND_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2  # Conservative for critical workloads
  --max-unavailable-upgrade 0  # Zero-downtime rolling
```

### 3. Mixed Pool Strategy (if single pool with both instance types)
If you have a single node pool containing both spot and on-demand instances:

- Use **moderate surge settings**: `maxSurge=3%, maxUnavailable=1`
- Accept that on-demand workloads may temporarily land on spot nodes during upgrade
- Ensure critical workloads have proper node affinity to prefer on-demand nodes post-upgrade

### 4. PDB Configuration
**Use PDBs even for spot workloads** to ensure orderly drain during upgrade:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 1  # Or 50% for larger deployments
  selector:
    matchLabels:
      workload-type: spot-tolerant
```

This prevents GKE from draining ALL spot replicas simultaneously during upgrade.

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist: Mixed Spot/On-Demand Cluster
- [ ] Cluster: [CLUSTER_NAME] | Mode: Standard | Channel: [CHANNEL]
- [ ] Current version: 1.31.x | Target version: 1.32.x

Spot-Specific Readiness
- [ ] Spot workloads confirmed preemption-tolerant (stateless, checkpointing enabled)
- [ ] Critical workloads identified and configured with on-demand node affinity
- [ ] PDBs configured for spot workloads to prevent simultaneous drain
- [ ] Spot pool surge settings configured (aggressive): maxSurge=5%, maxUnavailable=2
- [ ] On-demand pool surge settings configured (conservative): maxSurge=2%, maxUnavailable=0

Standard Upgrade Readiness
- [ ] 1.32 available in your release channel
- [ ] No deprecated API usage (check GKE deprecation insights)
- [ ] GKE release notes reviewed for 1.31→1.32 breaking changes
- [ ] Third-party operators compatible with 1.32
- [ ] Maintenance window configured for off-peak hours
```

## Upgrade Runbook

### Phase 1: Control Plane
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Spot Node Pool (Lower Risk First)
```bash
# Configure aggressive settings for spot workloads
gcloud container node-pools update SPOT_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'
```

### Phase 3: On-Demand Pool (After Spot Validation)
```bash
# Wait for spot upgrade completion and validate
kubectl get pods -A | grep -v Running | grep -v Completed

# Configure conservative settings for critical workloads
gcloud container node-pools update ON_DEMAND_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ON_DEMAND_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,PREEMPTIBLE:.metadata.labels.cloud\.google\.com/gke-preemptible

# Check workload distribution
kubectl get pods -A -o wide | grep -E "(spot|on-demand)"

# Validate critical workloads landed on appropriate node types
kubectl describe pods -l app=critical-app | grep "Node:"
```

## Key Advantages of This Strategy

1. **Risk Mitigation**: Spot workloads validate the upgrade process before touching critical on-demand workloads
2. **Speed**: Aggressive settings on spot pools reduce total upgrade time
3. **Cost Efficiency**: Spot instances already provide cost savings; faster upgrade reduces disruption window
4. **Validation**: Spot upgrade serves as a production test of your surge settings and PDB configuration

## Warning Signs to Watch

- **Spot workloads failing to reschedule**: May indicate insufficient on-demand capacity for spillover
- **Critical pods landing on spot nodes**: Review node affinity rules
- **Excessive spot preemptions during upgrade**: Consider temporarily reducing maxUnavailable to 1

This strategy leverages spot instances' inherent fault-tolerance to de-risk your upgrade while maintaining careful control over critical on-demand workloads.
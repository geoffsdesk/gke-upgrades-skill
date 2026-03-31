# Spot VM Node Pool Upgrade Considerations

For your Standard cluster upgrade from 1.31 to 1.32 with mixed spot and on-demand node pools, here are the key considerations and recommended approach:

## Spot VM Upgrade Strategy

**Spot instances have unique characteristics that actually make upgrades lower-risk:**

### Recommended Settings for Spot Pools
```bash
# Configure more aggressive surge settings for spot pools
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2
```

**Why more aggressive settings work for spot:**
- Workloads are already **preemption-tolerant** by design
- Higher disruption during upgrades is acceptable since workloads handle spot interruptions
- Faster upgrades reduce total maintenance window

### Upgrade Sequencing Strategy

**Upgrade spot pools FIRST, then on-demand:**
1. **Spot pools** → Lower risk, validates your surge/drain settings
2. **On-demand pools** → After validating the process works

This approach lets you catch any upgrade issues on the more resilient workloads before touching mission-critical on-demand nodes.

## Pre-Upgrade Preparation

### PDB Configuration
```bash
# Still use PDBs even for spot workloads to ensure orderly drain
kubectl get pdb -A -o wide
# Verify ALLOWED DISRUPTIONS > 0 for spot workloads
```

Even though spot workloads tolerate interruption, PDBs ensure controlled drain during upgrades rather than chaotic eviction.

### Workload Validation
- Confirm spot workloads have **checkpoint/resume capability**
- Verify workloads can handle both spot preemption AND upgrade eviction
- Check that critical workloads are on on-demand nodes, not spot

## Upgrade Runbook

### 1. Pre-flight Checks
```bash
# Current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Identify spot vs on-demand pools
gcloud container node-pools describe POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(config.preemptible)"
```

### 2. Control Plan Upgrade First
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32
```

### 3. Spot Pool Upgrade (Lower Risk First)
```bash
# Configure aggressive settings for spot pool
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'
```

### 4. On-Demand Pool Upgrade (After Validation)
```bash
# Conservative settings for on-demand pools
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Key Considerations

### Cost Optimization
- **Spot upgrades are faster** with higher maxSurge → shorter surge node costs
- Schedule during off-peak hours when spot pricing is typically lower
- Monitor surge node costs during upgrade window

### Workload Distribution
- Ensure critical workloads have **node affinity** to on-demand nodes
- Verify batch/fault-tolerant workloads prefer spot nodes
- Check that workloads can handle both spot preemption AND upgrade drain

### Monitoring During Upgrade
```bash
# Watch spot node replacements
kubectl get events -A --field-selector reason=NodeReady,reason=NodeNotReady

# Monitor workload rescheduling
kubectl get pods -A -l preemptible=true -o wide
```

## Troubleshooting Spot-Specific Issues

**Spot capacity unavailable for surge:**
- Reduce maxSurge to 1 if spot surge capacity is limited
- Consider drain-first approach: `maxSurge=0, maxUnavailable=2`

**Workloads not handling upgrade + preemption:**
- Verify applications have proper graceful shutdown
- Check restart policies are set to "Always" for resilient workloads

The key insight is that **spot workloads are inherently more resilient to disruption**, so you can use this to your advantage by upgrading them first and with more aggressive settings to validate your upgrade process before touching on-demand workloads.
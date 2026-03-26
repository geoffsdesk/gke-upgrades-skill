# Spot VM Node Pool Upgrade Plan

## Key Considerations for Spot VM Upgrades

Spot instances have unique characteristics that actually make them **easier** to upgrade than on-demand instances:

### Spot VM Advantages for Upgrades
- **Workloads are preemption-tolerant by design** — your applications already handle interruption gracefully
- **Lower upgrade risk** — since workloads expect sudden termination, upgrade-induced restarts are routine
- **Faster upgrade cadence recommended** — spot pools should be upgraded first to validate settings

### Recommended Upgrade Strategy

**1. Upgrade sequence: Spot pools FIRST, then on-demand pools**
- Spot workloads carry lower risk since they're interruption-tolerant
- Use spot pools to validate your surge/drain settings before touching on-demand pools
- If issues arise during spot pool upgrade, on-demand pools remain unaffected

**2. Surge settings for spot pools (more aggressive than on-demand):**
```bash
# For spot pools - higher parallelism is safe
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \  # Higher than typical 1-2% for on-demand
  --max-unavailable-upgrade 2  # Allow 1-2 nodes to drain simultaneously
```

**3. Conservative settings for on-demand pools:**
```bash
# For on-demand pools - more conservative
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2% \
  --max-unavailable-upgrade 1
```

## Complete Upgrade Runbook

### Pre-flight Checks
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify 1.32 available in your channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Identify spot vs on-demand pools
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE \
  --format="table(name, config.preemptible, instanceGroupUrls[0]:label=INSTANCE_GROUP)"
```

### Step 1: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32-gke.PATCH

# Wait for completion (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Step 2: Upgrade Spot Pool(s) First
```bash
# Configure spot pool surge settings
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32-gke.PATCH

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME -o wide'
```

### Step 3: Validate Spot Pool Success
```bash
# Confirm all spot nodes at 1.32
kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check workload health on spot nodes
kubectl get pods -A -o wide | grep SPOT_NODE_NAME
```

### Step 4: Upgrade On-Demand Pool(s)
```bash
# Configure on-demand pool (more conservative)
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2% \
  --max-unavailable-upgrade 1

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32-gke.PATCH
```

## PDB Considerations for Mixed Pools

Even though spot workloads are preemption-tolerant, **still use PDBs** for orderly drain:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 1  # Or 50% depending on replica count
  selector:
    matchLabels:
      app: your-spot-app
```

**Why PDBs matter for spot workloads:**
- Ensures orderly drain during upgrade (different from random preemption)
- Prevents upgrade from draining too many replicas simultaneously
- Maintains service availability even though workloads tolerate interruption

## Monitoring During Upgrade

```bash
# Watch both pools during upgrade
watch 'echo "=== SPOT POOL ===" && kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME && echo "=== ON-DEMAND POOL ===" && kubectl get nodes -l cloud.google.com/gke-nodepool=ONDEMAND_POOL_NAME'

# Check for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Error"

# Monitor GKE operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

## Expected Timeline

- **Control plane:** 10-15 minutes
- **Spot pool:** Typically 20-30% faster than on-demand due to higher maxSurge
- **On-demand pool:** Standard timing based on pool size and surge settings

## Troubleshooting Spot-Specific Issues

**Issue:** Spot nodes not draining cleanly
**Fix:** Spot workloads should handle SIGTERM gracefully. Check terminationGracePeriodSeconds:
```bash
kubectl get pods -l cloud.google.com/gke-preemptible=true -o json | \
  jq '.items[].spec.terminationGracePeriodSeconds'
```

**Issue:** New spot instances not available during surge
**Fix:** Spot capacity fluctuates. Consider temporary on-demand surge if spot unavailable:
```bash
# Temporarily switch surge to on-demand, then back to spot after upgrade
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # Drain-first approach
```

## Key Takeaway

**Spot VMs are actually ideal for testing upgrade procedures** because the workloads are already hardened against interruption. Use this to your advantage by upgrading spot pools first to validate your overall upgrade strategy before touching business-critical on-demand workloads.
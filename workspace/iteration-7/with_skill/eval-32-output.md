# Large-Scale GKE Upgrade Strategy (3,000 nodes)

## Core Issue Analysis

Your 8-hour Saturday window is insufficient for 3,000 nodes. With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, you're looking at **150+ batches minimum**. Even with aggressive surge settings, this translates to 12-20+ hours for a full cluster upgrade.

## Recommended Multi-Weekend Strategy

### Weekend 1: CPU Pools Only (Lower Risk)
```bash
# Extend maintenance window for CPU pools
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2025-01-11T02:00:00Z \
  --maintenance-window-end 2025-01-11T22:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Aggressive surge settings for CPU pools
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 10 --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 10 --max-unavailable-upgrade 0
```

### Weekend 2: GPU Pools (Higher Risk, Needs Training Coordination)
```bash
# GPU pools: maxUnavailable is the primary lever (surge capacity usually unavailable)
gcloud container node-pools update A100_POOL \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 --max-unavailable-upgrade 3

gcloud container node-pools update H100_POOL \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 --max-unavailable-upgrade 2
```

## Alternative: Skip-Level Node Pool Upgrades

If your control plane is already 2+ versions ahead of nodes, use skip-level upgrades to reduce total upgrade cycles:

```bash
# Instead of 1.29 → 1.30 → 1.31, go directly 1.29 → 1.31
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

This cuts upgrade time in half by eliminating intermediate versions.

## Maintenance Exclusion Strategy for Active Training

Protect running training jobs with targeted exclusions:

```bash
# Block node upgrades during training campaigns, allow CP patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q1-training-campaign" \
  --add-maintenance-exclusion-start-time 2025-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-03-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Pool-Specific Configuration

### CPU Pools (Stateless workloads)
```bash
# High parallelism, fast completion
--max-surge-upgrade 10 --max-unavailable-upgrade 0
```

### GPU Pools (Fixed reservations, no surge capacity)
```bash
# A100/H100 (expensive, limited): Conservative
--max-surge-upgrade 0 --max-unavailable-upgrade 1

# T4/L4 (more available): Moderate parallelism  
--max-surge-upgrade 0 --max-unavailable-upgrade 3
```

## Monitoring Large-Scale Upgrades

```bash
# Track progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status,instanceGroupUrls.len())"'

# Monitor stuck pods during upgrade
kubectl get pods -A | grep -E "Terminating|Pending" | wc -l
```

## Extended Maintenance Windows

For 3,000 nodes, consider 20-hour windows:
- **Friday 10pm - Saturday 6pm** (gives you Sunday buffer)
- **Saturday 2am - Sunday 10pm** (spans weekend)

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2025-01-10T22:00:00Z \
  --maintenance-window-end 2025-01-11T18:00:00Z
```

## Blue-Green Alternative for GPU Pools

If training schedules allow, blue-green eliminates the time constraint:

```bash
# Auto-scale blue-green for GPU pool (provisions full replacement)
gcloud container node-pools update H100_POOL \
  --cluster CLUSTER_NAME --zone ZONE \
  --enable-autoscaling-with-upgrade-policy
```

**Caveat:** Needs capacity for the entire replacement pool upfront. Coordinate with your Google account team for H100/A100 capacity planning.

## Recommended Execution Plan

1. **Control plane first** (always required, ~15 minutes)
2. **Weekend 1:** 4 CPU pools with aggressive surge
3. **Validate:** Full application testing on upgraded CPU nodes  
4. **Weekend 2:** 4 GPU pools during training gap
5. **Post-upgrade:** Verify GPU drivers and CUDA compatibility

Would you like me to create a detailed runbook with the specific commands for your 8 pools, or focus on the training job coordination strategy for your GPU workloads?
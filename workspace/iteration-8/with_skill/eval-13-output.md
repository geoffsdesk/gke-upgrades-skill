# GKE Upgrade Plan for Long-Running Batch Jobs

Based on your Standard cluster with 8-16 hour batch jobs, here's a comprehensive upgrade strategy that protects your workloads while keeping your cluster secure and up-to-date.

## Strategy Overview: Maintenance Exclusions + Scheduled Upgrades

The key insight is that **maintenance exclusions are your primary protection tool** — they can block upgrades for up to version End of Support, giving you full control over timing.

## Recommended Approach

### 1. Apply "No Minor or Node Upgrades" Exclusion

This exclusion blocks the disruptive 1.30→1.31 minor upgrade while still allowing critical control plane security patches:

```bash
# Block minor and node upgrades until you're ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time 2025-04-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This gives you until 1.30's End of Support (approximately April 2025) to plan the upgrade during a natural job gap.

### 2. Configure Maintenance Window

Set a predictable upgrade window aligned with your batch job schedules:

```bash
# Example: Saturday 2-6 AM UTC when jobs typically finish
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2025-01-11T02:00:00Z \
  --maintenance-window-end 2025-01-11T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 3. When Ready to Upgrade (During Job Gap)

Remove the exclusion and initiate the upgrade during a planned downtime:

```bash
# Remove exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-job-protection"

# Immediately upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Configure node pool surge settings for batch workloads
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools (after CP upgrade completes)
gcloud container node-pools upgrade BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

## Alternative: Autoscaled Blue-Green Strategy

For the ultimate protection of long-running jobs, consider GKE's autoscaled blue-green upgrade strategy (preview):

```bash
# Enable autoscaled blue-green for the node pool
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 24h \
  --enable-blue-green-upgrade \
  --blue-green-batch-size-percent 20 \
  --blue-green-batch-soak-duration 8h
```

This strategy:
- Cordons the old pool but keeps it running
- Scales up replacement nodes as needed
- Allows much longer eviction periods for job completion
- Perfect for your 8-16 hour workloads

## Workload Protection Checklist

```
Pre-Upgrade Protection
- [ ] Maintenance exclusion applied: "no_minor_or_node_upgrades"
- [ ] Maintenance window configured for job downtime periods
- [ ] PDBs configured on batch jobs (set minAvailable appropriately)
- [ ] terminationGracePeriodSeconds set to reasonable value (e.g., 30 minutes)
- [ ] Jobs have checkpointing enabled for resume after upgrade
- [ ] Monitoring active to track job completion patterns

During Upgrade Window
- [ ] No active batch jobs running (verify with kubectl get pods)
- [ ] Job queue paused or drained
- [ ] Exclusion removed
- [ ] Control plane upgraded first
- [ ] Node pools upgraded with conservative surge settings
- [ ] Job scheduling re-enabled after validation

Post-Upgrade Validation
- [ ] All nodes at target version
- [ ] Test batch job submission and execution
- [ ] Verify job runtime not affected by node image changes
- [ ] Resource quotas and scheduling behavior unchanged
```

## Timeline Considerations

- **1.30 End of Support:** Approximately April 2025
- **Recommended action:** Plan your next upgrade window within the next 2-3 months
- **Batch job patterns:** Monitor your typical job completion cycles to identify optimal upgrade windows

## Why This Approach Works

1. **Maintenance exclusions** give you complete control over timing — no surprise upgrades
2. **Control plane patches** still arrive automatically for security
3. **Scheduled timing** aligns with your operational patterns
4. **Conservative surge settings** minimize disruption during the actual upgrade
5. **Extended planning window** — you have until EoS to execute

This strategy transforms the upgrade from a disruptive surprise into a planned maintenance event that respects your workload requirements.
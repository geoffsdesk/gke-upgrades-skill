I notice you mentioned upgrading from 1.32 to 1.32 - I assume you meant upgrading **to** 1.33 or another target version. Let me create a rollout strategy assuming you want to upgrade to **1.33**. Please confirm the target version and I'll adjust accordingly.

# Multi-Environment GKE Upgrade Rollout Strategy

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current version:** 1.32.x
- **Target version:** 1.33.x (please confirm)
- **Channel:** Regular (all environments)
- **Cluster type:** Standard

## Rollout Sequence Strategy

Since all environments are on the **same release channel (Regular)**, we can't use GKE's native rollout sequencing feature (which requires different channels). Instead, we'll use **maintenance windows and exclusions** to create a controlled progression.

### Phase 1: Development Environment
**Duration:** Week 1
**Approach:** Fast parallel upgrade with auto-upgrades enabled

```bash
# Configure dev clusters for immediate upgrades (remove any exclusions)
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --remove-maintenance-exclusion EXCLUSION_NAME || true
done
```

**Validation criteria:**
- All dev clusters successfully upgraded
- Application smoke tests passing
- No critical issues identified
- 48-hour soak period completed

---

### Phase 2: Staging Environment  
**Duration:** Week 2 (after dev validation)
**Approach:** Controlled upgrade with maintenance windows

```bash
# Set staging maintenance windows (staggered across clusters)
gcloud container clusters update staging-cluster-1 \
  --zone ZONE \
  --maintenance-window-start "2024-02-10T02:00:00Z" \
  --maintenance-window-end "2024-02-10T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

gcloud container clusters update staging-cluster-2 \
  --zone ZONE \
  --maintenance-window-start "2024-02-10T03:00:00Z" \
  --maintenance-window-end "2024-02-10T07:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Continue for staging-cluster-3 and staging-cluster-4 with 1-hour offsets
```

**Validation criteria:**
- End-to-end testing in staging
- Performance benchmarks within baseline
- Integration tests with downstream services
- 72-hour soak period

---

### Phase 3: Production Environment
**Duration:** Week 3-4 (after staging validation)
**Approach:** Conservative upgrade with maximum safety controls

```bash
# Apply "no minor or node upgrades" exclusion to prod clusters initially
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "prod-upgrade-control" \
    --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
    --add-maintenance-exclusion-until-end-of-support \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done
```

**Production rollout sub-phases:**

**3a. Canary cluster (prod-cluster-1):**
```bash
# Remove exclusion for canary cluster
gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --remove-maintenance-exclusion prod-upgrade-control

# Set tight maintenance window
gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --maintenance-window-start "2024-02-17T03:00:00Z" \
  --maintenance-window-end "2024-02-17T05:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**3b. Production batch 1 (after 48h canary soak):**
```bash
# Upgrade prod-cluster-2 and prod-cluster-3
for cluster in prod-cluster-2 prod-cluster-3; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --remove-maintenance-exclusion prod-upgrade-control
done
```

**3c. Production batch 2 (after batch 1 validation):**
```bash
# Finally upgrade prod-cluster-4
gcloud container clusters update prod-cluster-4 \
  --zone ZONE \
  --remove-maintenance-exclusion prod-upgrade-control
```

## Node Pool Upgrade Strategy (per cluster)

Since these are Standard clusters, configure appropriate surge settings per node pool type:

### Stateless application pools:
```bash
gcloud container node-pools update NODEPOOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Database/stateful pools:
```bash
gcloud container node-pools update NODEPOOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### GPU pools (if any):
```bash
gcloud container node-pools update NODEPOOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Pre-Upgrade Validation Checklist

Run this for each environment before proceeding:

```bash
# Verify target version availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.regular)"

# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Validate PDB configurations
kubectl get pdb -A -o wide

# Check cluster health baseline
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Rollback Strategy

**If issues are discovered:**

1. **During dev/staging:** Apply immediate "no upgrades" exclusion to remaining environments
2. **During production:** 
   - Stop progression (apply exclusions to remaining clusters)
   - For control plane issues: Contact GKE support for potential downgrade
   - For node pool issues: Create new node pool at previous version and migrate workloads

```bash
# Emergency brake - block all upgrades for 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-stop" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Timeline Summary

| Phase | Duration | Clusters | Soak Time |
|-------|----------|----------|-----------|
| Dev | Week 1 | 4 clusters (parallel) | 48 hours |
| Staging | Week 2 | 4 clusters (staggered) | 72 hours |
| Prod Canary | Week 3 | 1 cluster | 48 hours |
| Prod Batch 1 | Week 3-4 | 2 clusters | 24 hours |
| Prod Batch 2 | Week 4 | 1 cluster | Final validation |

**Total timeline:** 3-4 weeks end-to-end

## Key Success Metrics

- Zero unplanned downtime
- All workloads maintain SLA during upgrades  
- Application performance within 5% of baseline
- No deprecated API breakages
- Successful upgrade of all 12 clusters

---

**Please confirm your target version (1.33?) and any specific workload types (GPU, stateful sets, etc.) so I can refine the node pool strategies accordingly.**
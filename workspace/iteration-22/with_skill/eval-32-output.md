# Large-Scale GKE Upgrade Strategy (3,000-node cluster)

Your upgrade timeouts are expected — with GKE's current ~20-node parallel upgrade limit, a 3,000-node cluster needs **150+ upgrade batches minimum**. An 8-hour maintenance window cannot accommodate this scale.

## Immediate Solutions

### 1. **Extend your maintenance window dramatically**
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2026-01-04T02:00:00Z" \
    --maintenance-window-duration 48h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Reality check:** At scale, upgrades take **days to weeks**, not hours. A 3,000-node cluster realistically needs 2-3 days of continuous upgrade time. Plan for weekend-spanning windows (Friday night → Monday morning).

### 2. **Sequence your node pool upgrades strategically**

**Phase 1 — CPU pools first (lower risk):**
```bash
# Upgrade CPU pools during first maintenance window
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
# Continue with remaining CPU pools
```

**Phase 2 — GPU pools during training gaps:**
```bash
# GPU pools upgraded separately during scheduled training downtime
# Use maxUnavailable=1-4 for GPU pools (maxSurge likely unavailable due to fixed reservations)
gcloud container node-pools update GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2  # Increase if workloads can tolerate capacity loss

gcloud container node-pools upgrade GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
```

### 3. **GPU-specific upgrade strategy**

For your A100/H100/L4/T4 pools:
- **Assume NO surge capacity available** (fixed GPU reservations)
- **Primary lever is `maxUnavailable`** — increase to 2-4 nodes if workloads tolerate capacity dips
- **Inference pools:** Consider autoscaled blue-green to avoid serving disruption
- **Training pools:** Use maintenance exclusions to block upgrades during active training campaigns

```bash
# GPU pool configuration for faster upgrades
gcloud container node-pools update A100_POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 4  # Drains 4 nodes simultaneously
```

## Operational Strategy

### **Use maintenance exclusions for phased rollouts**

Instead of relying on maintenance windows alone, use exclusions to control what upgrades when:

```bash
# Block all upgrades initially
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "large-cluster-rollout" \
    --add-maintenance-exclusion-start-time "2026-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2026-01-31T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# When ready, remove exclusion and manually trigger node pools in sequence
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion "large-cluster-rollout"
```

### **Manual upgrade coordination**

For ultimate control, trigger upgrades manually rather than waiting for auto-upgrades:

1. **Week 1:** Control plane upgrade only
2. **Week 2:** CPU pools 1-2 (stateless workloads first)  
3. **Week 3:** CPU pools 3-4
4. **Week 4:** GPU inference pools (during low-traffic periods)
5. **Week 5:** GPU training pools (during scheduled training gaps)

## Long-term Architecture Recommendations

### **Consider cluster decomposition**

A 3,000-node monolithic cluster may be too large for efficient upgrades. Consider splitting by function:

- **Training cluster:** GPU pools for training workloads
- **Inference cluster:** Mixed GPU/CPU for serving
- **Batch cluster:** CPU pools for batch processing  
- **Dev/staging clusters:** Separate from production

Smaller clusters (500-1000 nodes each) upgrade in hours instead of days.

### **Adopt Extended release channel**

```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**Benefits for large clusters:**
- 24-month support window (cost only during extended period)
- Minor version upgrades are NOT automatic — you control when they happen
- Only patches auto-apply, reducing overall upgrade frequency
- More time to plan and execute large-scale upgrades

### **Implement rollout sequencing (when available)**

For multi-cluster environments, configure fleet-based rollout sequencing to ensure dev/staging clusters upgrade before production.

## Monitoring and Validation

### **Track upgrade progress programmatically**

```bash
# Monitor node upgrade status
watch 'kubectl get nodes -o wide | grep -c "TARGET_VERSION"'

# Check upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE \
    --filter="operationType=UPGRADE_NODES AND status=RUNNING"

# Validate workload health during long upgrades
kubectl get pods -A | grep -E "Pending|Terminating|Error" | wc -l
```

### **Set realistic expectations**

- **3,000-node cluster = 150+ upgrade batches**
- **~20 nodes upgraded simultaneously (increasing to 100 in future)**
- **GPU pools with maxUnavailable=2: ~375 batches per GPU pool**
- **Total upgrade time: 3-7 days** depending on configuration

## Immediate Action Plan

1. **This weekend:** Extend maintenance window to 48+ hours
2. **Next month:** Implement phased CPU-first, GPU-second approach  
3. **Q1 planning:** Evaluate cluster decomposition for faster future upgrades
4. **Consider Extended channel** for fewer but more controllable major upgrades

The key insight: **Large-scale GKE upgrades are infrastructure operations, not maintenance windows.** Plan accordingly with multi-day execution periods and proper sequencing.
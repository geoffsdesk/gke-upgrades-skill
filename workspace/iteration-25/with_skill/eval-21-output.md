# Extended Channel Migration Plan

## Extended Channel Overview & Tradeoffs

### Benefits
- **Extended support period**: Up to 24 months vs 14 months on Regular/Stable
- **Manual minor version control**: Control plane minor upgrades are NOT automatic (except at end of extended support)
- **Same patch timing as Regular**: Security patches arrive at the same speed as Regular channel
- **Migration path from "No channel"**: Ideal for customers wanting maximum flexibility around EoS enforcement

### Key Tradeoffs

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Minor upgrades** | Automatic via maintenance windows | Manual only (customer-initiated) |
| **Patch upgrades** | Automatic | Automatic (same timing as Regular) |
| **Support duration** | 14 months | Up to 24 months |
| **Cost** | Standard | Extra cost ONLY during extended period (months 15-24) |
| **Node behavior** | Auto-upgrade to CP minor | Auto-upgrade to CP minor (unless blocked by exclusions) |
| **EoS enforcement** | Systematic at 14 months | Delayed until end of extended support |

### Critical Considerations

**Node pool behavior**: Node pools on Extended channel still auto-upgrade to match the control plane's minor version by default. If you manually upgrade the control plane from 1.31→1.32, node pools will auto-upgrade to 1.32 unless you have a "no minor" or "no minor or node" exclusion in place.

**Cost structure**: Extended channel has NO extra cost during the standard 14-month support period. Additional charges only apply during the extended support period (months 15-24). All minor versions 1.27+ are eligible for extended support.

**Patch timing**: Extended channel receives patches at the SAME speed as Regular channel — there is no delay. Only minor version progression is different.

## Migration Plan from Regular 1.31 to Extended

### Pre-Migration Steps

1. **Version compatibility check**:
   ```bash
   # Verify 1.31 is available in Extended channel
   gcloud container get-server-config --zone YOUR_ZONE \
     --format="yaml(channels.EXTENDED.validVersions)" | grep "1.31"
   ```

2. **Current cluster state**:
   ```bash
   gcloud container clusters describe CLUSTER_NAME \
     --zone ZONE \
     --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].version)"
   ```

### Migration Process

1. **Apply temporary "no upgrades" exclusion** (prevents immediate auto-upgrades after channel switch):
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-name "channel-migration" \
     --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
     --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
     --add-maintenance-exclusion-scope no_upgrades
   ```

2. **Switch to Extended channel**:
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --release-channel extended
   ```

3. **Add persistent minor version control** (recommended for Extended channel workflow):
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-name "minor-control" \
     --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```

4. **Remove temporary exclusion**:
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --remove-maintenance-exclusion "channel-migration"
   ```

### Recommended Extended Channel Configuration

For maximum control while maintaining security posture:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- ✅ Extended support (24 months)
- ✅ Auto-applied control plane security patches only
- ✅ Manual control over minor upgrades
- ✅ No node auto-upgrades (prevents CP/node version skew)
- ✅ Patches limited to Saturday 2-6 AM window

### Operational Workflow on Extended Channel

**Patches**: Automatic within your maintenance window (same timing as Regular)

**Minor upgrades**: Manual process when you're ready:
1. Monitor GKE release schedule for new minor versions
2. Test in staging/dev cluster first
3. Manually upgrade production:
   ```bash
   # Control plane first
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version 1.32.X-gke.Y
   
   # Node pools second (or use skip-level if CP is 2+ versions ahead)
   gcloud container node-pools upgrade NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.32.X-gke.Y
   ```

### Migration Warnings

⚠️ **Version availability**: Since your cluster is currently at 1.31 on Regular, and 1.31 is available in Extended, you can migrate without version concerns.

⚠️ **Post-migration auto-upgrade behavior**: After switching channels, verify your auto-upgrade target hasn't changed unexpectedly:
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

⚠️ **Rollout sequencing compatibility**: If you use rollout sequencing across multiple clusters, ALL clusters in the sequence must be on the same channel. Plan coordinated migration if needed.

## Alternative: Stay on Regular with Minor Control

If the 24-month support isn't critical, you can achieve similar control on Regular channel:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This blocks minor auto-upgrades on Regular channel while keeping the 14-month support lifecycle and avoiding extended support costs.

## Recommendation

**Choose Extended channel if**:
- You need 24-month support lifecycles
- You prefer manual minor upgrade control
- You want maximum flexibility around EoS enforcement
- Cost during extended period (months 15-24) is acceptable

**Stay on Regular with exclusions if**:
- 14-month lifecycle is sufficient
- You want to avoid extended support costs
- You're comfortable with slightly faster minor version availability

The migration process is straightforward, and Extended channel provides excellent control for production workloads requiring predictable, manual upgrade timing.
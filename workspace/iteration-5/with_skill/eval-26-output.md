# GKE 1.28 End of Support Impact Analysis

## What happens to each cluster type at EoS

### Regular Channel Clusters (3 clusters)
**What happens:** Force-upgraded to 1.29 automatically
- Control plane upgraded first, then all node pools
- Upgrade timing depends on your maintenance windows and current auto-upgrade target
- No way to stay on 1.28 past EoS unless you apply a temporary "no upgrades" exclusion (30-day max)
- Standard EoS enforcement applies

### Extended Channel Clusters (2 clusters) 
**What happens:** **No immediate force-upgrade** - you have options
- Extended channel provides up to 24 months of support for 1.28
- You can stay on 1.28 longer than Regular channel clusters
- Still subject to eventual EoS enforcement, but timeline is extended
- Continue receiving security patches during extended support period

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** **Systematic node-level EoS enforcement**
- Nodes on 1.28 will be force-upgraded when EoS hits
- This is the most disruptive scenario - individual nodes upgraded without coordination
- Control plane may be upgraded separately from nodes
- **High priority:** Migrate this cluster to a release channel before EoS

## Preparation options by cluster type

### For Regular Channel Clusters

**Option 1: Proactive upgrade (Recommended)**
```bash
# Upgrade to 1.29 before EoS enforcement
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.29.x-gke.xxxx
```

**Option 2: Temporary delay with exclusion**
```bash
# Buy 30 days max to prepare
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-preparation" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### For Extended Channel Clusters

**Option 1: Stay on 1.28 (Leverages Extended support)**
- Continue on 1.28 with extended support
- Plan upgrade to 1.29+ within the 24-month window
- Monitor for any extended support costs

**Option 2: Migrate to newer version**
- Same proactive upgrade options as Regular channel
- More flexibility on timing

### For Legacy "No Channel" Cluster (Critical)

**Step 1: Migrate to release channel IMMEDIATELY**
```bash
# Migrate to Regular channel (recommended for most cases)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# OR migrate to Extended if you need maximum upgrade flexibility
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Step 2: Apply maintenance exclusion while you plan**
```bash
# After channel migration, add protection
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

## Recommended action plan

### Immediate (this week)
1. **Migrate the "No channel" cluster** - this is your highest risk
2. **Check current auto-upgrade targets** on all clusters:
   ```bash
   for cluster in CLUSTER1 CLUSTER2 CLUSTER3; do
     echo "=== $cluster ==="
     gcloud container clusters describe $cluster --zone ZONE \
       --format="table(name,currentMasterVersion,releaseChannel.channel)"
   done
   ```

### Short-term (next 2-4 weeks)
1. **Plan upgrades for Regular channel clusters** - create upgrade runbooks, test in dev/staging
2. **Configure maintenance windows** if not already set:
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --maintenance-window-start "2024-01-06T06:00:00Z" \
     --maintenance-window-end "2024-01-06T10:00:00Z" \
     --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
   ```

### Medium-term (1-3 months)
1. **Execute upgrades** on Regular channel clusters in sequence (dev → staging → prod)
2. **Plan Extended channel strategy** - decide if you want to stay on 1.28 or upgrade
3. **Implement rollout sequencing** if you have 3+ clusters:
   ```bash
   # Configure rollout order with soak time
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --enable-rollout-sequencing
   ```

## Monitoring EoS timeline

Check the official timeline:
```bash
# See current version support status
gcloud container get-server-config --zone ZONE \
  --format="yaml(validMasterVersions,validNodeVersions)"
```

Monitor your clusters' EoS status in the GKE console or set up notifications via Cloud Logging for advance warning.

The key insight: your Extended channel clusters give you the most flexibility, Regular channel clusters need proactive management, and the "No channel" cluster is your immediate fire drill. Focus on the legacy cluster first, then plan systematic upgrades for the Regular channel clusters.
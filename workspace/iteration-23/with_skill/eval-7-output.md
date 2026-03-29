# GKE Multi-Environment Upgrade Strategy: 1.32 → 1.33

## Environment Overview
- **12 Standard clusters** across 3 environments (4 clusters each)
- **Current version:** 1.32
- **Target version:** 1.33 
- **Release channel:** Regular (all environments)
- **Upgrade type:** Minor version upgrade

## Recommended Rollout Strategy

### Option A: Progressive Manual Control (Recommended)

Since all environments are on the **same channel** (Regular), use maintenance exclusions with user-triggered upgrades to control progression timing:

```bash
# Step 1: Block auto-upgrades on all clusters
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4 \
               staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4 \
               prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "controlled-upgrade-133" \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

### Rollout Sequence

**Week 1: Dev Environment**
```bash
# Upgrade dev clusters sequentially with validation gaps
gcloud container clusters upgrade dev-cluster-1 --zone ZONE --cluster-version 1.33.x-gke.xxxx --master
# Wait 24-48h, validate workloads
gcloud container node-pools upgrade --all --cluster dev-cluster-1 --zone ZONE --cluster-version 1.33.x-gke.xxxx

# Repeat for remaining dev clusters with 2-day gaps
```

**Week 2: Staging Environment**  
After dev validation passes, upgrade staging clusters using the same pattern.

**Week 3-4: Production Environment**
After staging validation passes, upgrade production clusters.

### Option B: GKE Rollout Sequencing (Advanced)

For automated fleet-wide orchestration, configure rollout sequencing with fleets:

```bash
# Create fleet memberships (lightweight, no full fleet overhead)
gcloud container fleet memberships register dev-fleet-member \
  --cluster=projects/PROJECT_ID/locations/ZONE/clusters/dev-cluster-1 \
  --project=DEV_PROJECT_ID

# Configure sequencing: dev → staging → prod with 7-day soak times
gcloud container fleet clusterupgrade update \
  --project=STAGING_PROJECT_ID \
  --upstream-fleet=DEV_PROJECT_ID \
  --default-upgrade-soaking=7d

gcloud container fleet clusterupgrade update \
  --project=PROD_PROJECT_ID \
  --upstream-fleet=STAGING_PROJECT_ID \
  --default-upgrade-soaking=7d
```

## Pre-Upgrade Preparation

### 1. Version Compatibility Check
```bash
# Confirm 1.33 is available in Regular channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.REGULAR.validVersions)"

# Check for deprecated APIs (common upgrade blocker)
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  kubectl --context=$cluster get --raw /metrics | grep apiserver_request_total | grep deprecated
done
```

### 2. Maintenance Windows Configuration
```bash
# Set weekend maintenance windows for each environment
# Dev: Friday 10 PM - Saturday 6 AM
gcloud container clusters update dev-cluster-* \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"

# Staging: Saturday 10 PM - Sunday 6 AM  
gcloud container clusters update staging-cluster-* \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T22:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Prod: Sunday 2 AM - 6 AM (smaller window)
gcloud container clusters update prod-cluster-* \
  --zone ZONE \
  --maintenance-window-start "2024-01-07T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### 3. Node Pool Upgrade Strategy
Configure surge settings before starting upgrades:

```bash
# Standard settings for most workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Conservative settings for stateful workloads
gcloud container node-pools update database-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Execution Timeline

### Week 1: Development
- **Day 1:** Upgrade dev-cluster-1 (CP + nodes)
- **Day 2:** Validate, then upgrade dev-cluster-2  
- **Day 4:** Upgrade dev-cluster-3
- **Day 6:** Upgrade dev-cluster-4
- **Day 7:** Full dev environment validation

### Week 2: Staging  
- **Day 8:** Upgrade staging-cluster-1
- **Day 10:** Upgrade staging-cluster-2
- **Day 12:** Upgrade staging-cluster-3  
- **Day 14:** Upgrade staging-cluster-4

### Week 3-4: Production
- **Day 15:** Upgrade prod-cluster-1
- **Day 18:** Upgrade prod-cluster-2
- **Day 21:** Upgrade prod-cluster-3
- **Day 24:** Upgrade prod-cluster-4

## Validation Checklist Per Environment

```markdown
Environment Validation Checklist
- [ ] All clusters at 1.33.x-gke.xxxx
- [ ] All nodes Ready status
- [ ] No CrashLoopBackOff pods
- [ ] Application health checks passing
- [ ] Performance within baseline (latency, error rates)
- [ ] Integration tests passing
- [ ] Monitoring/alerting functional
```

## Rollback Strategy

**If issues found in dev:**
- Fix identified issues before proceeding to staging

**If issues found in staging:**
- Node pools can be rolled back by creating new pools at 1.32
- Control plane minor version rollback requires GKE support

**If issues found in production:**
- Halt rollout immediately
- Contact GKE support for control plane rollback assistance
- Implement workarounds while planning recovery

## Key Considerations

### Why Manual Control vs Auto-Upgrade
- **All environments on same channel** = they'll get 1.33 at roughly the same time
- **Manual trigger with exclusions** gives you precise control over rollout timing
- **Prevents version drift** between environments

### Alternative: Different Channels
Consider migrating environments to different channels for natural progression:
- Dev → **Rapid** channel (gets versions first)
- Staging → **Regular** channel (current)  
- Prod → **Stable** channel (gets versions last)

### Monitoring During Upgrade
- Enable scheduled upgrade notifications for 72h advance warning
- Monitor Cloud Logging for upgrade events and PDB violations
- Set up alerts for upgrade operation failures

This strategy balances speed, safety, and operational control while maintaining environment parity and minimizing risk to production workloads.
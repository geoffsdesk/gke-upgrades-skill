# Extended Release Channel Migration Plan

## Overview
Extended channel provides **up to 24 months of support** for versions 1.27+, but has key behavioral differences from Regular channel that affect upgrade operations.

## Key Tradeoffs

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Minor version auto-upgrades** | Yes, automatic | **No** - manual only (except at end of extended support) |
| **Patch auto-upgrades** | Yes | Yes |
| **Support duration** | 14 months | Up to 24 months |
| **Extra cost** | None | Only during extended period (months 15-24) |
| **Operational model** | Hands-off | **Requires planning for minor upgrades** |
| **Version availability** | Same as Regular | Same as Regular during standard support |

## Critical Behavioral Change

**Extended channel does NOT auto-upgrade minor versions** (except at the very end of extended support). This means:
- Your cluster will stay on 1.31.x indefinitely, receiving patches only
- When you want to adopt 1.32, 1.33, etc., **you must manually trigger the upgrade**
- This requires internal processes to track when new minors are available and plan upgrades

## Migration Steps

### 1. Pre-migration checks
```bash
# Verify current version is available in Extended
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED.validVersions)"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel,currentMasterVersion)"
```

### 2. Apply temporary maintenance exclusion
```bash
# Prevent auto-upgrades during channel switch
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Switch to Extended channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 4. Configure maintenance exclusion for manual control
```bash
# Remove temporary exclusion and add persistent "no minor" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-name "manual-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 5. Verify migration
```bash
# Confirm channel switch
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel,maintenancePolicy)"

# Check auto-upgrade target (should only show patches, not minors)
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

## Operational Process for Extended Channel

Since Extended doesn't auto-upgrade minor versions, establish this process:

### Monthly version tracking
```bash
# Check available minor versions
gcloud container get-server-config --zone ZONE \
  --format="table(channels.EXTENDED.validVersions[].version)"

# Monitor GKE release schedule for new versions
# https://cloud.google.com/kubernetes-engine/docs/release-schedule
```

### When to upgrade minors manually
- **Security:** When CVEs affect your current minor version
- **Features:** When you need new Kubernetes features
- **Timeline:** Before current minor reaches end of standard support (14 months)
- **Compliance:** Based on your organization's currency requirements

### Manual minor upgrade process
```bash
# When ready to adopt a new minor (e.g., 1.32)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx

# Node pools upgrade separately
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

## Cost Implications

- **Months 1-14:** No extra cost (standard support period)
- **Months 15-24:** Additional cost applies for extended support
- **Planning:** Budget for extended support fees starting ~12 months after each minor version adoption

## Recommendations

**For your Regular → Extended migration:**

✅ **Good fit if:**
- You want maximum control over minor version timing
- You have processes to track and plan minor upgrades
- You're comfortable with manual upgrade operations
- You need longer support windows for compliance

❌ **Consider staying on Regular if:**
- You prefer hands-off automatic minor upgrades
- You lack processes for tracking/planning upgrades
- You want the simplest operational model

**Alternative approach:** Stay on Regular with "no minor" exclusions and manual minor upgrades. This gives you similar control without switching channels and maintains the option for automatic minors if needed.

## Migration Timeline

1. **Week 1:** Apply temporary exclusion and switch channel
2. **Week 2:** Configure persistent exclusion policy
3. **Ongoing:** Establish monthly version monitoring process
4. **Future:** Plan manual minor upgrades based on your timeline

Would you like me to detail the specific commands for your environment or help design the ongoing operational process for tracking new versions?
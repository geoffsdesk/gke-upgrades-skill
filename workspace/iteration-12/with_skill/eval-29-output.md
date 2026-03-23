# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No upgrades"

```bash
# June code freeze - blocks ALL upgrades for 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 2. Black Friday/Cyber Monday (November) - "No upgrades"

```bash
# BFCM period - blocks ALL upgrades for critical sales period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Never Auto-upgrade Minor Versions - "No minor or node upgrades"

```bash
# Permanent exclusion - allows control plane patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Configuration Summary

| Period | Exclusion Type | What Happens | Duration |
|--------|---------------|--------------|----------|
| **June (code freeze)** | `no_upgrades` | Zero upgrades - patches, minor, nodes all blocked | 30 days max |
| **BFCM (November)** | `no_upgrades` | Zero upgrades - complete freeze during critical sales | 20 days |
| **Year-round** | `no_minor_or_node_upgrades` | Control plane patches allowed, minor + node versions require your approval | Until End of Support (auto-renews) |

## Key Benefits of This Setup

✅ **Control plane security patches continue** - even with the permanent exclusion, your control plane gets critical security updates  
✅ **No surprise minor version bumps** - you control when K8s versions change  
✅ **No surprise node disruptions** - node pool upgrades only happen when you initiate them  
✅ **Critical period protection** - complete upgrade freeze during June and BFCM  
✅ **Auto-renewing** - the permanent exclusion tracks End of Support dates automatically  

## When You Want to Upgrade

Since you're blocking auto-upgrades, you'll need to manually trigger upgrades:

```bash
# Control plane minor upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Node pool upgrade 
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Verification Commands

```bash
# List all exclusions on the cluster
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime,maintenancePolicy.window.maintenanceExclusions[].scope)"

# Check what upgrades are currently blocked
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Important Notes

⚠️ **"No upgrades" exclusions are honored even past End of Support** - if a version reaches EoS during June or BFCM, GKE will wait until the exclusion expires before force-upgrading  
⚠️ **30-day limit on "no_upgrades"** - you can't extend June beyond 30 days, but BFCM at 20 days is fine  
⚠️ **End of Support enforcement** - the permanent exclusion will NOT prevent EoS upgrades forever. When your current version reaches EoS, you'll need to upgrade to stay supported  

This configuration gives you maximum control while maintaining security through continued patch updates.
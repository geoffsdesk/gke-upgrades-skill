Based on your requirements, here's the exact configuration for your maintenance exclusions. You have three distinct needs that require different exclusion types:

## Configuration for Each Requirement

### 1. Quarterly Code Freeze (June)
Use **"no upgrades"** exclusion - blocks ALL upgrades including patches:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum. For a full 30-day June freeze, you'll need to chain exclusions if you need longer coverage.

### 2. Black Friday/Cyber Monday (November)
Use **"no upgrades"** exclusion for your critical sales period:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. No Automatic Minor Version Upgrades (Permanent)
Use **"no minor or node upgrades"** with persistent exclusion - allows control plane security patches but blocks disruptive changes:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-auto-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Why These Specific Exclusion Types?

| Exclusion Type | What It Blocks | Max Duration | Your Use Case |
|---------------|---------------|-------------|---------------|
| **"No upgrades"** | All upgrades (patches, minor, nodes) | 30 days | June freeze, BFCM |
| **"No minor or node upgrades"** | Minor version + node pool upgrades. Allows CP patches. | Until End of Support | Permanent minor version control |

## Important Considerations

**Exclusion Limits:**
- Maximum 3 "no upgrades" exclusions per cluster
- Within any 32-day period, at least 48 hours must be available for maintenance
- Plan your June and November exclusions carefully to avoid hitting these limits

**Security Patches:**
- Your permanent "no minor or node upgrades" exclusion still allows control plane security patches
- During June/BFCM "no upgrades" periods, you'll accumulate security debt - plan catch-up patches afterward

**Manual Upgrades When Ready:**
When you want to perform minor upgrades on your timeline:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Then node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Note:** Manual upgrades bypass ALL maintenance exclusions - the exclusions only control auto-upgrades.

## Recommended Maintenance Windows

Pair with predictable maintenance windows for when patches ARE allowed:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you: Saturday 2-6 AM weekly windows for allowed patches, complete freezes during your critical periods, and full control over when minor upgrades happen.
# GKE Maintenance Configuration for SOX Compliance

For your regulated financial services environment, I'll configure a comprehensive maintenance strategy that balances security (auto-patches) with operational control. This setup follows SOX compliance best practices while minimizing manual overhead.

## Recommended Configuration Strategy

**Core principle:** Use Extended channel + "no minor or node upgrades" exclusion + disruption budgets for maximum control while maintaining security posture.

### 1. Channel Strategy per Environment

```bash
# Production clusters → Extended channel (24-month support, manual minor upgrades)
gcloud container clusters update prod-cluster-1 \
    --release-channel extended

gcloud container clusters update prod-cluster-2 \
    --release-channel extended

# Dev/Staging → Regular channel (gets patches first for validation)
gcloud container clusters update dev-cluster-1 \
    --release-channel regular
```

**Rationale:** Extended channel provides 24 months of support and only auto-applies security patches (no minor version auto-upgrades). You control when minor upgrades happen, perfect for SOX change control processes.

### 2. Weekend-Only Maintenance Windows

```bash
# Production clusters - Saturday 2-6 AM EST maintenance window
gcloud container clusters update prod-cluster-1 \
    --maintenance-window-start "2024-01-06T07:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

gcloud container clusters update prod-cluster-2 \
    --maintenance-window-start "2024-01-06T08:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Stagger by 1 hour to avoid simultaneous upgrades
```

### 3. SOX-Compliant Exclusion Configuration

```bash
# Block minor version and node upgrades, allow security patches only
gcloud container clusters update prod-cluster-1 \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

gcloud container clusters update prod-cluster-2 \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Key benefit:** This persistent exclusion automatically tracks version End of Support dates and renews when adopting new minor versions. No manual exclusion chain management needed.

### 4. Disruption Budget (Compliance Control)

```bash
# Limit patch frequency to once every 90 days maximum
gcloud container clusters update prod-cluster-1 \
    --maintenance-patch-version-disruption-interval=90d \
    --maintenance-minor-version-disruption-interval=90d

gcloud container clusters update prod-cluster-2 \
    --maintenance-patch-version-disruption-interval=90d \
    --maintenance-minor-version-disruption-interval=90d
```

### 5. Quarterly Code Freeze Exclusions

For your quarterly freezes, apply temporary "no upgrades" exclusions:

```bash
# Q1 Code Freeze Example (blocks ALL upgrades including patches)
gcloud container clusters update prod-cluster-1 \
    --add-maintenance-exclusion-name "Q1-2024-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Apply to all production clusters
gcloud container clusters update prod-cluster-2 \
    --add-maintenance-exclusion-name "Q1-2024-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 6. Annual Audit Exclusion (November)

```bash
# November audit freeze
gcloud container clusters update prod-cluster-1 \
    --add-maintenance-exclusion-name "SOX-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

gcloud container clusters update prod-cluster-2 \
    --add-maintenance-exclusion-name "SOX-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## Complete Configuration Command (All-in-One)

```bash
# Production Cluster 1 - Full SOX Configuration
gcloud container clusters update prod-cluster-1 \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=90d \
    --maintenance-window-start "2024-01-06T07:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Production Cluster 2 - Staggered 1 hour later
gcloud container clusters update prod-cluster-2 \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=90d \
    --maintenance-window-start "2024-01-06T08:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## What This Configuration Provides

✅ **Security:** Auto-applied control plane security patches within your maintenance windows
✅ **Control:** No minor version or node upgrades without explicit approval
✅ **Predictability:** Only Saturday mornings, maximum once every 90 days
✅ **Compliance:** Full audit trail via Cloud Logging, supports SOX change control
✅ **Flexibility:** Can override with manual upgrades when needed

## Monitoring and Alerting Setup

Enable scheduled upgrade notifications for 72-hour advance warning:

```bash
gcloud container clusters update prod-cluster-1 \
    --send-scheduled-upgrade-notifications

gcloud container clusters update prod-cluster-2 \
    --send-scheduled-upgrade-notifications
```

Set up Cloud Logging alerts for upgrade events:

```
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
resource.labels.cluster_name=~"prod-cluster-.*"
```

## Minor Version Upgrade Process (When You're Ready)

When you need to upgrade minor versions (quarterly or as needed):

1. **Test in dev/staging first** (they're on Regular channel and get versions earlier)
2. **Plan maintenance window** during your scheduled weekend slots
3. **Execute manually:**
   ```bash
   gcloud container clusters upgrade prod-cluster-1 \
       --master --cluster-version 1.XX.X-gke.XXX
   ```
4. **Control plane upgrade** happens first, **node pools remain** at current version until you manually upgrade them
5. **Document in change control system** per SOX requirements

## Cost Implications

- **Extended channel cost:** Only applies during the extended support period (months 14-24). No extra charge during standard support (first 14 months).
- **Estimated additional cost:** ~$73/month per cluster only during extended support period for the control plane fee.

This configuration gives you the strongest compliance posture while maintaining security patches automatically. The setup prevents drift while respecting your code freezes and audit periods.
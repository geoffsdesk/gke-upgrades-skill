# GKE Configuration for Maximum Upgrade Control (Financial Services)

For financial services with strict change windows, here's the recommended configuration that gives maximum control while maintaining security posture:

## Recommended Configuration: Extended Channel + Persistent "No Minor or Node" Exclusion

```bash
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- **Extended support** (24 months vs. 14 months standard)
- **Security patches auto-applied** to control plane only
- **Manual control** over ALL disruptive changes (minor versions + node upgrades)
- **Patch frequency limit** (max once every 90 days)
- **Predictable timing** (Saturday 2-6 AM maintenance window)

## Why This Configuration Works for FinServ

### 1. Extended Release Channel Benefits
- **24-month support period** vs. 14 months standard
- **Additional cost only during extended period** (months 15-24)
- **No auto-upgrade of minor versions** (except at end of extended support)
- **Patches still auto-applied** for security
- **Recommended migration path** from legacy "No channel" setups

### 2. "No Minor or Node Upgrades" Exclusion
- **Blocks disruptive changes** while allowing security patches
- **Persistent exclusion** tracks End of Support automatically
- **No 30-day limit** like "no upgrades" exclusions
- **Prevents control plane/node version skew**

### 3. Disruption Interval Controls
- **Patch disruption interval: 90 days** prevents back-to-back patches
- **Enforced minimum gap** between upgrades
- **Regulatory compliance** friendly for change control

## Complete Setup Checklist

```markdown
Financial Services GKE Configuration Checklist

Channel & Version Control
- [ ] Migrate to Extended release channel
- [ ] Apply persistent "no minor or node upgrades" exclusion
- [ ] Configure 90-day patch disruption interval
- [ ] Set maintenance window to approved change window (e.g., Saturday 2-6 AM)

Security Posture
- [ ] Verify control plane patches auto-apply within maintenance window
- [ ] Enable scheduled upgrade notifications (72h advance notice)
- [ ] Configure Cloud Logging alerts for security patch notifications
- [ ] Document manual minor upgrade approval process

Change Management Integration
- [ ] Map GKE maintenance window to existing change control calendar
- [ ] Configure Pub/Sub notifications for upgrade events
- [ ] Create runbook for emergency patch exclusions (30-day "no upgrades" type)
- [ ] Establish quarterly minor upgrade planning cycle
```

## When You Need to Act

### 1. Control Plane Patches (Automatic)
- **Frequency:** Max once per 90 days
- **Timing:** During Saturday 2-6 AM window
- **Action required:** None (automatic)
- **Notification:** 72 hours advance via Cloud Logging

### 2. Minor Version Upgrades (Manual)
- **Frequency:** On your schedule (quarterly recommended)
- **Action required:** Manual initiation after change approval
- **Planning:** Use the 24-month extended support window

### 3. Node Pool Upgrades (Manual)
- **When:** After control plane minor upgrade
- **Strategy:** Blue-green recommended for zero downtime
- **Timing:** Within approved change windows only

## Emergency Override Process

For critical security patches that can't wait for the next maintenance window:

```bash
# Apply temporary "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "emergency-patch-defer" \
    --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-scope no_upgrades

# Manual patch during emergency change window
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version SECURITY_PATCH_VERSION

# Remove exclusion after emergency patch
gcloud container clusters update CLUSTER_NAME \
    --remove-maintenance-exclusion-name "emergency-patch-defer"
```

## Monitoring & Alerting Setup

```bash
# Enable scheduled upgrade notifications
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications

# Monitor upgrade events in Cloud Logging
# Query: resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
```

## Cost Considerations

- **Extended channel cost:** Only applies during extended support period (months 15-24)
- **No additional cost** for first 14 months
- **Budget planning:** Factor extended support cost for clusters you plan to keep on older versions

## Migration Path (if currently on "No Channel")

```bash
# Step 1: Apply temporary "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "channel-migration" \
    --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended

# Step 3: Apply persistent exclusion and remove temporary one
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --remove-maintenance-exclusion-name "channel-migration"
```

This configuration gives you **maximum control** over when disruptive changes happen while ensuring you **never miss critical security patches** - the ideal balance for regulated financial services environments.
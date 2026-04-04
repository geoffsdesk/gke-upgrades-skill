# Extended Release Channel Migration Plan

## Extended Channel Overview & Tradeoffs

### Benefits of Extended Channel
- **24-month support** for versions 1.27+ (vs 14 months on Regular)
- **Same patch timing as Regular** — patches arrive at Regular channel speed, no delay
- **Manual control over minor version upgrades** — control plane minor versions are NOT auto-upgraded (except at end of extended support)
- **Full SLA coverage** throughout both standard and extended support periods
- **Cost only during extended period** — no extra charge during the first 14 months

### Key Tradeoffs
- **Additional cost during extended support period** (months 15-24 of version lifecycle)
- **Manual minor upgrade responsibility** — you must plan and initiate control plane minor upgrades yourself
- **Node pools still follow control plane minor version** unless blocked by maintenance exclusions
- **Less frequent feature access** — you'll be on older minor versions longer than Regular channel users

### Cost Impact
Extended channel pricing applies ONLY during the extended support period (months 15-24). During the standard support period (months 1-14), there's no additional cost. For version 1.31, you'd pay extra costs roughly 10-12 months from now when 1.31 enters extended support.

## Migration Strategy & Warnings

### Current State Risk Assessment
Your cluster is currently on Regular channel at 1.31. **Critical consideration**: Check if version 1.31 is available in Extended channel yet:

```bash
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED.validVersions)"
```

**Migration warning**: If 1.31 is not yet available in Extended channel, migrating now will put your cluster "ahead of channel." This means:
- Your cluster will NOT receive auto-upgrades until Extended channel catches up to 1.31
- You'll be stuck at 1.31 without patches until Extended channel's version progression reaches 1.31
- You'll still receive patches, but not minor version upgrades

### Recommended Migration Approach

**Option 1: Wait for 1.31 in Extended (Safest)**
1. Monitor Extended channel until 1.31 becomes available
2. Then migrate during a maintenance window with temporary exclusion for control

**Option 2: Migrate Now with Temporary Exclusion**
```bash
# Step 1: Apply temporary "no upgrades" exclusion before migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Step 3: Remove temporary exclusion after verifying behavior
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration-freeze"
```

## Extended Channel Operational Model

### Control Plane Minor Version Control
Extended channel gives you manual control over control plane minor upgrades:

```bash
# Check available versions in Extended
gcloud container get-server-config --zone ZONE \
  --format="table(channels.EXTENDED.validVersions[].version)"

# Manually upgrade control plane when ready
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

### Node Pool Auto-Upgrade Behavior
**Important**: Node pools will still auto-upgrade to track the control plane's minor version unless you block them:

```bash
# Add persistent "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "production-stability" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This configuration gives you:
- Control plane patches automatically applied (security updates)
- Manual control over when minor upgrades happen
- Node pools stay at current version until you upgrade them manually
- Maximum predictability for production workloads

### Recommended Production Configuration

For regulated environments or maximum stability:

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

This provides:
- Extended 24-month support
- Control plane security patches only during Saturday 2-6 AM window
- Manual control over all minor version and node pool upgrades
- No surprise disruptions from auto-upgrades

## Migration Checklist

```markdown
Extended Channel Migration Checklist
- [ ] Current cluster: Regular channel at 1.31
- [ ] Target: Extended channel with manual minor upgrade control

Pre-Migration
- [ ] Verify 1.31 availability in Extended channel
- [ ] Plan maintenance window for migration
- [ ] Communicate change to team (manual minor upgrade responsibility)
- [ ] Decide on maintenance exclusion strategy for ongoing control

Migration Steps
- [ ] Apply temporary "no upgrades" exclusion (optional safety measure)
- [ ] Switch to Extended channel: `--release-channel extended`
- [ ] Verify channel change: `gcloud container clusters describe --format="value(releaseChannel.channel)"`
- [ ] Apply persistent exclusion for ongoing control if desired
- [ ] Remove temporary exclusion
- [ ] Document new operational procedures for team

Post-Migration Validation
- [ ] Auto-upgrade target matches expectations
- [ ] Maintenance windows still configured correctly
- [ ] Team understands new manual minor upgrade responsibility
- [ ] Monitoring/alerting updated for new channel behavior
```

## Ongoing Operations on Extended Channel

### When to Upgrade Minor Versions
- **Security advisories** affecting your Kubernetes version
- **Required features** only available in newer versions  
- **End of extended support approaching** (automatic upgrade triggers)
- **Application compatibility** requirements

### Minor Upgrade Process
1. Test target version in staging/dev environment first
2. Review [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
3. Upgrade control plane during maintenance window
4. Upgrade node pools after control plane validation
5. Validate workload health before marking complete

### Cost Management
Extended channel costs start when a version enters extended support (months 15-24 of its lifecycle). Monitor your [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) to understand when Extended pricing begins for your versions.

The Extended channel is ideal for your production environment if you value predictability and manual control over disruption timing, and can accept the additional operational responsibility for planning minor upgrades.
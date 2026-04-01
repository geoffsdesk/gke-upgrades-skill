# GKE Maintenance Configuration for SOX Compliance

I'll configure a maintenance strategy that provides maximum control while maintaining security posture for your regulated environment. This setup balances compliance requirements with automated security patching.

## Recommended Configuration Strategy

For financial services with SOX compliance, I recommend:
- **Extended release channel** for 24-month support and no automatic minor upgrades
- **Persistent "no minor or node" exclusions** for maximum control over disruptive changes
- **90-day patch disruption interval** to minimize control plane disruptions
- **Weekend-only maintenance windows** for predictable timing

## Configuration Commands

Run these commands for each of your 3 clusters:

```bash
# Replace with your actual cluster details
CLUSTER_NAME="your-cluster-name"
REGION="your-region"

# Configure Extended channel with maintenance controls
gcloud container clusters update $CLUSTER_NAME \
    --region $REGION \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## What This Configuration Provides

| Control | Benefit | SOX Compliance Impact |
|---------|---------|----------------------|
| **Extended channel** | 24-month support, no auto minor upgrades | Predictable change schedule, extended stability |
| **"No minor or node" exclusion** | Only security patches auto-apply to control plane | Critical security updates without disruptive changes |
| **90-day patch interval** | Maximum gap between control plane patches | Quarterly patch cycles align with your processes |
| **Saturday 2-6 AM window** | Predictable weekend-only upgrades | No business hours disruption |
| **Persistent exclusion** | Tracks EoS automatically, no manual renewal | Reduces operational overhead |

## Quarterly Code Freeze Configuration

For your quarterly freezes, add temporary "no upgrades" exclusions:

```bash
# Example for Q1 2024 freeze (adjust dates as needed)
gcloud container clusters update $CLUSTER_NAME \
    --region $REGION \
    --add-maintenance-exclusion-name "q1-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum. For longer freezes, chain multiple exclusions but be aware this increases security debt.

## Annual November Audit Freeze

```bash
# November audit freeze (example dates)
gcloud container clusters update $CLUSTER_NAME \
    --region $REGION \
    --add-maintenance-exclusion-name "november-audit" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## When Manual Upgrades Are Needed

With this configuration, you'll need to manually trigger:
1. **Minor version upgrades** - plan these during maintenance windows between quarters
2. **Node pool upgrades** - coordinate with application teams for validation
3. **Emergency security patches** - if a critical CVE requires immediate patching

Manual upgrade commands:
```bash
# Control plane minor upgrade (bypasses all exclusions)
gcloud container clusters upgrade $CLUSTER_NAME \
    --region $REGION \
    --master \
    --cluster-version TARGET_VERSION

# Node pool upgrade (after CP upgrade)
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster $CLUSTER_NAME \
    --region $REGION \
    --cluster-version TARGET_VERSION
```

## Monitoring and Compliance

Set up monitoring for compliance reporting:

```bash
# Check current exclusion status
gcloud container clusters describe $CLUSTER_NAME \
    --region $REGION \
    --format="yaml(maintenancePolicy)"

# Monitor upgrade info and EoS dates
gcloud container clusters get-upgrade-info $CLUSTER_NAME --region $REGION
```

## Key Benefits for SOX Compliance

✅ **Predictable change schedule** - upgrades only during defined windows
✅ **Maximum control** - all disruptive changes require manual approval
✅ **Security posture maintained** - critical patches still auto-apply to control plane
✅ **Audit trail** - all manual upgrades logged in Cloud Audit Logs
✅ **Extended support** - 24-month lifecycle reduces upgrade frequency
✅ **Freeze period support** - temporary exclusions for code freezes and audits

## Important Considerations

**Security Debt Warning:** Extended exclusion periods can cause clusters to fall behind on patches. Plan catch-up upgrades during maintenance windows.

**Version Skew:** Nodes can lag up to 2 minor versions behind control plane. Monitor with `kubectl get nodes` and upgrade node pools when needed.

**Cost:** Extended channel incurs additional cost only during the extended support period (months 15-24), not during standard support.

This configuration provides the maximum control available in GKE while maintaining automated security patching - ideal for regulated environments requiring SOX compliance.
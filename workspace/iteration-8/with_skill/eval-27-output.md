# GKE Upgrade Control Strategy for Financial Services

For maximum control over upgrade timing while maintaining security compliance, here's the recommended configuration:

## Primary Strategy: Release Channel + "No Minor or Node Upgrades" Exclusion

This gives you the best of both worlds - security patches automatically applied, but full control over disruptive changes.

### Configuration

```bash
# Set cluster to Regular or Stable channel (not Extended for this use case)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular  # or 'stable' for even more validation

# Add persistent maintenance exclusion that tracks End of Support
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "finserv-control-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Configure maintenance window for your change window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### What this achieves:

- ✅ **Control plane security patches**: Applied automatically during your maintenance window
- ✅ **No surprise minor version bumps**: Blocked until you explicitly choose to upgrade
- ✅ **No surprise node replacements**: Blocked until you explicitly choose to upgrade  
- ✅ **Persistent policy**: Automatically renews when you do upgrade to next minor version
- ✅ **Security compliance**: CVE patches still flow through automatically

## Why This Beats Other Options

| Approach | Security patches | Minor control | Node control | Complexity |
|----------|-----------------|---------------|--------------|------------|
| **"No minor or node upgrades" exclusion** ✅ | **Auto** | **Full** | **Full** | **Low** |
| Extended channel + manual minor upgrades | Auto | Full | Full | Medium |
| "No channel" (legacy) | Auto | Partial | Partial | High |
| Pure manual upgrades | Manual | Full | Full | High risk |

## Channel Selection: Regular vs Stable

For financial services, **Regular channel** is typically recommended:

- **Regular**: New versions after validation in Rapid (~2-4 weeks after release)
- **Stable**: Additional validation period (~6-8 weeks after release)

Choose Regular unless you have specific stability requirements that outweigh getting security patches sooner.

## Planned Upgrade Process

When you're ready for minor version upgrades (quarterly/semi-annually):

### 1. Remove exclusion temporarily
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "finserv-control-policy"
```

### 2. Initiate controlled upgrade
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Then node pools with controlled surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. Restore exclusion policy
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "finserv-control-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Emergency Override for Critical Security

If you need to block ALL upgrades temporarily (code freeze, major incident):

```bash
# Add 30-day "no upgrades" exclusion (blocks everything, including patches)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-31T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important**: This blocks security patches too - use sparingly and for maximum 30 days.

## Monitoring and Alerting

Set up proactive monitoring:

```bash
# Check auto-upgrade status and EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Enable scheduled upgrade notifications (72h advance notice)
# Configure via Cloud Logging notifications - see GKE documentation
```

## Multi-Environment Strategy

Typical financial services pattern:

- **Dev**: Regular channel, normal auto-upgrades (no exclusions)
- **Staging**: Regular channel, "no minor or node upgrades" exclusion  
- **Prod**: Regular or Stable channel, "no minor or node upgrades" exclusion

This allows you to validate in dev automatically, then control promotion to staging and prod.

## Why Not Extended Channel?

Extended channel seems appealing for control, but has drawbacks for your use case:

- **Manual minor upgrades required**: You must manually upgrade before end of extended support
- **Additional cost**: During extended support period (months 14-24)  
- **Still need exclusions**: For true control over timing within the extended period
- **Same security patches**: No additional security benefit vs Regular/Stable + exclusions

The "Regular/Stable + exclusions" approach gives you the same control with less complexity and cost.

This configuration gives you maximum upgrade control while ensuring you never fall behind on security patches - exactly what financial services compliance typically requires.
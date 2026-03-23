For your new production GKE Standard clusters on the Regular channel, **GKE's auto-upgrade system is the recommended approach** — this is the primary value proposition that differentiates GKE from self-managed Kubernetes. You should rely on automatic upgrades with proper controls rather than manual scheduling.

## Recommended Setup for Production

Here's what I recommend for your 3 production clusters:

### 1. Configure Maintenance Windows
Set predictable maintenance windows aligned with your off-peak hours:

```bash
# Example: Saturday 2-6 AM UTC maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Add Maintenance Exclusions for Maximum Control
For production workloads, I recommend the **"no minor or node upgrades"** exclusion, which:
- Allows control plane security patches (critical for security)
- Blocks disruptive minor version and node pool upgrades
- Gives you control over when major changes happen

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-upgrade-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

The `--add-maintenance-exclusion-until-end-of-support` flag automatically tracks your version's End of Support date, so you don't need to manually renew exclusions.

### 3. Plan User-Triggered Minor Upgrades
With the exclusion in place, plan to upgrade minor versions (1.30→1.31, etc.) during scheduled maintenance windows:

- Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) 
- Plan minor upgrades 1-2 months after they become available in Regular channel
- Execute during your maintenance windows when teams are available

## Why This Approach Works Best

**Auto-upgrades with controls beat manual scheduling because:**

1. **Security patches happen automatically** — you stay current on critical fixes without manual intervention
2. **Maintenance windows ensure predictable timing** — upgrades happen when you want them
3. **You control the scope** — exclusions let you approve minor versions while getting patches
4. **No operational overhead** — no need to track release schedules or remember to upgrade
5. **GKE's full SLA applies** — manual upgrades bypass some protections

## Alternative: Staging/Prod Channel Strategy

If you have staging environments, consider this simpler approach:
- **Staging**: Regular channel (no exclusions) — gets upgrades first
- **Production**: Stable channel (no exclusions) — gets validated versions ~1-2 weeks later

This gives you automatic validation in staging before production upgrades, with less operational complexity than exclusions.

## What to Avoid

❌ **Don't disable auto-upgrades entirely** — you'll miss security patches and eventually face forced upgrades at End of Support  
❌ **Don't use "No channel"** — it's a legacy option with fewer control features  
❌ **Don't rely purely on maintenance windows** — they control timing but not upgrade scope  

## Quick Setup Commands

Here's a complete setup for one cluster (repeat for all 3):

```bash
# Set maintenance window (adjust times for your timezone)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add persistent exclusion for upgrade control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-upgrade-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Verify configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy,releaseChannel)"
```

This gives you the best of both worlds: automatic security patching with controlled timing for disruptive changes. Your clusters will stay secure and up-to-date while giving you full control over when major upgrades happen.
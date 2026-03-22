For your new GKE Standard clusters on the Regular channel, **GKE will handle upgrades automatically** — this is the primary value proposition of managed Kubernetes and the recommended approach for most production environments.

## Auto-upgrades: The GKE default model

Your clusters will receive:
- **Patch upgrades** automatically (security fixes, bug fixes)
- **Minor version upgrades** automatically (new Kubernetes features)
- All upgrades follow the Regular channel cadence (well-tested versions after Rapid channel validation)

**Manual upgrades should be the exception**, used only for:
- Emergency security patching (accelerating ahead of auto-upgrade schedule)
- Upgrading clusters that have been deliberately held back with maintenance exclusions
- Specific timing requirements that can't be met with maintenance windows alone

## Recommended production setup

Here's what you should configure for proper upgrade control:

### 1. Set maintenance windows (essential)
```bash
# Configure recurring off-peak windows for each cluster
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-01T02:00:00Z \
  --maintenance-window-end 2024-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### 2. Configure maintenance exclusions for control
Choose the appropriate exclusion scope:

**For maximum control (recommended for production):**
```bash
# "No minor or node upgrades" - allows security patches on control plane, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-control" \
  --add-maintenance-exclusion-start-time 2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**For code freezes/critical periods:**
```bash
# "No upgrades" - blocks everything for up to 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "black-friday-freeze" \
  --add-maintenance-exclusion-start-time 2024-11-20T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-05T00:00:00Z \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Set disruption intervals
Control how frequently your clusters can be disrupted:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval 14d \
  --maintenance-minor-version-disruption-interval 60d
```

### 4. Configure node pool upgrade strategy
For each node pool, set appropriate surge settings:

**Stateless workloads:**
```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Stateful/database workloads:**
```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Multi-cluster coordination

Since you have 3 production clusters, consider staggered timing:

### Option 1: Different maintenance windows
- Cluster A: Sunday 2-6 AM
- Cluster B: Sunday 6-10 AM  
- Cluster C: Monday 2-6 AM

### Option 2: Rollout sequencing (advanced)
If all clusters must be on the same channel for workload compatibility:
```bash
# Configure rollout sequencing with soak time
gcloud container clusters update cluster-a \
  --zone ZONE \
  --rollout-sequencing-stage 1

gcloud container clusters update cluster-b \
  --zone ZONE \
  --rollout-sequencing-stage 2 \
  --rollout-sequencing-soak-time 72h

gcloud container clusters update cluster-c \
  --zone ZONE \
  --rollout-sequencing-stage 3 \
  --rollout-sequencing-soak-time 72h
```

## Monitoring and notifications

Enable upgrade visibility:
```bash
# Check auto-upgrade status and targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Opt into scheduled upgrade notifications (72h advance notice)
# Configure via Cloud Logging notifications
```

## When to manually upgrade

Only initiate manual upgrades when:
1. **Security emergency** - critical CVE requires immediate patching
2. **Controlled timing** - you want the upgrade at a specific moment within your maintenance window
3. **Testing new features** - validating a specific version before auto-upgrade arrives
4. **End of Support approaching** - proactive upgrade before enforcement

## Summary

✅ **Do**: Configure auto-upgrades with maintenance windows and exclusions
✅ **Do**: Set appropriate node pool surge strategies  
✅ **Do**: Stagger timing across your 3 clusters
✅ **Do**: Monitor upgrade status and notifications

❌ **Don't**: Disable auto-upgrades or use "No channel"
❌ **Don't**: Default to manual upgrade schedules
❌ **Don't**: Skip maintenance window configuration

This approach gives you the security and reliability benefits of automatic updates while maintaining control over timing and scope.
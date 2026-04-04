For your 3 GKE Standard clusters on Regular channel, **GKE handles upgrades automatically** — this is the recommended approach. You don't need to manually upgrade on a schedule.

## Auto-upgrade is the best practice

Your clusters will automatically receive:
- **Patch upgrades** (security fixes, bug fixes) 
- **Minor version upgrades** (new Kubernetes versions)

Both happen automatically based on GKE's release schedule, with Regular channel providing a good balance of stability and timeliness.

## What you should configure for production control

Instead of manual upgrades, configure these controls:

### 1. Maintenance Windows (timing control)
```bash
# Set upgrades to occur during off-peak hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-07T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

### 2. Rollout Sequencing (ordering across clusters)
Since you have 3 clusters, configure them to upgrade in sequence with validation time between:
- Cluster 1 (canary) → soak 2-3 days → Cluster 2 → soak 2-3 days → Cluster 3

### 3. Optional: Minor Version Control
For maximum control over disruptive changes, add a "no minor upgrades" exclusion:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

Then manually trigger minor upgrades after testing in your canary cluster.

## Recommended production setup

```bash
# For each cluster - set maintenance windows
gcloud container clusters update PROD-CLUSTER-1 \
  --zone ZONE \
  --maintenance-window-start "2024-01-07T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"

# Optional: Control minor versions while allowing patches
gcloud container clusters update PROD-CLUSTER-1 \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Why auto-upgrade beats manual schedules

- **Security**: You get patches automatically without delay
- **Reduced ops overhead**: No need to track release schedules manually  
- **Prevents snowflakes**: Manual schedules often slip, creating version drift
- **GKE expertise**: Google handles the upgrade orchestration and timing

The key is using maintenance windows and exclusions to control **when** and **what** upgrades happen, not trying to do them manually on your own schedule.

Would you like me to help you set up the specific maintenance windows and rollout sequencing for your 3-cluster setup?
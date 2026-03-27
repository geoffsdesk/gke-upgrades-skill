# GKE Version Terminology Explained

You're seeing three **distinct concepts** that are often confused. Here's what each means and why they're different:

## Version States Defined

| State | What it means | Your example |
|-------|---------------|--------------|
| **Available** | You CAN manually upgrade to this version right now | 1.31.6-gke.1000000 |
| **Default** | New clusters created today get this version | 1.31.8-gke.1200000 |
| **Auto-upgrade target** | Your existing cluster will be upgraded to this version automatically | 1.31.7-gke.1100000 |

## Why They're Different

**Available ≠ Auto-upgrade target:** GKE makes versions available for manual upgrades before they become the auto-upgrade target. This gives you the option to upgrade early if needed, while the auto-upgrade system waits for additional validation.

**Default ≠ Auto-upgrade target:** The default version for new clusters can be newer than what existing clusters auto-upgrade to. This happens during version rollouts — GKE may set a newer version as default for new clusters while being more conservative about upgrading existing production workloads.

**Your specific situation:** Your cluster will automatically upgrade to **1.31.7-gke.1100000** (the target), even though newer versions (1.31.8) are available. This is intentional — GKE's auto-upgrade system follows a more conservative path than what's available for manual upgrades.

## Factors Affecting Auto-upgrade Target

Your cluster's auto-upgrade target depends on:
- **Release channel** (Rapid/Regular/Stable/Extended)
- **Maintenance exclusions** (e.g., "no minor upgrades" changes the target to latest patch only)
- **Regional rollout** (versions roll out across regions over 4-5 days)
- **Progressive rollout** within the channel

## Check Your Cluster's Auto-upgrade Status

```bash
# See your cluster's specific auto-upgrade target and timing
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check your release channel
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(releaseChannel.channel)"
```

## Key Takeaway

**Focus on the auto-upgrade target** — that's what actually matters for your cluster's lifecycle. The "available" and "default" versions are useful for understanding your options, but your cluster will upgrade to the target version automatically based on your maintenance windows and exclusions.

If you want to upgrade to a different version than the target (like the newer 1.31.8), you'd need to trigger a manual upgrade. Otherwise, just let the auto-upgrade system handle it — it will upgrade to 1.31.7 when your maintenance window allows.
# GKE Version Terminology Explained

You're encountering the three distinct version concepts in GKE's lifecycle — they serve different purposes and can indeed be different versions. Here's what each means:

## Version Terminology Breakdown

| Term | What it means | Your example | Purpose |
|------|---------------|--------------|---------|
| **Available** | Versions you can manually upgrade to | 1.31.6-gke.1000000 | Manual upgrade options |
| **Default** | Version used for new cluster creation | 1.31.8-gke.1200000 | New cluster baseline |
| **Auto-upgrade target** | Version your existing cluster will upgrade to | 1.31.7-gke.1100000 | Actual upgrade destination |

## Why They're Different

**Available vs Default:** GKE keeps older patch versions "available" for manual upgrades (compatibility, rollback scenarios) even after promoting newer patches to "default." Your cluster can manually upgrade to 1.31.6 if needed, but new clusters get 1.31.8.

**Default vs Auto-upgrade target:** Your cluster's auto-upgrade target (1.31.7) is determined by:
- Your maintenance windows and exclusions
- Progressive rollout timing across regions
- Your cluster's current constraints

The "default" (1.31.8) represents the latest promoted version globally, but your specific cluster may target an earlier patch (1.31.7) based on rollout sequencing or policies.

## What This Means for You

- **Your cluster will auto-upgrade to 1.31.7-gke.1100000** when conditions are met
- **You could manually upgrade to 1.31.6 or 1.31.8** if needed
- **New clusters in your region get 1.31.8** by default

## Check Your Cluster's Specific Status

```bash
# See your cluster's auto-upgrade target and timing
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check your release channel and current version
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="table(releaseChannel.channel, currentMasterVersion)"
```

This will show you exactly when your cluster is scheduled to upgrade and why that specific target version was chosen.

**Key takeaway:** The auto-upgrade target is what actually matters for planning. The "default" and "available" versions give you context about the broader version landscape and manual upgrade options, but your cluster follows its specific auto-upgrade target based on your configuration.
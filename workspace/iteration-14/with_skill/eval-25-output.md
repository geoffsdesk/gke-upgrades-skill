You're encountering the three distinct version states in GKE's lifecycle. Let me clarify what each means:

## GKE Version Terminology

| Term | What it means | Your example |
|------|---------------|--------------|
| **Available** | Versions you CAN manually upgrade to | 1.31.6-gke.1000000 |
| **Default** | Version used for NEW cluster creation | 1.31.8-gke.1200000 |
| **Auto-upgrade target** | Version GKE will upgrade YOUR cluster to automatically | 1.31.7-gke.1100000 |

## Why they're different

**Available vs Default:** GKE keeps older patch versions "available" for manual upgrades even after promoting newer patches to "default" for new clusters. This gives you flexibility to choose specific patch levels.

**Default vs Auto-upgrade target:** Your cluster's auto-upgrade target is influenced by:
- **Maintenance exclusions** — if you have a "no minor" exclusion, your target stays on the latest patch of your current minor
- **Disruption intervals** — GKE enforces gaps between upgrades (default 24h for patches, 30d for minors)  
- **Progressive rollout** — newer versions roll out gradually across regions
- **Channel progression** — versions must prove stable before becoming auto-upgrade targets

## What this means for you

- **You can manually upgrade to 1.31.6** (available) or wait for auto-upgrade to 1.31.7 (target)
- **New clusters would get 1.31.8** (default)
- **Your cluster will auto-upgrade to 1.31.7** unless you have exclusions or are outside maintenance windows

## Check your cluster's specific constraints

```bash
# See your auto-upgrade status and why the target is what it is
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check for maintenance exclusions affecting your target
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(maintenancePolicy)"
```

The key insight: **auto-upgrade target** is what matters for planning — it's cluster-specific and considers your policies. "Available" and "default" are global states that don't account for your cluster's configuration.

Does this help explain the differences? What's your cluster's current version, and are you planning to upgrade manually or let auto-upgrade handle it?
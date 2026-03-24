# GKE Version Terminology Explained

You're encountering three distinct concepts in GKE's version lifecycle that are often confused but serve different purposes:

## The Three Version Types

| Type | Your Example | What It Means |
|------|--------------|---------------|
| **Available** | 1.31.6-gke.1000000 | Versions you can manually upgrade to right now |
| **Default** | 1.31.8-gke.1200000 | Version used for new cluster creation |
| **Auto-upgrade target** | 1.31.7-gke.1100000 | Version your existing cluster will actually upgrade to automatically |

## Why They're Different

### Available (1.31.6-gke.1000000)
- **All versions** officially released in your release channel
- Shows the full range of versions you could manually choose: `gcloud container clusters upgrade --cluster-version 1.31.6-gke.1000000`
- Includes older patches that are still supported but not recommended

### Default (1.31.8-gke.1200000)  
- **New cluster creation** uses this version
- Typically the newest stable version in your channel
- What you get when you run `gcloud container clusters create` without specifying `--cluster-version`

### Auto-upgrade target (1.31.7-gke.1100000)
- **Your cluster's specific target** for automatic upgrades
- Factors in your cluster's current constraints:
  - Maintenance windows
  - Maintenance exclusions (like "no minor upgrades")
  - Progressive rollout timing
  - Your cluster's current version and upgrade path

## Why Auto-upgrade Target ≠ Default

The auto-upgrade target is **cluster-specific** and considers your policies:

```bash
# Check your cluster's auto-upgrade constraints
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

Common reasons for the difference:
- **Progressive rollout**: Your cluster may be in an earlier rollout wave
- **Maintenance exclusions**: A "no minor upgrades" exclusion would keep you on 1.31.x patches
- **Channel promotion timing**: The newest version (1.31.8) may not have reached the auto-upgrade stage yet

## Practical Implications

**For planning:**
- **Auto-upgrade target** = what will happen automatically
- **Default** = what new clusters get  
- **Available** = what you could manually choose

**For operations:**
- Your cluster will auto-upgrade to 1.31.7-gke.1100000 (not the newer 1.31.8)
- If you want 1.31.8 immediately, you'd need to manually upgrade
- New clusters in your fleet would start at 1.31.8

## Version Progression Timeline

Versions typically progress through stages in your release channel:
1. **Available** → can manually upgrade
2. **Default** → new clusters use this  
3. **Auto-upgrade target** → existing clusters upgrade to this

The auto-upgrade target usually lags behind the default by ~1-2 weeks as GKE validates the version across the fleet.

This is working as designed — GKE separates "what's possible" (available) from "what's recommended for new clusters" (default) from "what's safe for your existing cluster" (auto-upgrade target).
When a GKE minor version reaches End of Support (EoS), Google’s policy is to ensure cluster security and reliability by systematically force-upgrading the control plane and nodes to the next supported minor version (in this case, 1.31). 

However, exactly **when and how** this happens depends entirely on the cluster's release channel. 

Here is exactly what will happen to your clusters and how to prepare.

---

### 1. What happens at EoS by Channel

#### 🟢 Regular Channel Clusters (3 clusters)
* **What happens:** At the standard EoS date for 1.30, GKE will automatically upgrade both the control plane and node pools to 1.31. 
* **Enforcement:** This auto-upgrade will ignore standard "no minor or node upgrades" exclusions because the version is no longer supported. The only exclusion that can delay this is a strict `"no upgrades"` exclusion, which has a hard maximum of 30 days.

#### 🔵 Extended Channel Clusters (2 clusters)
* **What happens:** **Nothing yet.** Version 1.30 on the Extended channel does *not* hit EoS at the same time as the Regular channel. Extended channel provides up to 24 months of support from the original release date.
* **Enforcement:** GKE will continue to auto-apply security patches for 1.30. However, **minor upgrades are not automated** on the Extended channel (until the very end of the 24-month window). You are responsible for manually triggering the minor upgrade to 1.31 when you are ready. 
* *Note: Extended channel incurs an additional fee, but only during the extended support period (after standard EoS).*

#### 🔴 Legacy "No channel" Cluster (1 cluster)
* **What happens:** At standard EoS, the control plane will be auto-upgraded to 1.31. The node pools will also be systematically force-upgraded to 1.31, **even if you have legacy "no auto-upgrade" settings configured**. 
* **Why this is risky:** "No channel" lacks the modern, granular maintenance exclusions available to release channels. You have very little control over the exact timing of this forced EoS upgrade.

---

### 2. Options to Prepare

To avoid disruptive, unpredictable force-upgrades during business hours, you should take control of the upgrade lifecycle before the EoS date arrives.

#### Step 1: Migrate your "No channel" cluster immediately
**Never stay on "No channel" approaching EoS.** Move this cluster to the **Regular** channel (if you want automated lifecycle management) or the **Extended** channel (if you want to delay the upgrade and maintain manual control over minor versions).
```bash
# Migrate to Extended channel to buy more time and avoid the immediate EoS force-upgrade
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```
*(Note: If you have existing legacy maintenance exclusions, add a temporary 30-day `"no_upgrades"` exclusion during the transition).*

#### Step 2: Check your exact EoS dates and targets
GKE provides a specific API to check exactly when standard and extended support ends for your specific clusters, and what version they are targeted to upgrade to. Run this for each cluster:
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```
Look for `endOfStandardSupportTimestamp`, `endOfExtendedSupportTimestamp`, and `minorTargetVersion`.

#### Step 3: Proactively schedule the 1.30 → 1.31 upgrade
Don't wait for the forced EoS upgrade. Plan a controlled upgrade during your preferred off-peak hours. 

For your **Regular** and **No Channel** (soon to be migrated) clusters:
1. **Set a Maintenance Window:** Ensure the clusters have a recurring maintenance window configured for off-peak hours. If GKE forces the upgrade, it will at least attempt to respect this window.
2. **Execute a Manual Upgrade:** The safest path is to manually trigger the upgrade to 1.31 during a planned maintenance window before the EoS date hits.

```bash
# 1. Upgrade the control plane to 1.31
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31

# 2. Upgrade the node pools (Standard clusters only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31
```

#### Step 4: Use a 30-day exclusion if you are out of time
If the Regular channel EoS date is next week and you are in a critical business period (e.g., a code freeze), you can apply a one-time, 30-day "No upgrades" exclusion. This will block the EoS force-upgrade, but only for a maximum of 30 days.

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "eos-delay-freeze" \
  --add-maintenance-exclusion-start-time "2023-10-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2023-10-30T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Summary Recommendation
1. **Migrate** the 1 "No channel" cluster to the Extended channel today so it doesn't get force-upgraded unexpectedly.
2. **Plan** a manual upgrade to 1.31 for the 3 Regular channel clusters during your next maintenance window.
3. **Leave** the 2 Extended channel clusters as-is for now, as they are protected from immediate EoS by the 24-month extended support window, but schedule their 1.31 minor upgrades in your upcoming quarterly planning.
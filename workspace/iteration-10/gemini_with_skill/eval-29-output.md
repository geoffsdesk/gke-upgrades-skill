To achieve this exact level of control over your GKE cluster upgrades, you will use a combination of **Persistent Maintenance Exclusions** (to block minor upgrades indefinitely) and **Fixed-window Maintenance Exclusions** (to block all changes during code freezes and Black Friday/Cyber Monday).

### Prerequisite: Release Channels
To use these advanced exclusion scopes, your clusters **must be enrolled in a Release Channel** (Regular, Stable, or Extended). If your clusters are on the legacy "No channel" configuration, you must migrate them to a release channel first, as "No channel" does not support blocking minor upgrades or persistent exclusions. 

---

### Configuration Runbook

Here are the exact `gcloud` commands to configure your cluster. Replace `CLUSTER_NAME` and `REGION` (or `--zone ZONE` if zonal) with your specific details.

#### 1. Prevent Minor Upgrades (Ongoing Policy)
To ensure minor version upgrades never happen without your explicit approval, use the `no_minor_or_node_upgrades` scope tied to the version's End of Support (EoS) date. 

This is the recommended approach for maximum control: it blocks automated minor version bumps and node upgrades, preventing version skew between your control plane and nodes, but **still allows automated control plane security patches**.

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "block-minor-and-node-upgrades" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades"
```
*Note: Because this uses the `--add-maintenance-exclusion-until-end-of-support` flag, the exclusion will automatically track your current version's End of Support date and will auto-renew whenever you manually initiate a minor upgrade.*

#### 2. June Code Freeze (Strict Lock)
During a true code freeze, you typically want zero disruptions—including security patches. The `no_upgrades` scope blocks **all** upgrades (patch, minor, and node). 

*Constraint:* GKE limits `no_upgrades` exclusions to a maximum of **30 consecutive days**. Adjust the dates below to fit your exact June freeze window.

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T00:00:00Z" \
  --add-maintenance-exclusion-scope "no_upgrades"
```

#### 3. Black Friday / Cyber Monday Freeze (Strict Lock)
Similarly, apply a strict 30-day `no_upgrades` exclusion covering your peak retail period in November to guarantee absolute stability.

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-15T00:00:00Z" \
  --add-maintenance-exclusion-scope "no_upgrades"
```

---

### How to execute manual upgrades under this policy

Because you have blocked automated minor upgrades, **you are now responsible for manually initiating minor upgrades** before your current version reaches End of Support. 

**Manual upgrades bypass maintenance exclusions.** When your team is ready to approve and execute a minor upgrade, you simply run the standard upgrade commands. You do not need to delete your exclusions first.

**1. Upgrade the Control Plane:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version TARGET_VERSION
```

**2. Upgrade the Node Pools (Standard clusters only):**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

### Important Warning: End of Support (EoS) Enforcement
GKE's automated lifecycle ultimately enforces security. When a GKE version reaches its End of Support date:
1. The `no_minor_or_node_upgrades` exclusion will expire.
2. GKE will systematically force-upgrade your cluster to the next supported minor version to keep it secure.

**If you need longer than standard support periods (14 months):**
Consider enrolling your production clusters in the **Extended Release Channel**. This channel gives you up to **24 months** of support for a minor version (for versions 1.27+), giving your team maximum flexibility to schedule manual minor upgrades on your own terms while safely delaying EoS enforcement.
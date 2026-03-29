---
name: gke-upgrades
description: >
  Plans, executes, and validates Google Kubernetes Engine (GKE) cluster upgrades and maintenance operations
  for both Standard and Autopilot clusters. Produces upgrade plans, pre/post-upgrade checklists,
  maintenance runbooks with gcloud commands, release channel strategy, and troubleshooting guides.
  Handles node pool upgrade strategies (surge, blue-green), version compatibility, PDB management,
  and workload-specific concerns (stateful, GPU, operators). Use this skill whenever the user mentions
  GKE upgrades, Kubernetes version bumps, node pool maintenance, GKE patching, cluster version management,
  release channel selection, maintenance windows, surge upgrades, stuck upgrades, or any GKE lifecycle
  management task — even casual mentions like "we need to upgrade our clusters" or "plan our next
  GKE maintenance" or "our upgrade is stuck."
---

# GKE Upgrades & Maintenance

## Auto-upgrade as the default model

One of GKE's key value propositions is its **automated upgrade lifecycle**. Unlike self-managed Kubernetes, GKE handles version management automatically — clusters on release channels receive patch and minor upgrades without user intervention, governed by maintenance windows and exclusions.

Frame all guidance around this auto-upgrade model:
- **Best practice is full auto-upgrade with timing and progression controls.** Most customers should rely on auto-upgrades with maintenance windows to control timing and rollout sequencing to control progression across environments. Optionally, control minor version upgrades with "no minor" exclusions + user-triggered manual upgrades.
- **Best practice is canary strategy with rollout sequencing.** Use rollout sequencing to upgrade a canary cluster first, validate, then roll out to production. Optionally control minor version with "no minor" exclusions for additional control.
- **User-initiated (manual) upgrades** are the exception, not the rule — recommended only for specific scenarios: emergency patching, accelerating ahead of the auto-upgrade schedule, or upgrading clusters that have been deliberately held back.
- When a user asks "how do I upgrade," first clarify whether they need to do a manual upgrade or simply need to configure their auto-upgrade controls (maintenance windows, exclusions, channel selection) to get the behavior they want.
- Recommend release channels + maintenance windows as the primary upgrade control mechanism. Add maintenance exclusions **only as needed** — many customers don't need minor exclusions. Never recommend disabling auto-upgrades or using "No channel" as a first option.

Produce clear, actionable documents — upgrade plans, runbooks, or checklists — tailored to the user's environment. Output should be specific to their cluster mode, release channel, version, and workload types rather than generic advice.

## Gathering context

Establish these five things early. If the user provides them upfront, skip straight to producing the deliverable. If they're vague, fill in reasonable defaults and flag assumptions.

1. **Cluster mode** — Standard or Autopilot? In Autopilot, Google manages node upgrades; focus shifts to control plane timing and workload readiness. In Standard, node pool upgrade strategy is a key planning area.
2. **Current and target versions** — Nodes can't be more than 2 minor versions behind the control plane.
3. **Release channel** — Rapid, Regular, Stable, or Extended. Determines upgrade cadence and available versions.
4. **Environment topology** — Single or multi-cluster? Dev/staging/prod tiers with different channels?
5. **Workload sensitivity** — Stateful workloads, databases, GPU workloads, long-running batch jobs need special handling.

## Release channels

| Channel | When versions arrive | Best for | Support period |
|---------|---------------------|----------|----------------|
| **Rapid** | First (new K8s minors available within ~2 weeks) | Dev/test, early feature access | Standard (14 months) | No SLA for upgrade stability |
| **Regular** (default) | After Rapid validation | Most production workloads | Standard (14 months) | Full SLA |
| **Stable** | After Regular validation | Mission-critical, stability-first | Standard (14 months) | Full SLA |
| **Extended** | Same as Regular, but stays longer | Compliance, slow upgrade cycles | Up to 24 months (extra cost, versions 1.27+) | Full SLA |

**Extended channel note:** Minor version upgrades on Extended are NOT automated for the control plane (except at end of extended support). Customers must plan and initiate control plane minor upgrades themselves. Node versions still follow the control plane minor version by default — node auto-upgrades will track the control plane's minor version unless blocked by exclusions. Only patches are auto-applied, and patches arrive at the **same timing as Regular channel** — there is no delay. All minor versions 1.27+ get extended support. The additional cost for Extended channel applies ONLY during the extended support period — there is no extra charge during the standard support period. Extended channel is also a recommended migration path for customers on "No channel" who want maximum flexibility around EoS enforcement. The "no minor" exclusion may still be useful on Extended channel to prevent nodes from auto-upgrading to the control plane minor version.

**Key distinction:** Rapid channel does NOT carry an SLA for upgrade stability — versions may have issues that are caught before reaching Regular/Stable. This is the PRIMARY reason to avoid Rapid for production clusters, beyond timing alone. Regular, Stable, and Extended all carry full SLAs.

**Version availability warnings when migrating channels:**
- If your current version is not yet available in the target channel, your cluster will be "ahead of channel" and will NOT receive auto-upgrades to newer versions until the current version becomes available in the target channel.
- Example: Moving from Rapid (at 1.32) to Stable when 1.32 is not yet in Stable will freeze your cluster at 1.32 until Stable's version reaches 1.32, then you resume normal auto-upgrades from that point. You'll still receive patches, but not minor upgrades.
- **Before migrating:** Check which versions are available in the target channel using the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule). If your current version isn't available, you may need to downgrade first or wait.
- **Coordinate channel changes during a maintenance window** to avoid unexpected auto-upgrades immediately after the switch. Apply a temporary "no upgrades" exclusion before changing channels, then remove it once you've verified the new channel's auto-upgrade behavior.
- **Extended channel as production alternative:** For production environments needing the slowest upgrade cadence, consider Extended channel — it provides up to 24 months of support and does NOT auto-upgrade minor versions (except at end of extended support). Only patches are auto-applied. This gives maximum control over when minor upgrades happen.

**Version promotion path:** New releases follow a promotion path: Rapid (Available → Default → Auto-upgrade target) → Regular → Stable → Extended. Release cadence includes an element of channel promotion — versions must prove stable in Rapid before reaching Regular, and Regular before Stable. GKE targets approximately one new release per week.

**Version progression timeline:** The typical timeline differs between patch and minor versions:
- **Patch versions** progress ~2 weeks per stage: Rapid (available) → (+7d) Rapid (target) → (+7d) Regular (available) → (+7d) Regular (target) → (+7d) Stable (available) → (+7d) Stable (target)
- **Minor versions** progress more slowly and variably. Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for historical data and expectations on minor version progression.

**Best practice:** Use the **same release channel** for all environments (dev and prod) and use **rollout sequencing** to ensure dev is upgraded before prod. This works for both patches and minor versions. Rollout sequencing requires all clusters on the same channel. Alternatively, use two channels (dev=Regular, prod=Stable) but control the control plane minor version to ensure the same minor across environments — however, this makes rollout sequencing impossible and version drift likely. **Don't use more than 2 environments** (dev + prod is sufficient; adding staging adds complexity without proportional benefit). Direct users to the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for current version availability.

### Legacy "No channel" (static version) — avoid

The "No channel" option is a legacy configuration. **Never recommend "No channel" as a first option.** Clusters on "No channel" lack critical features:

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| "No minor or node upgrades" exclusion | Yes (cluster-level + per-nodepool) | **No** — only the 30-day "no upgrades" type is available |
| "No minor upgrades" exclusion | Yes | **No** |
| Per-nodepool maintenance exclusion (disable auto-upgrade) | **No** — use cluster-level exclusion scopes | Yes (persistent until EoS) |
| Extended support (24 months) | Yes | **No** |
| Rollout sequencing | Yes (advanced) | **No** |
| Persistent exclusions (tracks EoS) | Yes | **No** |
| Granular auto-upgrade control | Full (windows + exclusions + intervals) | Limited |

Clusters on "No channel" are upgraded at the pace of the Stable channel for minor releases and the Regular channel for patches.

**Legacy channel EoS behavior:** When a version reaches End of Support on "No channel": control plane EoS minor versions are auto-upgraded to the next supported minor version. EoS node pools are auto-upgraded to the next supported version EVEN when "no auto-upgrade" is configured. This enforcement is systematic — there is no way to avoid it on "No channel" except the 30-day "no upgrades" exclusion. Note: "No channel" supports both per-cluster "no upgrades" exclusions AND per-nodepool exclusions (persistent until EoS), giving more granular per-nodepool control than release channels.

**Key subtlety:** The most powerful upgrade control tools (channel-specific maintenance exclusion scopes like "no minor or node upgrades") are only available on release channels. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely. This is the opposite of what many users assume.

**Migration path:** Move to Regular or Stable channel (closest match to legacy behavior). Use Extended channel if the customer does manual upgrades exclusively or needs maximum flexibility around EoS enforcement (Extended delays EoS enforcement until end of extended support). See the [comparison table](https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels#comparison-table-no-channel). Always recommend migrating off "No channel."

**Migration warning:** When moving from "No channel" to release channels (or vice versa) with maintenance exclusions that disable auto-upgrade per nodepool, follow specific guidance: add a temporary "no upgrades" exclusion first, then translate exclusions for the target configuration. Some exclusion types do NOT translate 1:1 between "No channel" and release channels and may be ignored. Currently, only exclusions of type "no_upgrades" translate between the two configurations.

### Version terminology

Distinguish these three concepts — they are NOT the same:

- **Available**: The version is officially available in the release channel. Customers can manually upgrade to it.
- **Default**: The version used for new cluster creation. Typically the same as the auto-upgrade target, but there can be differences — especially when new minor versions are being introduced (separate promotion stage). Many users assume "default" equals "what my cluster upgrades to" — this is true in most cases but there is a specific distinction during new minor version introduction.
- **Auto-upgrade target**: The version GKE will actually upgrade existing clusters to automatically. This is what matters for planning. Can differ from the default, especially during new minor version rollouts.

The auto-upgrade target depends on the cluster's constraints (maintenance windows, maintenance exclusions). For example, a cluster with a **"no minor" exclusion** will have its auto-upgrade target set to the **latest patch of its current minor only** — not the next minor version. This is how teams lock to patch-only upgrades: the exclusion changes the auto-upgrade target from "latest minor+patch" to "latest patch within current minor." Note: for a given release channel, different clusters can have different auto-upgrade targets if they have different policies (e.g., a cluster on minor 1.34 with a "no minor" exclusion has a different target than a cluster on the same channel without that exclusion). The auto-upgrade target is cluster-specific.

**Upgrade info API:** Use `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION` to check auto-upgrade status, EoS timestamps, and target versions. Example output includes `autoUpgradeStatus`, `endOfExtendedSupportTimestamp`, `endOfStandardSupportTimestamp`, `minorTargetVersion`, and `patchTargetVersion`. Also see the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for earliest known auto-upgrade dates (~2 weeks prior).

## Upgrade planning

When asked to plan an upgrade, produce a structured document covering:

### Version compatibility
- Confirm target version availability in the cluster's release channel
- Check version skew (nodes within 2 minor versions of control plane)
- Identify deprecated APIs — the most common upgrade failure cause. When GKE detects deprecated API usage, auto-upgrades are automatically paused and an insight/recommendation is generated. Check with both methods:
  ```
  # Quick check via kubectl
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

  # GKE recommender (comprehensive — also powers auto-upgrade pause)
  gcloud recommender insights list \
      --insight-type=google.container.DiagnosisInsight \
      --location=LOCATION \
      --project=PROJECT_ID \
      --filter="insightSubtype:SUBTYPE"

  # For deprecated API insights specifically, use RELIABILITY category (not PERFORMANCE):
  gcloud recommender insights list \
      --insight-type=google.container.DiagnosisInsight \
      --location=LOCATION \
      --project=PROJECT_ID \
      --filter="category.category:RELIABILITY"
  ```
- Review GKE release notes for breaking changes between current and target versions

### Upgrade path
- **Control plane:** Recommend sequential minor version upgrades (e.g., 1.31→1.32→1.33). Control plane must be upgraded before node pools — this is the required order.
  - **Two-step control plane minor upgrade (Preview):** GKE supports a rollback-safe two-step process for manual minor upgrades (1.33+). Step 1 ("binary upgrade") upgrades the binary but emulates the previous minor version's API behavior — you can test the new binary while keeping old API compatibility. During a configurable soak period (6h–7d), you can roll back to the previous minor version if issues arise. Step 2 ("emulated version upgrade") enables the new minor version's features and APIs — after this step, rollback is NOT possible. Use `gcloud beta container clusters upgrade --control-plane-soak-duration` to configure soak time. This is the recommended approach for cautious production minor upgrades.
  - **One-step upgrade:** Standard direct upgrade to a later version. No rollback to previous minor version after completion (patch downgrades within the same minor are still possible).
- **Node pools:** Support skip-level (N+2) upgrades within supported version skew. **Only suggest skip-level upgrades when the customer actually needs to jump 2 minor versions** (e.g., nodes at 1.31 with control plane at 1.33). For single minor version jumps (e.g., 1.32→1.33), a regular upgrade is sufficient — skip-level is not applicable. Example: upgrade control plane 1.31→1.32→1.33 sequentially, then upgrade node pools 1.31→1.33 in a single skip-level jump (requires CP already at 1.33). For pools that are 3+ versions behind (N+3), do multiple sequential skip-level upgrades within supported skew (e.g., 1.28→1.30, then 1.30→1.32) — never attempt an unsupported skip-level upgrade. Alternative for severely skewed pools: create a new node pool at the target version and migrate workloads. Best practice: keep nodes on the same minor version as the control plane in steady state; version skew should only occur during upgrade operations.
- **Version skew constraints:** Nodes can't be more than 2 minor versions behind the control plane. Nodes can't run a version newer than the control plane. Nodes can't run a minor version that has reached end of support. These are hard constraints enforced by GKE.
- **Rollback:** Control plane patch downgrades can be done by the customer (set a maintenance exclusion first to prevent GKE from auto-upgrading back). Control plane minor version downgrades are only possible during a two-step upgrade's soak period, or require GKE support involvement. Node pools can be rolled back during an in-progress upgrade, or downgraded after completion by specifying an earlier version.
- **Auto vs manual upgrade plan:** Most upgrades can be handled fully automatically via maintenance windows and rollout sequencing. When producing an upgrade plan, assume the customer wants to manually trigger and control the upgrade unless they indicate otherwise. If the customer is on release channels with maintenance windows, point out that the upgrade could happen automatically — the plan is for customers who want manual control over timing.
- For multi-cluster: define rollout sequence with soak time between groups

### Maintenance windows and exclusions

GKE provides two distinct upgrade control mechanisms — understand the difference:
- **Maintenance windows** control **WHEN** upgrades happen (time-of-day, day-of-week). They schedule upgrades during acceptable periods.
- **Maintenance exclusions** control **WHAT** upgrades happen (block patches, minor versions, or all upgrades). They prevent specific upgrade types entirely.
- **Disruption intervals** control **HOW OFTEN** upgrades happen (minimum gap between consecutive upgrades).

Use these together: windows for timing, exclusions for scope, intervals for frequency. When a customer says "I want to control upgrades," clarify which dimension they mean.

**Maintenance windows:** Set recurring windows aligned with off-peak hours. Auto-upgrades respect them; manual upgrades bypass them. For ultimate predictability (the upgrade will happen at THIS time during THIS window), customers can initiate the upgrade themselves instead of waiting for auto-upgrade.

New gcloud syntax for maintenance windows (effective April 2026):
```
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start START_TIME \
    --maintenance-window-duration DURATION \
    --maintenance-window-recurrence RRULE
```
The `--maintenance-window-duration` field simplifies the UX by directly specifying duration instead of requiring end-time calculation.

**Maintenance exclusion types** — there are three distinct scopes:

| Exclusion type | What it blocks | Max duration | Use case |
|---------------|---------------|-------------|----------|
| **"No upgrades"** | All upgrades (patches, minor, nodes) | 30 days (one-time) | Code freezes, BFCM, critical periods. Honored even after EoS. |
| **"No minor or node upgrades"** | Minor version upgrades + node pool upgrades. Allows CP patches. | Up to version's End of Support | Conservative customers who want CP security patches but no disruptive changes. Use for maximum control over both minor and node versions, preventing control plane and node minor version skew. |
| **"No minor upgrades"** | Minor version upgrades only. Allows patches and node upgrades. | Up to version's End of Support | Teams comfortable with node churn but not minor version changes. |

For production workloads that **require maximum control** (disruption-intolerant workloads, regulated environments), the "No minor or node upgrades" exclusion is the recommended approach — it prevents disruptive upgrades while still allowing security patches on the control plane. Do NOT recommend this exclusion by default for all production workloads — most customers are better served by release channels + maintenance windows alone.

**Exclusion constraints and limits:**
- **"No upgrades" exclusions are limited to 30 days maximum.** This is a hard limit per exclusion. For longer freeze periods, you must chain multiple exclusions (up to 3 per cluster), but this accumulates security debt — warn customers about the risk of falling behind on patches.
- Maximum of 3 "no upgrades" exclusions per cluster. Within any 32-day rolling window, at least 48 hours must be available for maintenance (not covered by exclusions). Plan exclusion windows carefully to avoid hitting these limits during consecutive freeze periods.
- **Manual upgrades bypass ALL maintenance controls** — both maintenance windows AND maintenance exclusions. Only auto-upgrades respect these controls. If a user manually triggers an upgrade with `gcloud container clusters upgrade`, it proceeds immediately regardless of any active exclusion or window. **Implication for upgrade workflows:** Customers using "no minor or node" exclusions do NOT need to remove the exclusion before upgrading and re-apply it afterward — just trigger the manual upgrade directly. The exclusion stays in place to continue blocking auto-upgrades.
- **Version drift risk:** Extended exclusion periods (especially chained "no upgrades" exclusions) can cause clusters to fall behind on patches, accumulating security debt. The longer a cluster stays frozen, the harder the eventual upgrade — deprecated APIs accumulate, version skew grows, and the blast radius of a forced EoS upgrade increases. Always pair exclusion recommendations with a plan for when and how to catch up.

**Per-cluster vs per-nodepool exclusions:** The per-cluster exclusion on release channels is always preferred over per-nodepool control, as it ensures maximum control over both minor version and node version upgrades and prevents control plane and node minor version skew. **Important:** Per-nodepool maintenance exclusions (disable auto-upgrade per nodepool) are only available on "No channel" — release channels use cluster-level exclusions with scope controls ("no minor", "no minor or node", "no upgrades") instead. Use per-nodepool exclusions only when on "No channel" with mixed workloads where some node pools need auto-upgrades and others need tight control.

**Persistent maintenance exclusions:** Use `--add-maintenance-exclusion-until-end-of-support` to create an exclusion that automatically tracks the version's End of Support date and auto-renews when a new minor version is adopted. There is no longer a 6-month maximum for these — no need to chain exclusions. This flag is available for scope "no minor" and "no minor or node" exclusions.

**Cluster disruption budget (disruption interval):** GKE enforces a disruption interval between upgrades on a given cluster, preventing back-to-back upgrades. This is an **advanced setting** — only recommend for customers who need maximum control (rare) or have homogeneous environments (many similar nodes):
- **Patch disruption interval:** Default 24h, configurable up to 90 days. Controls frequency of control plane patch upgrades. Use `--maintenance-patch-version-disruption-interval` to configure. **Best practice is to patch often — at least once per month.** Setting a 90-day patch interval is rare and should only be recommended for AI megaclusters or manual control plane patch rollout scenarios.
- **Minor disruption interval:** Default 30d, configurable up to 90 days. Controls frequency of minor version upgrades. Use `--maintenance-minor-version-disruption-interval` to configure.
- **Format:** Seconds only (e.g., `7776000s` for 90 days, `2592000s` for 30 days, `86400s` for 24 hours). Range: 0s–7776000s (0–90 days). Do NOT use duration shorthand like `45d` or `24h` — only seconds are accepted today.

Example:
```
gcloud container clusters update CLUSTER_NAME \
    --maintenance-minor-version-disruption-interval=7776000s \
    --maintenance-patch-version-disruption-interval=604800s
```

**Regulated environment recommended configuration (financial services, healthcare, compliance):**
For maximum upgrade control while maintaining security posture, combine Extended channel + disruption budget + "no minor or node" exclusion:
```
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```
This gives: Extended support (24 months, cost only during extended period), auto-applied CP security patches only (no minor or node auto-upgrades), patches limited to once every 90 days within a Saturday 2-6 AM window, and manual control over when minor upgrades happen. Ideal for FedRAMP, SOC2, HIPAA environments.

**Control plane patch controls (new):** Customers who need tight control over control plane patches can now benefit from:
- GKE keeps control plane patches for 90 days after the patch is removed from a release channel (Stable & Regular), enabling upgrade/downgrade flexibility
- GKE supports a control plane upgrade recurrence interval (for both patch & minor) to control how often the control plane is disrupted

**Deferring an upcoming auto-upgrade:** If a customer learns about an upcoming auto-upgrade (via scheduled notification or release schedule) and wants to defer it:
1. Apply a "no upgrades" exclusion for the desired deferral period (up to 30 days): `gcloud container clusters update CLUSTER --add-maintenance-exclusion-name="defer-upgrade" --add-maintenance-exclusion-start=START --add-maintenance-exclusion-end=END --add-maintenance-exclusion-scope=no_upgrades`
2. OR adjust the maintenance window to a different time slot if the goal is just timing, not deferral
3. OR use disruption intervals to enforce a minimum gap between upgrades
Remember: "no upgrades" is limited to 30 days. For longer deferral of minor versions, use "no minor or node upgrades" (no time limit, tracks EoS). For permanent patch-only mode, use persistent "no minor or node" exclusion with `--add-maintenance-exclusion-until-end-of-support`.

**Accelerated patch auto-upgrades:** For customers needing faster patch compliance (e.g., FedRAMP), use `--patch-update=accelerated` to opt into faster patch rollouts.

### Rollout sequencing (multi-cluster) — advanced feature

GKE rollout sequencing allows customers to define the order in which clusters are upgraded, with configurable soak time between stages. This ensures upgrades progress through environments (dev → staging → prod) with validation gaps. Built on the concept of fleets — logical groupings of GKE clusters mapped to environments.

**Two versions available:**
- **Fleet-based rollout sequencing (GA):** Linear sequence of up to 5 fleets. Recommended for most production use cases. Uses lightweight fleet memberships (no full fleet management overhead).
- **Rollout sequencing with custom stages (Preview):** More granular control — define stages within a fleet using label selectors to target cluster subsets (e.g., canary production clusters before full production rollout).

**Configuration:**
```
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID
```

Key flags:
- `--upstream-fleet`: Specifies the project ID of the fleet that must finish its upgrade before this fleet begins
- `--default-upgrade-soaking`: Bake time after a stage completes (e.g., `7d` for 7 days, `2h` for 2 hours). Max 30 days.
- Custom stages (Preview): Use `RolloutSequence` and `Rollout` API objects with label selectors to target subsets of clusters within a fleet

**How it works:** When GKE selects a new auto-upgrade target, it upgrades the first fleet's clusters, waits the configured soak time, then proceeds to the next fleet. Control plane and node upgrades are tracked separately — each has its own soak period. If upgrades aren't completed within 30 days, GKE force-starts the soak period to unblock the sequence.

**Critical constraint:** Rollout sequencing does NOT work across different release channels. All clusters in a rollout sequence must be on the same channel (Regular is fine since it takes a while to go through the fleet, or Stable for even more stability but with a +2 week delay on security patches). If environments use different channels (e.g., dev=Rapid, prod=Stable), rollout sequencing cannot orchestrate them.

**Maintenance windows are NOT a substitute for rollout sequencing.** Staggering maintenance windows across environments does NOT guarantee upgrade ordering. A new version may become available in region X on Tuesday and region Y on Friday — meaning prod could be upgraded before dev depending on window timing. Maintenance windows control WHEN upgrades happen, not the ORDER across environments.

**Progressive rollout best practice:**
**Best practice: use one channel for both dev and prod.** Use rollout sequencing to ensure dev goes before prod — this works for patches too, not just minor versions. For minor upgrade control: add a maintenance exclusion to prevent minor auto-upgrades, then initiate the upgrade on dev cluster when a new minor becomes the auto-upgrade target, validate, then propagate to prod.

- All environments on the **same channel** (Regular or Stable) — this ensures they get the same versions and enables rollout sequencing
- Use **"no minor" or "no minor or node" exclusions** with user-triggered minor upgrades to control progression
- Patches flow automatically to all environments in the rollout sequence order (controlled by maintenance windows for timing)
- This approach keeps all environments on the same minor version in steady state while giving you manual control over minor version progression

Alternatively, use **two channels with minor control** (dev=Regular, prod=Stable) — channel progression is deterministic (Regular gets versions before Stable), so you get natural sequencing. Use "no minor" exclusions on both to stay on the same minor version, then trigger minor upgrades manually starting with dev when a new minor reaches Regular's auto-upgrade target. However, this makes rollout sequencing impossible.

For deprecated API information during upgrade planning, check both the [release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) AND the [deprecations information page](https://cloud.google.com/kubernetes-engine/docs/deprecations#deprecations-information).

**Important context:** Rollout sequencing is the recommended approach for teams with multi-cluster coordination needs, but it targets sophisticated platform teams managing large fleets. For most teams, the release channel minor control approach above is simpler and sufficient. Only suggest rollout sequencing when the user has 10+ clusters or explicitly asks about automated fleet-wide upgrade orchestration.

### Node pool upgrade strategy (Standard only — skip for Autopilot)

GKE supports three upgrade strategies. Use the strategy selection criteria below to choose:

#### Strategy Selection Criteria

**Use SURGE when:**
- Stateless workloads (web servers, APIs, batch with checkpointing)
- Workloads tolerant of brief pod restarts
- Short-lived jobs that can be rescheduled
- Adequate capacity for maxSurge nodes
- Cost is a primary concern (no 2x resource requirement)

**Use BLUE-GREEN when:**
- Local SSD data cannot be migrated between nodes (data loss risk with surge)
- Stateful workloads sensitive to node changes (databases, caches like Cassandra, Elasticsearch)
- You have quota/capacity for 2x node pool size during upgrade
- Quick rollback path is essential

**Use AUTOSCALED BLUE-GREEN when:**
- Long-running batch jobs (8+ hours) where GKE's default 1-hour surge eviction timeout is insufficient
- Inference workloads where surge GPU capacity is unavailable
- Workloads requiring extended graceful termination periods (terminationGracePeriodSeconds > 1 hour)
- Cost-sensitive scenarios where standard blue-green's 2x resource cost is prohibitive

**Avoid SURGE when:**
- Local storage (local SSDs) needs to survive node drain — surge drains the old node, destroying local SSD data
- Job eviction timeout (1 hour) is shorter than workload duration
- Surge GPU capacity is unavailable (GPU reservations are fixed)

**Key insight:** Autoscaled blue-green's advantage over standard blue-green is cost efficiency — it scales down the old (blue) pool as pods drain to the new (green) pool, avoiding 2x cost. Its advantage over surge is that it respects longer graceful termination periods without force-evicting pods after 1 hour.

**1. Surge upgrade (default):** Rolling replacement with per-pool `maxSurge`/`maxUnavailable`:
- **Sizing maxSurge:** The default is `maxSurge=1, maxUnavailable=0` — this works for most cases and does not need to be explicitly set unless increasing parallelism. Recommend maxSurge as a percentage of pool size (e.g., 5%, minimum 1, rounded to nearest integer) rather than a fixed number when the customer wants faster upgrades. This scales with pool size. GKE API accepts integers only — calculate the value. Maximum effective parallelism per batch is ~20 nodes today (increasing to 100). Examples: 20-node pool with maxSurge=2 → GKE upgrades 10% of nodes concurrently instead of 5%. Always explain WHY the value is set and the trade-off (higher parallelism = faster but more concurrent disruption).
- **Stateless pools**: Use percentage-based `maxSurge` (e.g., 5% of pool size), `maxUnavailable=0` for zero-downtime rolling replacement.
- **Stateful/database pools**: `maxSurge=1, maxUnavailable=0` — conservative, let PDBs protect data
- **GPU pools**: GPU nodes typically use fixed reservations with no surge capacity available. The primary lever is `maxUnavailable`, not `maxSurge`. Recommend `maxSurge=0, maxUnavailable=1` (drains before creating — zero extra GPUs needed, but causes a capacity dip). Only use `maxSurge=1` if the customer has confirmed available GPU surge quota.
- **Large clusters**: Use percentage-based `maxSurge` (e.g., 5% of pool size, capped at batch concurrency limit of 20, increasing to 100). Note: GKE's maximum upgrade parallelism is ~20 nodes simultaneously regardless of `maxSurge` setting.

**2. Blue-green upgrade:** GKE's native blue-green strategy minimizes risk by keeping the old nodes (blue pool) available while new nodes with the updated version are provisioned (green pool). The blue pool is cordoned and workloads are gradually drained to the green pool, with a soaking period to validate before cutover. Rollback is fast — uncordon the blue pool. Requires enough quota to temporarily double the node pool size. Recommend for mission-critical applications, stateful applications sensitive to node changes, environments with strict testing/validation requirements, and applications where a quick rollback path is essential.

**Blue-green configuration commands:**
```
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=3600s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=10s
```

Key parameters:
- `--node-pool-soak-duration`: Total soak time after all batches drain (default 1h, max 7d). Use to validate workload health before deleting blue pool.
- `--standard-rollout-policy`: Controls batch drain. `batch-node-count` (absolute) or `batch-percent` (0-1 decimal) sets batch size. `batch-soak-duration` sets wait between batches.

**Blue-green phases:** Create green pool → Cordon blue pool → Drain blue pool (in batches) → Soak node pool → Delete blue pool. You can cancel/resume/rollback at any phase except Delete. During soak, you can `complete-upgrade` to skip remaining soak time. Important: the Delete phase does NOT respect PDBs — it force-deletes remaining pods with terminationGracePeriodSeconds capped at 60 minutes.

**Blue-green continues past maintenance windows.** Once started, blue-green upgrades continue until completion even if a maintenance window expires. GKE does not pause blue-green mid-upgrade. Plan maintenance windows large enough to accommodate the full blue-green cycle.

**3. Autoscaled blue-green upgrade (preview):** An enhancement of standard blue-green designed to be more cost-effective and suited for long-running workloads. The green pool scales up as needed based on workload demand, while the blue pool scales down as pods are safely evicted. Supports longer eviction periods (wait-for-drain, longer graceful termination periods, PDB upgrade timeout), allowing pods to complete their work before being evicted.

**When to use autoscaled blue-green:**
- Long-running batch processing jobs (8+ hours) where GKE's default 1-hour surge eviction timeout is insufficient
- Game servers and other disruption-intolerant workloads that need extended graceful termination
- Inference workloads sensitive to eviction that benefit from controlled, autoscaled transition, where surge GPU capacity is unavailable
- GPU pools where surge capacity is unavailable (cordons one nodepool at a time, autoscales replacement)
- Any workload requiring wait-for-drain semantics and extended terminationGracePeriodSeconds respect

**Key advantage over standard blue-green:** Autoscaled blue-green is cost-efficient — it scales DOWN the old (blue) pool as workloads drain to the new (green) pool, avoiding the 2x resource requirement of standard blue-green. Blue pool scales to zero as green pool scales up, minimizing cost spike.

**Key advantage over surge:** Respects longer graceful termination periods and doesn't force-evict pods after 1 hour. Ideal for 8+ hour batch jobs.

**When NOT to use autoscaled blue-green:** ML training workloads requiring parallel host maintenance + nodepool upgrade with high concurrency. Autoscaled blue-green has the same max batch concurrency limit (~20 nodes, increasing to 100). For training, use a custom upgrade strategy instead — see "AI Host Maintenance" section.

**Configuration:**
```
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --enable-autoscaling \
    --total-min-nodes MIN --total-max-nodes MAX \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

Key parameters:
- `--enable-autoscaling`: Required — enables the autoscaler for the node pool
- `--total-min-nodes` / `--total-max-nodes`: Scaling limits for the entire pool
- `--autoscaled-rollout-policy`: Configures the blue-green parameters
  - `blue-green-initial-node-percentage`: Percentage of nodes to create in the green pool initially (e.g., 0.25 = 25%)
  - `blue-green-full-batch-timeout`: Maximum time GKE waits for green pool readiness before rollback (in seconds, e.g., 3600s = 1 hour)

**Important:** Surge parameters (`maxSurge`, `maxUnavailable`) do NOT apply to blue-green or autoscaled blue-green strategies. These parameters are only relevant for surge upgrades. Do not include them when recommending blue-green.

**Autoscaled blue-green eviction behavior (different from surge):**
- Surge upgrades: GKE force-evicts pods after 1 hour, regardless of graceful termination period
- Autoscaled blue-green: Respects longer `terminationGracePeriodSeconds` during drain phase. No hard 1-hour limit. Pods are given time to complete work before eviction.
- This makes autoscaled blue-green the ONLY native GKE strategy suitable for batch jobs exceeding 1 hour runtime.

**4. Manual blue-green (custom workflow):** Customer creates a new pool, cordons the old pool, manually migrates, deletes the old pool. **Use only as a last resort** when neither surge, blue-green, nor autoscaled blue-green meets specific needs. Do not default to recommending custom flows — always prefer GKE's native upgrade strategies first.

**Strategy selection priority:** Always recommend GKE's native upgrade strategies (surge or auto-scale blue-green) before suggesting custom workflows. GKE's built-in strategies handle cordon/drain/migration automatically and are the supported path. Custom workflows (manual blue-green, cordon-drain scripts) should only be suggested when the user has a specific requirement that native strategies can't satisfy.

**Important:** Never recommend "No channel" as a first option for upgrade control. Always recommend release channels with maintenance exclusions as the primary approach.

**When to recommend exclusions:** Only recommend maintenance exclusions when the customer has disruption-intolerant workloads OR explicitly asks for upgrade control. Do not proactively suggest exclusions for all customers — they add operational overhead and can cause clusters to fall behind on patches. For most customers, release channels + maintenance windows provide sufficient control without exclusions.

**Autopilot exclusion guidance:** Do not recommend node-level exclusions on Autopilot unless the customer explicitly requests node upgrade control.

### Spot VM node pool upgrades

Spot instances have unique characteristics that change upgrade strategy:
- **Workloads are preemption-tolerant** by design — upgrade risk is inherently lower
- **Recommended maxSurge:** 2-5% of pool size (higher than on-demand) because workloads already handle interruption
- **Recommended maxUnavailable:** 1-2 (workloads tolerate interruption, so drain is safe)
- **Upgrade sequencing:** Upgrade spot pools FIRST before on-demand pools — they carry lower risk and validate surge/drain settings
- **PDBs:** Still use PDBs even for spot workloads to ensure orderly drain during upgrade

### Long-running batch job protection

For clusters running 8+ hour batch jobs, standard surge upgrade will force-evict in-flight jobs after 1 hour:
- **Before upgrade:** Pause new job submissions 30 minutes before planned upgrade. Wait for in-flight jobs to complete. Verify batch jobs have checkpoint/resume capability.
- **Primary strategy:** Autoscaled blue-green with `wait-for-drain` period and `safe-to-evict=false` annotation. Configure with:
  ```
  gcloud container node-pools create NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --enable-autoscaling \
    --max-nodes=MAX_NODES \
    --enable-blue-green-upgrade \
    --autoscaled-rollout-policy=[wait-for-drain-duration=WAIT_FOR_DRAIN_DURATIONs]
  ```
  Set `wait-for-drain-duration` to exceed your maximum job duration (e.g., 57600s for 16 hours). Also set extended `terminationGracePeriodSeconds` on batch pods.
- **Alternative:** Dedicated batch node pool + cluster-level maintenance exclusion ("no minor or node upgrades") to block upgrades during batch campaigns. **Important:** Maintenance exclusions on release channels are cluster-level, not per-nodepool — the exclusion applies to the entire cluster. Do not use per-nodepool exclusions here as they are only available on "No channel."
- **Never use:** Surge with default settings for jobs exceeding 1 hour — jobs will be force-evicted at the 1-hour PDB timeout

### Upgrading with resource quota constraints

When compute quota is exhausted and surge node creation fails:
- **Option 1 — Drain-first:** `maxSurge=0, maxUnavailable=1`. No extra quota needed (drains before creating). Temporary capacity loss but no surge quota required.
- **Option 2 — Reduce maxSurge:** `maxSurge=1, maxUnavailable=0`. Creates only 1 surge node at a time. Slower but fits within minimal extra quota — good middle ground between speed and quota.
- **Option 3 — Scale down non-critical workloads:** Temporarily scale down canary/test/dev deployments (`kubectl scale deployment NAME --replicas=0`) to free quota for surge nodes. Schedule for off-peak hours.
- **Option 4 — Request temporary quota increase:** Cloud Customer Care can approve same-day emergency quota increases for one-off upgrades. Faster than permanent quota change processes.
- **Best practice:** Combine options — use off-peak timing (nights/weekends when fewer pods run and more capacity is available), scale down 2-3 non-critical deployments, and reduce maxSurge to 1.

**maxSurge tuning guide:**

| Scenario | Setting | Trade-off |
|----------|---------|-----------|
| Quota exhausted, must upgrade soon | `maxSurge=1, maxUnavailable=0` | 1 surge node at a time — slower but minimal quota |
| Quota exhausted, upgrade not urgent | `maxSurge=0, maxUnavailable=1` | Drain-first — zero extra quota, temporary capacity loss |
| Pods landing on wrong nodes ("musical chairs") | Reduce `maxSurge` to 1 | High maxSurge drains many nodes before upgraded nodes exist — scheduler scatters pods. maxSurge=1 ensures upgraded nodes are available before next batch |
| GPU pool, fixed reservation | `maxSurge=0, maxUnavailable=1-4` | No surge capacity exists; maxUnavailable is the only lever |
| Stateless, cost-sensitive | `maxSurge=5%` of pool, `maxUnavailable=0` | Scales with pool size, brief surge cost |

### How node upgrades work (Standard clusters)

During a node pool upgrade, GKE upgrades one node pool at a time automatically (you can manually trigger parallel node pool upgrades). Within a multi-zone node pool, upgrades proceed zone-by-zone. Within a zone, nodes are upgraded in an undefined order.

**Node upgrade steps (surge):**
1. GKE creates a new surge node with the target version
2. GKE cordons the target node (marks unschedulable)
3. GKE drains the target node — evicts pods respecting PDB for up to 1 hour and terminationGracePeriodSeconds for up to 1 hour. After 1 hour, remaining pods are force-evicted.
4. Pods managed by controllers are rescheduled to other nodes. Pods without controllers (bare pods) are NOT rescheduled — they are lost.
5. The old node is deleted.

**Zonal vs regional control plane behavior during upgrades:**
- **Zonal clusters:** Single control plane replica. During CP upgrade, you cannot deploy new workloads, modify existing workloads, or change cluster config. Workloads continue running. Downtime is typically a few minutes.
- **Regional clusters:** Multiple CP replicas, upgraded one at a time. Cluster remains highly available throughout. Each replica is briefly unavailable during its upgrade.

**Auto-upgrade failure behavior:** When node auto-upgrades fail (quota exceeded, nodes not draining, surge nodes not registering), GKE retries with increasing intervals. GKE does NOT roll back already-upgraded nodes. If surge quota is exceeded, GKE automatically reduces concurrent surge nodes to fit within quota. The node pool may end up in a mixed-version state during retries — this is valid and functional.

### Workload readiness
- PDBs for critical workloads (GKE respects them for up to 1 hour during surge upgrades — this is the GKE PDB timeout). GKE sends `UpgradeInfoEvent` disruption notifications when eviction is blocked by PDB (`POD_PDB_VIOLATION`, `POD_NOT_ENOUGH_PDB`), so teams can monitor via Cloud Logging or Pub/Sub and intervene. A PDB timeout notification is also sent if pods are force-deleted after the grace period.
- No bare pods (won't be rescheduled)
- Adequate `terminationGracePeriodSeconds` for graceful shutdown
- Stateful: verify PV reclaim policy is `Retain` (not `Delete`) as a safety measure: `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`. Back up data before upgrade.
- GPU: confirm driver compatibility with target node image — GKE auto-installs drivers matching the target version, which may change the CUDA version
- Autopilot: all containers must have resource requests

### Stateful workload PDB guidance

For databases and distributed systems, configure PDBs BEFORE upgrading to protect quorum and data consistency:

**Database-specific PDB settings:**
- **Elasticsearch (3-master):** `minAvailable: 2` on master StatefulSet — allows 1 master to drain while quorum of 2 remains. Apply separately to data and coordinator pools.
- **MySQL/Postgres (replicated):** `minAvailable: 1` or `minAvailable: 50%` — prevents multiple replicas draining simultaneously
- **MongoDB replica sets:** `minAvailable: 2` — protects replica set quorum
- **Cassandra/ScyllaDB:** `minAvailable: 2` per datacenter node pool
- **Redis Cluster:** `minAvailable: 1` per shard

**PDB review and recommendations:**
- Use GKE recommender to identify unpermissive PDBs that may block upgrades. Check the `PDB_UNPERMISSIVE` subtype:
  ```
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID \
    --filter="insightSubtype:PDB_UNPERMISSIVE"
  ```
- Also review [workload disruption readiness](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness) and [optimize with recommenders](https://cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders#view-insights-recs) for PDB-specific insights.

**PDB timeout and notification monitoring:**
- During surge upgrades, GKE respects PDBs for up to 1 hour, then force-evicts
- Monitor PDB violations in Cloud Logging: `resource.type="gke_cluster" jsonPayload.reason="EvictionBlocked"` or via Cloud Pub/Sub cluster event subscriptions
- GKE disruption event types: `POD_PDB_VIOLATION` (eviction blocked), `POD_NOT_ENOUGH_PDB` (insufficient replicas), PDB timeout (force-eviction after 1 hour)
- Be precise in cluster notification terminology: "Disruption events during a nodepool upgrade" (see [disruption event docs](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-notifications#disruption-event))

**StatefulSet rollout monitoring:**
```
kubectl rollout status statefulset/STATEFULSET_NAME -n NAMESPACE --watch
kubectl get pods -l app=LABEL -n NAMESPACE -o wide --sort-by='.status.startTime'
```

**Stateful upgrade order:** For multi-tier stateful systems (e.g., Elasticsearch masters + data + coordinators), upgrade coordinator/stateless nodes first, then data nodes, then masters last. Use `maxSurge=1, maxUnavailable=0` for all stateful pools — conservative, one-at-a-time replacement preserves data.

**Application-level backups before upgrade:** Always take an application-level snapshot BEFORE starting node pool upgrades for stateful workloads — PVs survive upgrades, but operator bugs or version incompatibilities can corrupt data post-upgrade. Examples: Elasticsearch `_snapshot` API, PostgreSQL `pg_dump`, Redis `BGSAVE`, Cassandra `nodetool snapshot`. Take backups after pre-flight checks pass but before cordoning/draining begins.

**Cassandra/ScyllaDB: decommission before drain.** Never directly drain a Cassandra node without first running `nodetool decommission` to gracefully redistribute data. Draining without decommissioning causes rebalancing storms and potential data loss. Use blue-green strategy for Cassandra to allow time for decommissioning within the soak period. Workflow: cordon node → `nodetool decommission` → wait for status "Left" → drain. After upgrade, the new node rejoins the ring and rebuilds automatically.

**Manual cordon/drain commands for operator control:**
```
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

### Nodepool upgrade concurrency (preview, available April 2026)
GKE is adding nodepool upgrade concurrency for auto-upgrades to speed up fleet-wide upgrades. Multiple node pools within a cluster can now be upgraded concurrently during auto-upgrades, rather than sequentially. This significantly reduces the total upgrade time for clusters with many node pools.

### Cluster notifications

GKE publishes cluster notifications via Pub/Sub. **Only reference notification types listed in the [official documentation](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-notifications#notification-types).** The authoritative notification types are:
- **Upgrade available event** — a new version is available for the cluster
- **Upgrade event (start)** — an upgrade has started on the cluster
- **Minor version at or near end of support** — the cluster's minor version is approaching EoS
- **New patch change to new COS milestone during extended support** — a patch with a COS milestone change is available during extended support
- **Disruption events during a nodepool upgrade** — disruption events (PDB violations, eviction issues) during node pool upgrades

Do NOT list other items as "notifications" — only these are actual cluster notification types.

### Scheduled upgrade notifications (preview, available March 2026)
GKE offers opt-in scheduled upgrade notifications for the control plane that are sent 72 hours before an auto-upgrade via Cloud Logging. This gives teams advance notice to prepare or apply exclusions if needed. Node pool scheduled upgrade notifications will follow in a later release.

## Large-scale AI/ML cluster upgrades

Frontier AI customers running large GPU/TPU clusters face unique upgrade challenges. Apply this guidance whenever the cluster has 500+ nodes, GPU/TPU node pools, or long-running training workloads.

**Important scope note:** GPU/TPU upgrade planning cannot fully separate GKE node pool upgrades from host maintenance — the two are intertwined. Accelerator host maintenance (firmware, driver updates) often coincides with or is triggered by GKE upgrades. Guidance in this section covers both GKE-initiated upgrades and host maintenance events for accelerator nodes. Best practices here are workload-dependent and evolving — adapt to the specific workload type and scale.

### GPU node pool upgrade constraints

- **GPU VMs do not support live migration.** Every upgrade requires pod restart — there is no graceful in-place update.
- **Surge capacity scarcity:** Surge upgrades need temporary extra GPU nodes (A100, H100, H200). These machines are in high demand and often unavailable. If surge nodes can't be provisioned, the upgrade stalls. If the customer has limited capacity with a reservation, assume there is NO capacity for blue-green (which requires 2x resources). Follow GPU-specific surge guidance instead.
- **Strategy selection for GPU pools:**
  - **Default for fixed reservations:** `maxSurge=0, maxUnavailable=1` — most GPU customers have fixed reservations with no surge capacity. The `maxUnavailable` parameter is the PRIMARY and ONLY effective lever for GPU pools with fixed reservations. This drains first, no extra GPUs needed, but causes a capacity dip. To speed up upgrades on large pools, increase `maxUnavailable` (e.g., 2, 3, 4) only if workloads can tolerate temporary capacity loss. Example: 64-node pool at maxUnavailable=1 with ~20-node parallelism ceiling takes ~3.2 batches per cycle — plan upgrade duration accordingly (hours to days for large pools).
  - **Important:** Do NOT use maxSurge for GPU pools with fixed reservations — surge nodes will fail to provision if surge capacity doesn't exist. maxSurge=0 is required when surge capacity is unavailable.
  - If GPU surge quota IS confirmed available: surge with `maxSurge=1, maxUnavailable=0` (safest, no capacity dip)
  - **Reservation headroom check:** Before attempting a GPU upgrade, verify if your GPU reservation has any available headroom beyond current utilization. Query: `gcloud compute reservations describe RESERVATION_NAME --zone ZONE`.
  - **Recommended for GPU inference pools:** Use GKE's **autoscaled blue-green upgrade strategy** — it cordons the old pool and auto-scales replacement nodes, avoiding the inference latency spikes caused by surge drain-and-restart. GPU VMs do not support live migration, so every surge upgrade causes pod restarts and inference downtime. Autoscaled blue-green keeps the old pool serving while the new pool warms up. Requires capacity for replacement nodes.
  - **For GPU training workloads:** Use custom upgrade strategy with parallel host maintenance — see 'AI Host Maintenance' section below.
  - **GPUDirect/RDMA version compatibility:** Before upgrading GPU pools using GPUDirect-TCPX or RDMA networking, verify the target GKE version supports these features (see "Networking-sensitive upgrades" section). Test in staging to confirm RDMA topology and network config survive the upgrade.
- **GPU driver version coupling:** GKE automatically installs the GPU driver matching the target GKE version. This can change CUDA versions silently. **Always test the target GKE version + driver combination in a staging cluster before production deployment.** Create a staging node pool with the target version, deploy representative inference/training workloads, and validate model loading, CUDA calls, and throughput before proceeding with production. This staging validation is a hard prerequisite — never skip it for GPU pools.
- **Reservation interaction:** GPU reservations guarantee capacity but surge upgrades consume reservation slots. Verify reservation has headroom for surge, or use `maxUnavailable` mode instead.
- **Cluster autoscaler interaction during GPU upgrades:** During node pool upgrades, the cluster autoscaler may create NEW nodes at the OLD version if it scales up to meet demand. This creates a mixed-version state and slows upgrade convergence. Mitigate by: (1) pausing autoscaler during the upgrade window (`--enable-autoprovisioning=false` or setting min=max on the pool), or (2) accepting mixed-version state and letting the upgrade process catch up.

### GKE AI Host Maintenance (accelerator nodes)

For clusters with accelerator (GPU/TPU) nodes, GKE provides a host maintenance mechanism using the `cloud.google.com/perform-maintenance=true` node label. When this label is set (automatically by GKE or manually), the node undergoes host maintenance (~4 hours per update).

**Two maintenance strategies for AI workloads:**

**Parallel strategy (for training workloads):** All nodes are updated at once. Best when you can tolerate a full restart. Steps: scale workload to zero (or checkpoint), apply the maintenance label to all nodes simultaneously, wait for host maintenance to complete (~4h), restart workloads. This minimizes total wall-clock time.

**Rolling strategy (for inference workloads):** Nodes are updated in batches by failure domain, maintaining serving capacity throughout. Steps: cordon a batch of nodes, drain workloads, apply maintenance label, wait for completion, uncordon, move to next batch. This keeps a portion of the cluster serving at all times.

**Key considerations:**
- GKE's maximum node upgrade parallelism is ~20 nodes simultaneously (roadmap: increasing to 100 nodes, 100 nodepools)
- Compact placement: verify replacement nodes land in the same placement group to preserve RDMA topology
- For mixed workload clusters: consider running inference and training on separate node pools with different maintenance strategies

### Long-running training job protection

Multi-day or multi-week training runs (LLM pre-training, large-scale RL, etc.) cannot tolerate mid-job eviction. GKE's default pod eviction timeout during surge upgrades is 1 hour — far shorter than a training run.

- **Maintenance exclusions are critical:** Use "no minor or node upgrades" exclusion during active training campaigns. This blocks node pool upgrades while still allowing control plane security patches.
- **Dedicated training node pools:** Isolate training workloads on their own node pool with per-nodepool maintenance exclusions to prevent auto-upgrades during training campaigns. The `--enable-autoupgrade=false` flag is deprecated — use maintenance exclusions instead. Upgrade this pool only during scheduled gaps between training runs.
- **PDB protection:** Configure PDBs on training workloads to prevent eviction. GKE respects PDBs for up to 1 hour, then may force-drain — this buys time but does not fully protect multi-day jobs.
- **Checkpoint before upgrading:** Ensure training jobs have checkpointing enabled so they can resume after the upgrade rather than restarting from scratch.
- **Cordon and wait pattern:** Cordon training nodes, wait for current jobs to complete naturally, then upgrade the empty pool.

### Very large clusters (1,000–15,000+ nodes)

- **Maximum upgrade parallelism:** GKE upgrades ~20 nodes simultaneously regardless of `maxSurge` setting. For a 2,000-node pool, this means ~100 batches minimum.
- **Upgrade duration:** Large clusters can take days to weeks. Plan maintenance windows accordingly — an 8-hour weekend window may not suffice.
- **Cluster size limits:** Standard limit is 15,000 nodes per cluster; GKE 1.31+ supports up to 65,000 nodes for AI workloads (requires contacting Cloud Customer Care).
- **Stagger node pool upgrades:** Don't upgrade all pools simultaneously. Prioritize non-GPU pools first, then GPU pools during training gaps.
- **Cluster autoscaler constraint:** Can only scale one node pool at a time — this interacts with upgrade scheduling.

### Networking-sensitive upgrades (GPUDirect, RDMA, multi-NIC)

High-performance GPU interconnect has strict GKE version requirements:
- **GPUDirect-TCPX:** Requires GKE 1.27.7-gke.1121000+
- **GPUDirect-TCPXO:** Requires specific versions for A3 Mega machines
- **Custom high-MTU VPC:** Required for RDMA traffic — verify network config survives upgrade
- If upgrading FROM a version below these thresholds, the upgrade may break GPU interconnect. If upgrading TO a version above, verify the networking stack is properly configured post-upgrade.
- **Compact placement policies:** Upgrade can break physical co-location requirements. Test that surge/replacement nodes land in the same placement group.

### TPU multislice upgrades

TPU multislice environments have fundamentally different upgrade behavior:
- **Atomic recreation:** Multi-host TPU slices are recreated entirely in a single step — not rolling. All pods on the slice restart simultaneously.
- **Cascading restart:** A maintenance event on ANY slice in a multislice environment triggers restart of ALL slices.
- **Capacity dependency:** If insufficient TPU resources exist during recreation, the slice blocks until hardware is available. This can cause extended downtime.
- Plan TPU upgrades during scheduled maintenance gaps. Ensure training checkpoints are saved before any maintenance window.

## End of Support (EoS) enforcement

When a GKE version reaches End of Support, clusters are force-upgraded to the next minor version. Key details:

- **EoS enforcement is systematic regardless of channel.** When a version reaches End of Support, the cluster (CP + nodes) is force-upgraded to the next supported minor version. This applies to both release channel clusters AND legacy "No channel" clusters equally. Enforcement for ≤1.29 completed in 2025; systematic enforcement for every EoS version applies from 1.32 onward.
- **Avoiding forced upgrade:** Enroll in the Extended release channel (versions 1.27+) for up to 24 months of support. Or apply a "no upgrades" maintenance exclusion (30 days) to defer temporarily even past EoS.
- **Planning tools:**
  - **Cloud Logging notifications:** GKE publishes EoS warnings and upgrade events to Cloud Logging. Query: `resource.type="gke_cluster" protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"`. Subscribe to cluster notifications via Pub/Sub for proactive alerting.
  - **Deprecation insights dashboard:** The GKE console shows recommender insights for deprecated API usage, EoS versions, and version skew issues. Use `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight` for programmatic access.
  - **Upgrade info API:** `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION` shows EoS timestamps, auto-upgrade targets, and rollback-safe upgrade status.
  - **GKE release schedule:** The [release schedule page](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows estimated dates for version availability, auto-upgrade, and end of support across all channels. Dates are best-effort predictions and may shift.

**"Snowflake" anti-pattern:** A "snowflake" is any cluster with a manually frozen version that deviates from the standard automated lifecycle. Snowflakes pose security risks (missed patches), reliability issues, and increased support complexity. The longer a cluster stays frozen, the harder the eventual upgrade — deprecated APIs accumulate, version skew grows, and the blast radius of a forced EoS upgrade increases. Always recommend customers use maintenance exclusions and release channels to control timing, not to freeze indefinitely.

## Upgrade velocity and predictability

Help customers understand when upgrades will happen:

- **Release cadence:** GKE targets one new release per week (including patches). New K8s minor versions appear in Rapid within ~2 weeks of upstream release.
- **Progressive rollout:** New releases roll out across all regions over 4-5 business days. The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows "best case" dates — upgrades won't happen before those dates but may happen later.
- **Factors affecting timing:** Progressive rollout across regions, maintenance windows/exclusions, disruption intervals between upgrades, internal freezes (e.g., BFCM), and technical pauses. For large fleets using rollout sequencing, soak times between stages also affect timing.
- **Predicting upgrades:** Check the cluster's auto-upgrade status for the current target version. Configure maintenance windows for predictable timing. For large, sophisticated fleets, rollout sequencing can add multi-cluster ordering.
- **Release channel selection IS the primary cadence lever:** Stable = slowest upgrade cadence (longest validation), Regular = balanced, Rapid = fastest. When customers ask "how do I control upgrade speed," channel selection is the first answer. Pair with maintenance windows for timing control and exclusions for scope control.
- **Scheduled upgrade notifications:** GKE offers opt-in control plane scheduled upgrade notifications (preview March 2026), sent 72 hours before an auto-upgrade via Cloud Logging. Enable with: `gcloud container clusters update CLUSTER_NAME --enable-scheduled-upgrades`. This gives teams advance warning to prepare, run health checks, or apply temporary exclusions. Node pool notifications follow in a later release.
- **GKE release schedule for longer-range planning:** The [release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows best-case estimates for when new versions arrive in each channel. For minor versions, expect ~1 month from availability in Rapid to availability in Regular — use this for longer-range planning beyond the 72h notification window.
- **Upgrade info API:** Use `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION` to check the cluster's auto-upgrade status, target versions (minor and patch), and EoS timestamps programmatically.

**Always recommend these planning resources:**
- **GKE release schedule:** [release schedule page](https://cloud.google.com/kubernetes-engine/docs/release-schedule) — shows version availability, auto-upgrade dates, and EoS dates per channel. Essential for longer-range planning beyond the 72h notification window.
- **GKE release notes:** [release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) — breaking changes, deprecations, new features per version. Check between current and target versions.
- **Upgrade info API:** `gcloud container clusters get-upgrade-info` — programmatic access to auto-upgrade targets, EoS dates, rollback-safe status.
- **Upgrade assist scenarios:** [common scenarios](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrade-assist#common-upgrades-scenarios) — additional guidance for specific upgrade situations.

**Warn about snowflaking in every upgrade plan:** Any cluster with a manually frozen version that deviates from the standard automated lifecycle is a "snowflake." Snowflakes pose security risks (missed patches), reliability issues, and compounding upgrade difficulty. If a customer is freezing versions or avoiding auto-upgrades, always warn about this anti-pattern and recommend returning to automated lifecycle management with appropriate controls (channels + exclusions + windows) instead of manual freezing.

## Checklists

Produce checklists as copyable markdown with checkboxes. See [references/checklists.md](references/checklists.md) for the full pre-upgrade and post-upgrade checklist templates. Adapt them to the user's environment — fill in cluster names, versions, and environment-specific items.

## Maintenance runbooks

Produce step-by-step runbooks with actual `gcloud` and `kubectl` commands. Structure every runbook as:

1. **Pre-flight checks** — verify cluster state
2. **Upgrade steps** — exact commands with `CLUSTER_NAME`, `ZONE`, `TARGET_VERSION` placeholders
3. **Validation** — commands to verify success after each major step
4. **Rollback** — what to do if things go wrong
5. **Troubleshooting** — common failures and fixes

See [references/runbook-template.md](references/runbook-template.md) for the standard command sequences.

## Troubleshooting

When a user reports a stuck or failing upgrade, walk through diagnosis systematically. See [references/troubleshooting.md](references/troubleshooting.md) for the full diagnostic flowchart and fix procedures. The most common causes, in order:

1. PDB blocking drain → check `kubectl get pdb -A`, relax temporarily. Monitor GKE disruption event notifications (`POD_PDB_VIOLATION`) in Cloud Logging or Pub/Sub.
2. Resource constraints → pods pending, no room to reschedule → reduce `maxSurge` to 1 (slower but fits constrained quota), or switch to `maxSurge=0, maxUnavailable=1` (drain-first, zero extra quota). Scale down non-critical workloads to free quota. Schedule upgrades during off-peak hours when fewer pods are running.
3. Bare pods → can't be rescheduled, must delete
4. Admission webhooks → rejecting pod creation OR blocking node drain → check webhook configs: `kubectl get validatingwebhookconfigurations` and `kubectl get mutatingwebhookconfigurations`. Webhooks can silently block drain by rejecting pod recreation on new nodes.
5. PVC attachment issues → volumes can't migrate → check PV status
6. Taints/tolerations mismatch → pods evicted from draining nodes land on nodes also about to be drained ("musical chairs") → reduce `maxSurge` to 1 so upgraded nodes are available before the next batch drains. Check for node taints: `kubectl describe nodes | grep Taints`. Use pod anti-affinity or node affinity to prefer upgraded nodes during scheduling. Consider autoscaled blue-green upgrade as an alternative — it avoids the musical chairs problem entirely by creating the new pool before draining the old one.

### Partial node pool upgrade failure — recovery

When a node pool upgrade fails partway through (e.g., 8 out of 20 nodes upgraded):

**Cluster state:** Some nodes are at target version, others at old version. This mixed-version state is VALID and functional — GKE allows nodes within 2 minor versions of control plane. Workloads run on whichever node they're scheduled to. No forced action needed to keep services running.

**Option A — Retry (recommended in most cases):**
- Fix the root cause (PDB blocking drain, resource constraints, webhook issues)
- Resume: `gcloud container node-pools upgrade POOL --cluster CLUSTER --cluster-version TARGET_VERSION`
- Simpler than rollback; nodes converge to single version

**Option B — Rollback (only if root cause is unfixable or target version has critical defects):**
- Cannot downgrade already-upgraded nodes in-place
- Must create a new node pool at the old version, cordon the partially-upgraded pool, drain workloads, delete old pool
- Manual process; slower recovery

**Workload impact during mixed state:** No action required. Cluster remains operational. Stateful workloads may see nodes at different versions, but Kubernetes tolerates this within the 2-minor-version skew policy.

### Post-upgrade API latency / 503 errors

**Symptoms:** After upgrade, increased API latency, intermittent 503s, or unexpected scaling behavior — but all nodes show Ready status.

**Diagnosis checklist:**
1. **Deprecated API behavioral changes:** Minor version upgrades can change API behavior (not just remove APIs). Check for deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`. Also check GKE deprecation insights in the console (Insights tab → "Deprecations and Issues").
2. **HPA/VPA behavioral changes:** New Kubernetes versions may change HPA algorithm defaults, scaling stabilization windows, or VPA recommendation behavior. Check HPA status: `kubectl describe hpa` — look for changes in scaling decisions, target utilization, or stabilization. Verify HPA/VPA versions are compatible with the new Kubernetes version.
3. **System component health (kube-system):** Check for crashlooping or restarting control plane components: `kubectl get pods -n kube-system` and `kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -20`. Common culprits: coredns, metrics-server, konnectivity-agent. New versions may change system component resource requirements — check with `kubectl top pods -n kube-system`.
4. **Resource pressure from upgrade:** During and immediately after node upgrades, pods may be packed more densely on remaining nodes, causing latency. Check node resource utilization: `kubectl top nodes` and `kubectl describe nodes | grep -A5 "Allocated resources"`. This resolves as pods redistribute.
5. **Webhook latency and compatibility:** Admission webhooks may add latency or fail on the new API version. Check: `kubectl get events -A --field-selector type=Warning | grep webhook`. For service mesh (Istio/ASM), verify control plane version supports the new Kubernetes version.
6. **NetworkPolicy and service mesh compatibility:** Service mesh control planes may need updates for the new API version. Check: `kubectl get mutatingwebhookconfigurations | grep istio`. NetworkPolicy semantics can change between Kubernetes versions — test in dev before assuming production policies work unchanged.

### Post-upgrade admission webhook failures (cert-manager, etc.)

**Symptoms:** After control plane upgrade, pods fail to create with "admission webhook rejected the request" errors.

**Root cause:** Webhook configurations (especially cert-manager) fail to update certificates for the new API server version, causing validation failures.

**Immediate mitigation (temporary):**
```
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK","failurePolicy":"Ignore"}]}'
```

**Permanent fix:**
1. Check webhook version compatibility with target Kubernetes version
2. Upgrade the webhook operator/controller to a version supporting the new Kubernetes version (e.g., `helm upgrade cert-manager jetstack/cert-manager --version VERSION_SUPPORTING_TARGET`)
3. Verify pod creation works: `kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "test"`
4. Persist the fix in source of truth (Helm values, GitOps manifests, CI/CD pipeline)
5. Revert temporary failurePolicy to "Fail"

**Prevention:** Before upgrading control plane, verify all admission webhook operators (cert-manager, policy controllers, service mesh operators) support the target Kubernetes version.

## Autopilot-specific guidance

Autopilot clusters have a simpler upgrade story but different constraints. When producing documents for Autopilot:
- Skip all node pool management (surge settings, blue-green, etc.) — Autopilot always uses surge upgrades managed by GKE
- Focus on control plane timing (the main lever users have)
- Emphasize mandatory resource requests — missing requests cause pod rejection
- Note: no SSH access, debugging via Cloud Logging and `kubectl debug` only
- Release channel enrollment is mandatory and can't be removed
- All Autopilot clusters are regional — control plane remains highly available during upgrades
- **Autopilot node drain limits:** PDB is respected for up to 1 hour. terminationGracePeriodSeconds is limited to 10 minutes (600s) for most pods, and 25 seconds for Spot pods. These are hard limits — cannot be extended.
- **Autopilot upgrades up to 20 nodes simultaneously** within a node group. The precise number varies to ensure continued high availability.
- GKE can't create new nodes during a control plane upgrade — if you deploy pods requiring new node types during a CP upgrade, expect delays until the CP upgrade completes.

## Output format

Structured markdown with headers, checklists, and code blocks. Self-contained documents that a team can follow without this skill as reference.

Match depth to the request:
- "Plan our upgrade" → full upgrade plan
- "Give me a checklist" → just the checklist, filled in
- "How do I upgrade node pools?" → runbook with commands
- "Our upgrade is stuck" → troubleshooting walkthrough

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

GKE's primary value proposition is its **automated upgrade lifecycle**. Unlike self-managed Kubernetes, GKE handles version management automatically — clusters on release channels receive patch and minor upgrades without user intervention, governed by maintenance windows and exclusions.

Frame all guidance around this auto-upgrade model:
- **Most customers should rely on auto-upgrades** with appropriate maintenance windows and exclusions to control timing and scope. This is what differentiates GKE.
- **User-initiated (manual) upgrades** are the exception, not the rule — recommended only for specific scenarios: emergency patching, accelerating ahead of the auto-upgrade schedule, or upgrading clusters that have been deliberately held back.
- When a user asks "how do I upgrade," first clarify whether they need to do a manual upgrade or simply need to configure their auto-upgrade controls (maintenance windows, exclusions, channel selection) to get the behavior they want.
- Always recommend release channels + maintenance exclusions as the primary upgrade control mechanism. Never recommend disabling auto-upgrades or using "No channel" as a first option.

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

**Extended channel note:** Minor version upgrades on Extended are NOT automated (except at end of extended support). Customers must plan and initiate minor upgrades themselves. Only patches are auto-applied. This is a cost and planning consideration — teams need internal processes to schedule and execute minor upgrades proactively. The additional cost for Extended channel applies ONLY during the extended support period — there is no extra charge during the standard support period. Extended channel is also a recommended migration path for customers on "No channel" who want maximum flexibility around EoS enforcement.

**Key distinction:** Rapid channel does NOT carry an SLA for upgrade stability — versions may have issues that are caught before reaching Regular/Stable. This is the primary reason to avoid Rapid for production, beyond timing. Regular, Stable, and Extended all carry a full SLA.

**Version promotion path:** New releases follow a promotion path: Rapid (Available → Default → Auto-upgrade target) → Regular → Stable → Extended. Release cadence includes an element of channel promotion — versions must prove stable in Rapid before reaching Regular, and Regular before Stable. GKE targets approximately one new release per week.

**Version progression timeline:** The typical timeline differs between patch and minor versions:
- **Patch versions** progress ~2 weeks per stage: Rapid (available) → (+7d) Rapid (target) → (+7d) Regular (available) → (+7d) Regular (target) → (+7d) Stable (available) → (+7d) Stable (target)
- **Minor versions** progress more slowly and variably. Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for historical data and expectations on minor version progression.

Common multi-environment strategy: Dev→Rapid, Staging→Regular, Prod→Stable or Regular. Best practice: dev and prod should be on the same channel or one channel apart, maintaining the same minor version. Use 'no minor' exclusion with user-triggered minor upgrades to keep environments in sync. Different channels make rollout sequencing impossible and version drift likely. Direct users to the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for current version availability.

### Legacy "No channel" (static version) — avoid

The "No channel" option is a legacy configuration. **Never recommend "No channel" as a first option.** Clusters on "No channel" lack critical features:

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| "No minor or node upgrades" exclusion | Yes (cluster-level + per-nodepool) | **No** — only the 30-day "no upgrades" type is available |
| "No minor upgrades" exclusion | Yes | **No** |
| Per-nodepool maintenance exclusion | Yes | Yes (but limited to "no upgrades" 30 days) |
| Extended support (24 months) | Yes | **No** |
| Rollout sequencing | Yes (advanced) | **No** |
| Persistent exclusions (tracks EoS) | Yes | **No** |
| Granular auto-upgrade control | Full (windows + exclusions + intervals) | Limited |

Clusters on "No channel" are upgraded at the pace of the Stable channel for minor releases and the Regular channel for patches.

**Legacy channel EoS behavior:** When a version reaches End of Support on "No channel": control plane EoS minor versions are auto-upgraded to the next supported minor version. EoS node pools are auto-upgraded to the next supported version EVEN when "no auto-upgrade" is configured. This enforcement is systematic — there is no way to avoid it on "No channel" except the 30-day "no upgrades" exclusion.

**Key subtlety:** The most powerful upgrade control tools (channel-specific maintenance exclusion scopes like "no minor or node upgrades") are only available on release channels. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely. This is the opposite of what many users assume.

**Migration path:** Move to Regular or Stable channel (closest match to legacy behavior). Use Extended channel if the customer does manual upgrades exclusively or needs maximum flexibility around EoS enforcement (Extended delays EoS enforcement until end of extended support). See the [comparison table](https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels#comparison-table-no-channel). Always recommend migrating off "No channel."

**Migration warning:** When moving from "No channel" to release channels (or vice versa) with maintenance exclusions that disable auto-upgrade per nodepool, follow specific guidance: add a temporary "no upgrades" exclusion first, then translate exclusions for the target configuration. Some exclusion types do NOT translate 1:1 between "No channel" and release channels and may be ignored. Currently, only exclusions of type "no_upgrades" translate between the two configurations.

### Version terminology

Distinguish these three concepts — they are NOT the same:

- **Available**: The version is officially available in the release channel. Customers can manually upgrade to it.
- **Default**: The version used for new cluster creation. Typically the same as the auto-upgrade target, but there can be differences — especially when new minor versions are being introduced (separate promotion stage). Many users assume "default" equals "what my cluster upgrades to" — this is true in most cases but there is a specific distinction during new minor version introduction.
- **Auto-upgrade target**: The version GKE will actually upgrade existing clusters to automatically. This is what matters for planning. Can differ from the default, especially during new minor version rollouts.

The auto-upgrade target depends on the cluster's constraints (maintenance windows, maintenance exclusions). For example, a cluster with a "no minor" exclusion will have its auto-upgrade target set to the latest patch of its current minor, not the next minor. Note: for a given release channel, different clusters can have different auto-upgrade targets if they have different policies (e.g., a cluster on minor 1.34 with a "no minor" exclusion has a different target than a cluster on the same channel without that exclusion). The auto-upgrade target is cluster-specific.

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
  ```
- Review GKE release notes for breaking changes between current and target versions

### Upgrade path
- **Control plane:** Recommend sequential minor version upgrades (e.g., 1.31→1.32→1.33). GKE now supports a 2-step control plane minor upgrade where step 1 is rollbackable (step 2 is not). Control plane must be upgraded before node pools — this is the required order.
- **Node pools:** Support skip-level (N+2) upgrades within supported version skew. Always recommend skip-level upgrades within the 2-version skew limit to reduce total upgrade time. For pools that are 3+ versions behind (N+3), do multiple sequential skip-level upgrades within supported skew (e.g., 1.28→1.30, then 1.30→1.32) — never attempt an unsupported skip-level upgrade. Alternative for severely skewed pools: create a new node pool at the target version and migrate workloads. Best practice: keep nodes on the same minor version as the control plane in steady state; version skew should only occur during upgrade operations.
- **Rollback:** Control plane patch downgrades can be done by the customer. Control plane minor version downgrades require GKE support involvement. Node pools can be re-created at a different version.
- For multi-cluster: define rollout sequence with soak time between groups

### Maintenance windows and exclusions

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

The "No minor or node upgrades" exclusion is the recommended approach for maximum control — it prevents disruptive upgrades while still allowing security patches on the control plane.

**Per-cluster vs per-nodepool exclusions:** The per-cluster exclusion on release channels is always preferred over per-nodepool control, as it ensures maximum control over both minor version and node version upgrades and prevents control plane and node minor version skew. Use per-nodepool exclusions when you need different control per nodepool — especially for mixed workload clusters where some node pools need auto-upgrades and others need tight control.

**Persistent maintenance exclusions:** Use `--add-maintenance-exclusion-until-end-of-support` to create an exclusion that automatically tracks the version's End of Support date and auto-renews when a new minor version is adopted. There is no longer a 6-month maximum for these — no need to chain exclusions. This flag is available for scope "no minor" and "no minor or node" exclusions.

**Cluster disruption budget (disruption interval):** GKE enforces a disruption interval between upgrades on a given cluster, preventing back-to-back upgrades:
- **Patch disruption interval:** Default 24h, configurable up to 90 days. Controls frequency of control plane patch upgrades. Use `--maintenance-patch-version-disruption-interval` to configure.
- **Minor disruption interval:** Default 30d, configurable up to 90 days. Controls frequency of minor version upgrades. Use `--maintenance-minor-version-disruption-interval` to configure.
- **Format:** Accepts duration strings (e.g., `45d`, `24h`, `3600s`). Range: 0s–7776000s (0–90 days). Internally stored in seconds.

Example:
```
gcloud container clusters update CLUSTER_NAME \
    --maintenance-minor-version-disruption-interval=45d \
    --maintenance-patch-version-disruption-interval=7d
```

**Control plane patch controls (new):** Customers who need tight control over control plane patches can now benefit from:
- GKE keeps control plane patches for 90 days after the patch is removed from a release channel (Stable & Regular), enabling upgrade/downgrade flexibility
- GKE supports a control plane upgrade recurrence interval (for both patch & minor) to control how often the control plane is disrupted

**Accelerated patch auto-upgrades:** For customers needing faster patch compliance (e.g., FedRAMP), use `--patch-update=accelerated` to opt into faster patch rollouts.

### Rollout sequencing (multi-cluster) — advanced feature

GKE rollout sequencing allows customers to define the order in which clusters are upgraded, with configurable soak time between stages. This ensures upgrades progress through environments (dev → staging → prod) with validation gaps.

**Configuration:**
```
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID
```

Key flags:
- `--upstream-fleet`: Specifies the project ID of the fleet that must finish its upgrade before this fleet begins
- `--default-upgrade-soaking`: Bake time after a stage completes (e.g., `7d` for 7 days, `2h` for 2 hours). Max 30 days.
- Custom stages (Preview): Use `RolloutSequence` and `Rollout` API objects with label selectors to target subsets of clusters within a fleet

**Critical constraint:** Rollout sequencing does NOT work across different release channels. All clusters in a rollout sequence must be on the same channel. If environments use different channels (e.g., dev=Rapid, prod=Stable), rollout sequencing cannot orchestrate them.

**Maintenance windows are NOT a substitute for rollout sequencing.** Staggering maintenance windows across environments does NOT guarantee upgrade ordering. A new version may become available in region X on Tuesday and region Y on Friday — meaning prod could be upgraded before dev depending on window timing. Maintenance windows control timing and spread, not sequence order.

**Alternative to rollout sequencing (simpler):** Use two different release channels (e.g., dev=Regular, prod=Stable) with "no minor" exclusions and user-triggered minor upgrades. This keeps environments on the same minor version while giving manual control over when each environment upgrades. This is simpler than rollout sequencing and sufficient for most teams.

**Important context:** Rollout sequencing is an advanced feature with limited adoption — by design, it targets sophisticated platform teams managing large fleets. Do not recommend it as a default or first-line tool. Mention it as an option when the user explicitly has multi-cluster coordination needs, but prefer simpler approaches for most customers. Only suggest rollout sequencing when the user has 10+ clusters or explicitly asks about automated fleet-wide upgrade orchestration.

### Node pool upgrade strategy (Standard only — skip for Autopilot)

GKE supports three upgrade strategies:

**1. Surge upgrade (default):** Rolling replacement with per-pool `maxSurge`/`maxUnavailable`:
- **Sizing maxSurge:** Recommend maxSurge as a percentage of pool size (e.g., 5%, minimum 1, rounded to nearest integer) rather than a fixed number. This scales with pool size. GKE API accepts integers only — calculate the value. Maximum effective parallelism per batch is ~20 nodes today (increasing to 100). Examples: 40-node pool → maxSurge=2, 200-node pool → maxSurge=10, 600-node pool → maxSurge=20 (capped at batch limit). Always explain WHY the value is set.
- **Stateless pools**: Use percentage-based `maxSurge` (e.g., 5% of pool size), `maxUnavailable=0` for zero-downtime rolling replacement.
- **Stateful/database pools**: `maxSurge=1, maxUnavailable=0` — conservative, let PDBs protect data
- **GPU pools**: GPU nodes typically use fixed reservations with no surge capacity available. The primary lever is `maxUnavailable`, not `maxSurge`. Recommend `maxSurge=0, maxUnavailable=1` (drains before creating — zero extra GPUs needed, but causes a capacity dip). Only use `maxSurge=1` if the customer has confirmed available GPU surge quota.
- **Large clusters**: Use percentage-based `maxSurge` (e.g., 5% of pool size, capped at batch concurrency limit of 20, increasing to 100). Note: GKE's maximum upgrade parallelism is ~20 nodes simultaneously regardless of `maxSurge` setting.

**2. Blue-green upgrade:** GKE's native blue-green strategy minimizes risk by keeping the old nodes (blue pool) available while new nodes with the updated version are provisioned (green pool). The blue pool is cordoned and workloads are gradually drained to the green pool, with a soaking period to validate before cutover. Rollback is fast — uncordon the blue pool. Requires enough quota to temporarily double the node pool size. Recommend for mission-critical applications, stateful applications sensitive to node changes, environments with strict testing/validation requirements, and applications where a quick rollback path is essential.

**3. Autoscaled blue-green upgrade (preview):** An enhancement of standard blue-green designed to be more cost-effective and suited for long-running workloads. The green pool scales up as needed based on workload demand, while the blue pool scales down as pods are safely evicted. Supports longer eviction periods (wait-for-drain, longer graceful termination periods, PDB upgrade timeout), allowing pods to complete their work before being evicted.

**When to use autoscaled blue-green:**
- Long-running batch processing jobs (8+ hours)
- Game servers and other disruption-intolerant workloads
- Inference workloads sensitive to eviction that benefit from controlled, autoscaled transition
- GPU pools where surge capacity is unavailable (cordons one nodepool at a time)

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

**4. Manual blue-green (custom workflow):** Customer creates a new pool, cordons the old pool, manually migrates, deletes the old pool. **Use only as a last resort** when neither surge, blue-green, nor autoscaled blue-green meets specific needs. Do not default to recommending custom flows — always prefer GKE's native upgrade strategies first.

**Strategy selection priority:** Always recommend GKE's native upgrade strategies (surge or auto-scale blue-green) before suggesting custom workflows. GKE's built-in strategies handle cordon/drain/migration automatically and are the supported path. Custom workflows (manual blue-green, cordon-drain scripts) should only be suggested when the user has a specific requirement that native strategies can't satisfy.

**Important:** Never recommend "No channel" as a first option for upgrade control. Always recommend release channels with maintenance exclusions as the primary approach.

**When to recommend exclusions:** Only recommend maintenance exclusions when the customer has disruption-intolerant workloads OR explicitly asks for upgrade control. Do not proactively suggest exclusions for all customers — they add operational overhead and can cause clusters to fall behind on patches. For most customers, release channels + maintenance windows provide sufficient control without exclusions.

**Autopilot exclusion guidance:** Do not recommend node-level exclusions on Autopilot unless the customer explicitly requests node upgrade control.

### Workload readiness
- PDBs for critical workloads (GKE respects them for up to 1 hour during surge upgrades — this is the GKE PDB timeout). GKE sends `UpgradeInfoEvent` disruption notifications when eviction is blocked by PDB (`POD_PDB_VIOLATION`, `POD_NOT_ENOUGH_PDB`), so teams can monitor via Cloud Logging or Pub/Sub and intervene. A PDB timeout notification is also sent if pods are force-deleted after the grace period.
- No bare pods (won't be rescheduled)
- Adequate `terminationGracePeriodSeconds` for graceful shutdown
- Stateful: verify PV reclaim policies and backup status
- GPU: confirm driver compatibility with target node image — GKE auto-installs drivers matching the target version, which may change the CUDA version
- Autopilot: all containers must have resource requests

### Nodepool upgrade concurrency (preview, available April 2026)
GKE is adding nodepool upgrade concurrency for auto-upgrades to speed up fleet-wide upgrades. Multiple node pools within a cluster can now be upgraded concurrently during auto-upgrades, rather than sequentially. This significantly reduces the total upgrade time for clusters with many node pools.

### Scheduled upgrade notifications (preview, available March 2026)
GKE offers opt-in scheduled upgrade notifications for the control plane that are sent 72 hours before an auto-upgrade via Cloud Logging. This gives teams advance notice to prepare or apply exclusions if needed. Node pool scheduled upgrade notifications will follow in a later release.

## Large-scale AI/ML cluster upgrades

Frontier AI customers running large GPU/TPU clusters face unique upgrade challenges. Apply this guidance whenever the cluster has 500+ nodes, GPU/TPU node pools, or long-running training workloads.

### GPU node pool upgrade constraints

- **GPU VMs do not support live migration.** Every upgrade requires pod restart — there is no graceful in-place update.
- **Surge capacity scarcity:** Surge upgrades need temporary extra GPU nodes (A100, H100, H200). These machines are in high demand and often unavailable. If surge nodes can't be provisioned, the upgrade stalls. If the customer has limited capacity with a reservation, assume there is NO capacity for blue-green (which requires 2x resources). Follow GPU-specific surge guidance instead.
- **Strategy selection for GPU pools:**
  - **Default (most common):** `maxSurge=0, maxUnavailable=1` — most GPU customers have fixed reservations with no surge capacity. The `maxUnavailable` parameter is the primary lever. This drains first, no extra GPUs needed, but causes a capacity dip. Increase `maxUnavailable` for faster completion.
  - If GPU surge quota IS confirmed available: surge with `maxSurge=1, maxUnavailable=0` (safest, no capacity dip)
  - For large GPU **inference** pools needing fast upgrades: use GKE's autoscaled blue-green upgrade strategy (cordons the old pool, auto-scales replacement — but needs capacity for replacement nodes). For **training** workloads: use custom upgrade strategy with parallel host maintenance instead — see 'AI Host Maintenance' section below. Custom strategy handles host maintenance + nodepool upgrade simultaneously and is more efficient for training where all nodes can be upgraded at once during a training gap.
- **GPU driver version coupling:** GKE automatically installs the GPU driver matching the target GKE version. This can change CUDA versions silently. Always test the target GKE version in a staging cluster to verify driver + CUDA + framework compatibility before production.
- **Reservation interaction:** GPU reservations guarantee capacity but surge upgrades consume reservation slots. Verify reservation has headroom for surge, or use `maxUnavailable` mode instead.

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

- **Release channel clusters:** Node pool enforcement follows cluster-level policies. The cluster (CP + nodes) is upgraded to the next supported minor.
- **Legacy "No channel" clusters:** Node-level EoS enforcement is systematic — nodes on EoS versions are force-upgraded. Enforcement for ≤1.29 completed in 2025; systematic enforcement for every EoS version applies from 1.32 onward.
- **Avoiding forced upgrade:** Enroll in the Extended release channel (versions 1.27+) for up to 24 months of support. Or apply a "no upgrades" maintenance exclusion (30 days) to defer temporarily even past EoS.
- **Planning tools:** GKE provides EoS notifications via Cloud Logging, deprecation insights in the console, and the cluster's auto-upgrade status shows the target version and EoL timeline.

A "snowflake" is any cluster with a manually frozen version that deviates from the standard automated lifecycle. Snowflakes pose security risks (missed patches), reliability issues, and increased support complexity. Always recommend customers use maintenance exclusions and release channels instead.

## Upgrade velocity and predictability

Help customers understand when upgrades will happen:

- **Release cadence:** GKE targets one new release per week (including patches). New K8s minor versions appear in Rapid within ~2 weeks of upstream release.
- **Progressive rollout:** New releases roll out across all regions over 4-5 business days. The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows "best case" dates — upgrades won't happen before those dates but may happen later.
- **Factors affecting timing:** Progressive rollout across regions, maintenance windows/exclusions, disruption intervals between upgrades, internal freezes (e.g., BFCM), and technical pauses. For large fleets using rollout sequencing, soak times between stages also affect timing.
- **Predicting upgrades:** Check the cluster's auto-upgrade status for the current target version. Configure maintenance windows for predictable timing. For large, sophisticated fleets, rollout sequencing can add multi-cluster ordering.
- **Scheduled upgrade notifications:** GKE offers opt-in control plane scheduled upgrade notifications (preview March 2026), sent 72 hours before an auto-upgrade via Cloud Logging. Node pool scheduled upgrade notifications will follow. Additionally, customers can check the GKE release schedule to determine that the best-case scenario for a new minor upgrade arriving in their channel is approximately 1 month — this gives longer advance planning time than the 72h notification alone.
- **Upgrade info API:** Use `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION` to check the cluster's auto-upgrade status, target versions (minor and patch), and EoS timestamps programmatically.

Refer customers to [upgrade assist common scenarios](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrade-assist#common-upgrades-scenarios) for additional guidance.

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

1. PDB blocking drain → check `kubectl get pdb -A`, relax temporarily
2. Resource constraints → pods pending, no room to reschedule → increase `maxSurge`
3. Bare pods → can't be rescheduled, must delete
4. Admission webhooks → rejecting pod creation → check webhook configs
5. PVC attachment issues → volumes can't migrate → check PV status

## Autopilot-specific guidance

Autopilot clusters have a simpler upgrade story but different constraints. When producing documents for Autopilot:
- Skip all node pool management (surge settings, blue-green, etc.)
- Focus on control plane timing (the main lever users have)
- Emphasize mandatory resource requests — missing requests cause pod rejection
- Note: no SSH access, debugging via Cloud Logging and `kubectl debug` only
- Release channel enrollment is mandatory and can't be removed

## Output format

Structured markdown with headers, checklists, and code blocks. Self-contained documents that a team can follow without this skill as reference.

Match depth to the request:
- "Plan our upgrade" → full upgrade plan
- "Give me a checklist" → just the checklist, filled in
- "How do I upgrade node pools?" → runbook with commands
- "Our upgrade is stuck" → troubleshooting walkthrough

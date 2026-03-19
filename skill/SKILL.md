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
| **Rapid** | First (new K8s minors available within ~2 weeks) | Dev/test, early feature access | Standard (14 months) |
| **Regular** (default) | After Rapid validation | Most production workloads | Standard (14 months) |
| **Stable** | After Regular validation | Mission-critical, stability-first | Standard (14 months) |
| **Extended** | Same as Regular, but stays longer | Compliance, slow upgrade cycles | Up to 24 months (extra cost, versions 1.27+) |

Common multi-environment strategy: Dev→Rapid, Staging→Regular, Prod→Stable or Regular. Direct users to the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for current version availability.

### Legacy "No channel" (static version)

The "No channel" option is a legacy configuration that lacks critical features available in release channels, including granular maintenance exclusion types (e.g., "no minor or node upgrades"), Extended support, and rollout sequencing. Clusters on "No channel" are upgraded at the pace of the Stable channel for minor releases and the Regular channel for patches.

**Migration path:** Move to Regular or Stable channel (closest match to legacy behavior). Use Extended channel if the customer does manual upgrades exclusively or needs flexibility around EoS enforcement. See the [comparison table](https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels#comparison-table-no-channel). Always recommend migrating off "No channel."

### Version terminology

Distinguish these three concepts — they are NOT the same:

- **Available**: The version is officially available in the release channel. Customers can manually upgrade to it.
- **Default**: The version used for new cluster creation. Not necessarily the auto-upgrade target.
- **Auto-upgrade target**: The version GKE will automatically upgrade existing clusters to. This is what matters for planning. Can differ from the default, especially during new minor version rollouts.

The auto-upgrade target depends on the cluster's constraints (maintenance windows, maintenance exclusions). For example, a cluster with a "no minor" exclusion will have its auto-upgrade target set to the latest patch of its current minor, not the next minor.

## Upgrade planning

When asked to plan an upgrade, produce a structured document covering:

### Version compatibility
- Confirm target version availability in the cluster's release channel
- Check version skew (nodes within 2 minor versions of control plane)
- Identify deprecated APIs — the most common upgrade failure cause. Use `kubectl get --raw /metrics | grep apiserver_request_total` or the GKE deprecation insights dashboard
- Review GKE release notes for breaking changes between current and target versions

### Upgrade path
- Recommend sequential minor version upgrades (e.g., 1.28→1.29→1.30) even though skipping is technically possible via CLI — sequential is safer for catching compatibility issues between versions
- Control plane first, then node pools — this is the required order
- For multi-cluster: define rollout sequence with soak time between groups

### Maintenance windows and exclusions

**Maintenance windows:** Set recurring windows aligned with off-peak hours. Auto-upgrades respect them; manual upgrades bypass them.

**Maintenance exclusion types** — there are three distinct scopes:

| Exclusion type | What it blocks | Max duration | Use case |
|---------------|---------------|-------------|----------|
| **"No upgrades"** | All upgrades (patches, minor, nodes) | 30 days (one-time) | Code freezes, BFCM, critical periods. Honored even after EoS. |
| **"No minor or node upgrades"** | Minor version upgrades + node pool upgrades. Allows CP patches. | Up to version's End of Support | Conservative customers who want CP security patches but no disruptive changes. |
| **"No minor upgrades"** | Minor version upgrades only. Allows patches and node upgrades. | Up to version's End of Support | Teams comfortable with node churn but not minor version changes. |

The "No minor or node upgrades" exclusion is the recommended approach for maximum control — it prevents disruptive upgrades while still allowing security patches on the control plane. Customers can chain exclusions to stay on a minor version until its EoS.

**Disruption budget/interval:** GKE enforces a disruption interval between patch and minor upgrades on a given cluster, preventing back-to-back upgrades. Control plane patch and minor disruption intervals can be configured (max 90 days) to control manual rollout cadence.

### Rollout sequencing (multi-cluster)

GKE rollout sequencing allows customers to define the order in which clusters are upgraded, with configurable soak time between stages. This ensures upgrades progress through environments (dev → staging → prod) with validation gaps. Recommend configuring rollout sequencing for any fleet with 3+ clusters.

### Node pool upgrade strategy (Standard only — skip for Autopilot)

Recommend surge upgrade as the default, with per-pool `maxSurge`/`maxUnavailable` settings tailored to workload type:
- **Stateless pools**: Higher `maxSurge` (2-3) for speed, `maxUnavailable=0` for safety
- **Stateful/database pools**: `maxSurge=1, maxUnavailable=0` — conservative, let PDBs protect data
- **GPU pools**: `maxSurge=1, maxUnavailable=0` — GPUs are expensive, minimize temporary overcapacity. If GPU quota/capacity is too scarce for surge, use `maxSurge=0, maxUnavailable=1` (drains before creating — zero extra GPUs needed, but causes downtime).
- **Large clusters**: `maxSurge=20, maxUnavailable=0` for faster completion. Note: GKE's maximum upgrade parallelism is ~20 nodes simultaneously regardless of `maxSurge` setting.

Recommend blue-green only when the user needs instant rollback or has particularly fragile stateful workloads. For GPU pools, blue-green avoids the surge capacity problem but requires the full duplicate pool quota upfront.

### Workload readiness
- PDBs for critical workloads (GKE respects them for up to 1 hour during surge upgrades)
- No bare pods (won't be rescheduled)
- Adequate `terminationGracePeriodSeconds` for graceful shutdown
- Stateful: verify PV reclaim policies and backup status
- GPU: confirm driver compatibility with target node image — GKE auto-installs drivers matching the target version, which may change the CUDA version
- Autopilot: all containers must have resource requests

## Large-scale AI/ML cluster upgrades

Frontier AI customers running large GPU/TPU clusters face unique upgrade challenges. Apply this guidance whenever the cluster has 500+ nodes, GPU/TPU node pools, or long-running training workloads.

### GPU node pool upgrade constraints

- **GPU VMs do not support live migration.** Every upgrade requires pod restart — there is no graceful in-place update.
- **Surge capacity scarcity:** Surge upgrades need temporary extra GPU nodes (A100, H100, H200). These machines are in high demand and often unavailable. If surge nodes can't be provisioned, the upgrade stalls.
- **Strategy selection for GPU pools:**
  - If GPU quota/capacity is available: surge with `maxSurge=1, maxUnavailable=0` (safest)
  - If GPU quota is scarce: `maxSurge=0, maxUnavailable=1` (drains first, no extra GPUs needed, but causes capacity dip)
  - For large GPU pools needing fast upgrades: blue-green (creates full replacement pool, then migrates — but needs 2x quota temporarily)
- **GPU driver version coupling:** GKE automatically installs the GPU driver matching the target GKE version. This can change CUDA versions silently. Always test the target GKE version in a staging cluster to verify driver + CUDA + framework compatibility before production.
- **Reservation interaction:** GPU reservations guarantee capacity but surge upgrades consume reservation slots. Verify reservation has headroom for surge, or use `maxUnavailable` mode instead.

### Long-running training job protection

Multi-day or multi-week training runs (LLM pre-training, large-scale RL, etc.) cannot tolerate mid-job eviction. GKE's default pod eviction timeout during surge upgrades is 1 hour — far shorter than a training run.

- **Maintenance exclusions are critical:** Use "no minor or node upgrades" exclusion during active training campaigns. This blocks node pool upgrades while still allowing control plane security patches.
- **Dedicated training node pools:** Isolate training workloads on their own node pool with auto-upgrade disabled. Upgrade this pool only during scheduled gaps between training runs.
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
- **Factors affecting timing:** Progressive rollout across regions, maintenance windows/exclusions, disruption intervals between upgrades, internal freezes (e.g., BFCM), rollout sequencing soak times, and technical pauses.
- **Predicting upgrades:** Check the cluster's auto-upgrade status for the current target version. Configure maintenance windows for predictable timing. Use rollout sequencing to control multi-cluster ordering.
- **Scheduled upgrade notifications:** GKE offers opt-in notifications 72 hours before an auto-upgrade, delivered via Cloud Logging.

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

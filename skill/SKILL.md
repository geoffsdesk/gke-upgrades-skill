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
- **GPU pools**: `maxSurge=1, maxUnavailable=0` — GPUs are expensive, minimize temporary overcapacity
- **Large clusters**: `maxSurge=20, maxUnavailable=0` for faster completion

Recommend blue-green only when the user needs instant rollback or has particularly fragile stateful workloads.

### Workload readiness
- PDBs for critical workloads (GKE respects them for up to 1 hour during surge upgrades)
- No bare pods (won't be rescheduled)
- Adequate `terminationGracePeriodSeconds` for graceful shutdown
- Stateful: verify PV reclaim policies and backup status
- GPU: confirm driver compatibility with target node image
- Autopilot: all containers must have resource requests

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

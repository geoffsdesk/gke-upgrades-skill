# Iteration 12 — Big Picture Plan

**Date:** March 23, 2026
**Source:** PM Director eval review (evals 1–40), structured feedback JSON, and prior Claude analysis
**Scope:** SKILL.md updates, eval fixes, new eval assertions, gcloud command corrections

---

## Research Overview

**Methodology:** Expert PM review of all 40 evals with written feedback on 16 evals, plus a structured notes document covering cross-cutting themes.

**Research question:** Is the GKE Upgrades skill producing accurate, actionable, and production-grade guidance?

**Key conclusion:** The skill's structure and coverage are solid, but it has accuracy gaps in gcloud commands, over-recommends controls customers don't need, and lacks precision in several technical areas that a GKE PM or SRE would immediately spot.

---

## Findings — Prioritized by Impact

### Finding 1: gcloud commands are wrong for autoscaled blue-green and rollout sequencing
**Impact:** CRITICAL | **Confidence:** High | **Evals affected:** 7, 8, 9, 13, and all ML/training evals

The skill's gcloud commands for autoscaled blue-green are missing key flags (`--enable-autoscaling`, `--autoscaled-rollout-policy`) and some configs shown are for standard blue-green only. Rollout sequencing gcloud syntax is also incorrect.

**Action — Skill:**
- Rewrite the autoscaled blue-green section with correct gcloud flags from [configure-autoscaled-blue-green docs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-pool-upgrade-strategies#configure-autoscaled-blue-green)
- Rewrite rollout sequencing commands from [rollout sequencing docs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing-custom-stages/manage-upgrades-with-rollout-sequencing#create-rollout-sequence-custom-stages)
- Add explicit gcloud command blocks for each strategy (surge, blue-green, autoscaled blue-green) side by side

**Action — Evals:**
- Eval 7: Fix gcloud for rollout sequencing
- Eval 8: Remove surge parameters from blue-green assertions (surge params are irrelevant for blue-green)
- Eval 13: Add assertions for `--enable-autoscaling` and `--autoscaled-rollout-policy` flags
- All ML evals referencing autoscaled b/g: verify gcloud accuracy

---

### Finding 2: Eval prompts have version typos (1.32 → 1.32)
**Impact:** HIGH | **Confidence:** High | **Evals affected:** 1, 7, 20, and others

Multiple eval prompts say "upgrade from 1.32 to 1.32" which is a no-op. These should be 1.32 → 1.33.

**Action — Evals:**
- Audit all 40 eval prompts for version typos
- Update to 1.32 → 1.33 (or appropriate target versions)
- Update corresponding assertions that reference specific version numbers

---

### Finding 3: Skill over-recommends maintenance exclusions
**Impact:** HIGH | **Confidence:** High | **Evals affected:** 2, 6, 38

The skill defaults to recommending maintenance exclusions even when the customer hasn't asked for tight control. This is wrong — exclusions should only be recommended for disruption-intolerant workloads or when the customer explicitly asks for maximum control. On Autopilot specifically, node exclusions should not be recommended unless the customer specifically asks.

**Action — Skill:**
- Add a guardrail: "Do not recommend maintenance exclusions unless the customer has disruption-intolerant workloads or explicitly asks for upgrade control. Exclusions are not for everyone."
- In the exclusion type table, change framing from "recommended" to "use when maximum control is needed for disruption-intolerant workloads"
- For Autopilot: add "Do not recommend node-level exclusions on Autopilot unless the customer explicitly requests node upgrade control"

**Action — Evals:**
- Eval 2: Update assertion — exclusions should not be recommended for Autopilot unless customer asks
- Eval 6: Update assertion — "consider configuring maintenance exclusions for maximum control" → should not be proactively recommended
- Eval 38: Reframe "maximum control" language to "when needed for disruption-intolerant workloads"

---

### Finding 4: API deprecation checks lack the gcloud recommender command
**Impact:** HIGH | **Confidence:** High | **Evals affected:** 1, 2, 4, 14, 20 (cross-cutting)

The skill only mentions `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`. But GKE provides a first-party deprecation detection system: when deprecated APIs are detected, auto-upgrades are paused, and insights/recommendations are generated. The proper gcloud command is:

```
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID \
    --filter="insightSubtype:SUBTYPE"
```

**Action — Skill:**
- In "Version compatibility" section, add the gcloud recommender command alongside the kubectl metrics command
- Note that GKE automatically pauses auto-upgrades when deprecated API usage is detected
- Reference the insight/recommendation system

**Action — Evals:**
- Add cross-cutting assertion to all evals that mention API deprecation checks: "Includes gcloud recommender insights command for deprecated API detection, not just kubectl metrics"

---

### Finding 5: maxSurge should use percentage-based recommendations
**Impact:** MEDIUM-HIGH | **Confidence:** High | **Evals affected:** 1, 3, 5, 8, 9, 11 (cross-cutting)

Fixed maxSurge values (e.g., maxSurge=2, maxSurge=20) don't scale with pool size. Should recommend percentage-based calculation (e.g., 5% of pool size, minimum 1, rounded to nearest integer). Note: the GKE API only accepts integers, and max batch concurrency is 20 today (increasing to 100 soon).

**Action — Skill:**
- Update surge guidance: "Recommend maxSurge as a percentage of pool size (e.g., 5%, minimum 1). Note: GKE API accepts integers only — calculate the value. Maximum effective parallelism is 20 nodes per batch (increasing to 100)."
- Provide examples: "For a 40-node pool: maxSurge=2. For a 200-node pool: maxSurge=10. For a 600-node pool: maxSurge=20 (capped at batch limit)."

**Action — Evals:**
- Update surge-related assertions to accept either percentage-based reasoning or justified fixed values

---

### Finding 6: ML/training workloads should use custom upgrade strategy, not autoscaled b/g
**Impact:** HIGH | **Confidence:** High | **Evals affected:** 9, 31-37, 39

For ML training workloads that need host maintenance + nodepool upgrade simultaneously and require high concurrency, custom upgrade strategy is more appropriate than autoscaled blue-green. Autoscaled b/g still has the same max batch concurrency limit. The answer depends on workload type: inference can use standard strategies, but training benefits from upgrading all at once with custom strategies.

**Action — Skill:**
- In the AI/ML section, differentiate between inference and training upgrade strategies:
  - Inference: standard surge or autoscaled b/g (rolling, maintain serving capacity)
  - Training: custom upgrade strategy with parallel host maintenance (upgrade all at once during training gap)
- Note that custom strategy handles host maintenance + nodepool upgrade simultaneously

**Action — Evals:**
- Eval 9: Add assertion distinguishing inference vs. training strategy
- Eval 39: Update to reflect workload-type-dependent answer
- ML evals (31-37): Verify each correctly distinguishes inference vs. training

---

### Finding 7: Version skew best practice needs precision
**Impact:** MEDIUM | **Confidence:** High | **Evals affected:** 5

Best practice: keep nodes on the same minor version as the control plane in steady state. During upgrades, stay within N-2 skew. For N+3 situations, do multiple skip-level upgrades within supported skew — never do an unsupported skip-level. Alternative: create a new nodepool at the target version and migrate.

**Action — Skill:**
- Update version skew section: "Best practice is same minor version between CP and nodes in steady state. During upgrades, nodes must stay within 2 minor versions of CP. For severely skewed pools (N+3), do multiple N+2 skip-level upgrades in sequence, or create a new nodepool and migrate. Never attempt an unsupported skip-level upgrade."

**Action — Evals:**
- Eval 5: Replace specific version references with generic skew rule; add new nodepool migration as alternative; remove any N+3 single-hop recommendation

---

### Finding 8: Rollout sequencing vs. maintenance windows distinction
**Impact:** MEDIUM | **Confidence:** High | **Evals affected:** 7

Staggering maintenance windows does NOT guarantee environment ordering — a new version may first become available when the prod window opens (e.g., available Tuesday in region X, Friday in region Y). Maintenance windows control timing/spread, not sequencing. An alternative to rollout sequencing: use two different channels with minor version controls so both channels stay on the same minor.

**Action — Skill:**
- Update the rollout sequencing section: "Maintenance windows do NOT guarantee upgrade ordering across environments. A new version may be available in region X on Tuesday and region Y on Friday — the prod window could fire first. Windows control timing and spread, not sequence."
- Add alternative: "For simpler fleet ordering without rollout sequencing, use two different release channels with minor version exclusions to keep environments on the same minor."

**Action — Evals:**
- Eval 7: Update prompt (fix 1.32→1.32 typo); add assertion noting maintenance windows don't guarantee ordering; add two-channel alternative

---

### Finding 9: Control plane 2-step upgrade + rollback clarity
**Impact:** MEDIUM | **Confidence:** High | **Evals affected:** 1, 4

The skill mentions 2-step CP upgrade but needs more emphasis: step 1 is rollbackable, step 2 is not. Node pools support downgrade. This is a key risk-reduction feature.

**Action — Skill:**
- Ensure "Upgrade path" section prominently explains: "GKE supports 2-step minor CP upgrade. Step 1 is rollbackable (customer can roll back). Step 2 commits the upgrade and is not rollbackable. Node pools support downgrade."

**Action — Evals:**
- Eval 1: Add assertion about 2-step CP upgrade with rollback for step 1
- Eval 4: Already has partial coverage — strengthen assertion

---

### Finding 10: Disruption interval values need correct format
**Impact:** MEDIUM | **Confidence:** High | **Evals affected:** 38, 40

The `--maintenance-minor-version-disruption-interval` accepts duration strings (`30d`, `24h`, `3600s`) but is internally stored in seconds. Range: 0s–7776000s (0–90 days). Values like bare "30" or "90" without units are ambiguous. The PM notes the current values in the skill/evals don't seem appropriate.

**Action — Skill:**
- Clarify disruption interval format: accepts duration strings (`45d`, `24h`, `3600s`). Default minor: 30d, default patch: 24h. Range: 0–90 days.
- Update examples to use explicit duration strings (e.g., `--maintenance-minor-version-disruption-interval=45d`)

**Action — Evals:**
- Eval 38: Fix disruption interval values to use duration strings
- Eval 40: Fix disruption interval values to use duration strings

---

### Finding 11: Channel progression timeline for minor vs. patch
**Impact:** MEDIUM | **Confidence:** Medium | **Evals affected:** Cross-cutting (channel-related evals)

The typical patch progression is ~2 weeks per stage:
Rapid (available) → (+7d) Rapid (target) → (+7d) Regular (available) → (+7d) Regular (target) → (+7d) Stable (available) → (+7d) Stable (target)

Minor version progression is more complex and slower. Best to check the GKE release schedule for historical data.

**Action — Skill:**
- Add a "Version progression timeline" subsection under Release channels explaining patch vs. minor cadence
- Reference GKE release schedule for minor version timelines

---

### Finding 12: Notification timing correction
**Impact:** LOW-MEDIUM | **Confidence:** High | **Evals affected:** 19

Scheduled upgrade notification is 72 hours (3 days), not 1–2 weeks. The skill already says 72h in one place but Eval 19 asserts "plan within 1-2 weeks" for scheduled notifications.

**Action — Evals:**
- Eval 19: Fix notification urgency — scheduled upgrade notification gives 3 days, not 1-2 weeks

---

### Finding 13: PDB eviction blocked notifications
**Impact:** LOW-MEDIUM | **Confidence:** High | **Evals affected:** 3, and PDB-related evals

GKE now sends disruption-event notifications when eviction is blocked by PDB. Reference: [cluster notifications - disruption events](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-notifications#disruption-event)

**Action — Skill:**
- In PDB/troubleshooting section, add: "GKE sends disruption-event notifications when eviction is blocked by PDB. Monitor these via Cloud Logging or Pub/Sub."

**Action — Evals:**
- Eval 3: Add assertion about PDB eviction notifications

---

### Finding 14: --enable-autoupgrade=false is being retired
**Impact:** MEDIUM | **Confidence:** High | **Evals affected:** 13

The flag is being deprecated. Replacement: per-nodepool maintenance exclusions on release channels (new feature coming as part of "No channel" deprecation).

**Action — Skill:**
- Remove all recommendations for `--enable-autoupgrade=false`
- Replace with: "Use per-nodepool maintenance exclusions to control auto-upgrades on specific node pools. The `--enable-autoupgrade=false` flag is deprecated."

**Action — Evals:**
- Eval 13: Remove assertion that it's acceptable; add assertion that skill should NOT recommend it

---

### Finding 15: Webhook changes need persistence + risk qualification
**Impact:** LOW-MEDIUM | **Confidence:** High | **Evals affected:** 16

When recommending webhook changes (failurePolicy: Ignore, cert-manager upgrade), note: (a) changes must be persisted in source of truth (Helm, GitOps), (b) failurePolicy: Ignore is a temporary debugging measure with explicit risks, (c) revert after resolution.

**Action — Evals:**
- Eval 16: Add assertions for persistence and risk qualification

---

### Finding 16: Dev & prod channels should be same or one apart with same minor
**Impact:** LOW-MEDIUM | **Confidence:** Medium | **Evals affected:** 2, 7

Best practice: dev and prod environments should be on the same channel or one channel apart, maintaining the same minor version. Use "no minor" exclusion with user-triggered minor upgrades.

**Action — Skill:**
- Update multi-environment strategy section with this guidance

---

## Work Plan — Execution Order

### Phase 1: Critical Fixes (do first — these affect accuracy)
| # | Item | Type | Effort |
|---|------|------|--------|
| 1 | Fix all eval version typos (1.32→1.32 → 1.32→1.33) | Eval | Small |
| 2 | Correct autoscaled blue-green gcloud commands in skill | Skill | Medium |
| 3 | Correct rollout sequencing gcloud commands in skill | Skill | Medium |
| 4 | Fix disruption interval units (seconds) in skill + evals | Both | Small |
| 5 | Add gcloud recommender command for API deprecation | Skill | Small |
| 6 | Remove --enable-autoupgrade=false recommendations | Skill | Small |

### Phase 2: Accuracy Improvements (correct wrong guidance)
| # | Item | Type | Effort |
|---|------|------|--------|
| 7 | Stop over-recommending maintenance exclusions | Skill + Evals 2,6,38 | Medium |
| 8 | Differentiate inference vs. training upgrade strategies | Skill + ML evals | Medium |
| 9 | Fix maintenance windows ≠ sequencing distinction | Skill + Eval 7 | Small |
| 10 | Update version skew to generic N-2 rule + new nodepool option | Skill + Eval 5 | Small |
| 11 | Fix notification timing (3 days not 1-2 weeks) | Eval 19 | Small |
| 12 | Remove surge params from blue-green eval assertions | Eval 8 | Small |

### Phase 3: Enrichment (add missing depth)
| # | Item | Type | Effort |
|---|------|------|--------|
| 13 | Expand autoscaled blue-green description + gcloud | Skill | Medium |
| 14 | Add percentage-based maxSurge guidance | Skill + cross-cutting evals | Medium |
| 15 | Add 2-step CP upgrade + rollback detail | Skill + Evals 1,4 | Small |
| 16 | Add channel progression timeline (patch vs. minor) | Skill | Small |
| 17 | Add PDB eviction blocked notification reference | Skill + Eval 3 | Small |
| 18 | Add dev/prod channel best practice | Skill | Small |
| 19 | Add key-parameters-explained as standard pattern | Skill | Small |
| 20 | Add webhook persistence + risk qualification | Eval 16 | Small |

### Phase 4: Validate
| # | Item | Type | Effort |
|---|------|------|--------|
| 21 | Run full 40-eval Claude benchmark | Eval run | Auto |
| 22 | Run Gemini benchmark (if API key available) | Eval run | Auto |
| 23 | Generate iteration 12 comparison report | Report | Auto |
| 24 | PM re-review of updated evals 1-13 | Review | Manual |

---

## Reference Links
- [Autoscaled blue-green config](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-pool-upgrade-strategies#configure-autoscaled-blue-green)
- [Rollout sequencing](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing-custom-stages/manage-upgrades-with-rollout-sequencing#create-rollout-sequence-custom-stages)
- [Cluster disruption budget](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-disruption-budget#configure-cdb)
- [Disruption event notifications](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-notifications#disruption-event)

---

## Appendix A: Verified gcloud Commands (from official docs)

### Autoscaled Blue-Green Node Pool Upgrade

```bash
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --enable-autoscaling \
    --total-min-nodes 1 --total-max-nodes 10 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

Key flags:
- `--enable-autoscaling`: Required — enables autoscaler for the node pool
- `--total-min-nodes` / `--total-max-nodes`: Scaling limits for the entire pool
- `--autoscaled-rollout-policy`: Configures blue-green parameters
  - `blue-green-initial-node-percentage`: % of nodes to create in the green pool initially
  - `blue-green-full-batch-timeout`: Max wait time for green pool readiness before rollback

**Note:** These flags are specific to autoscaled blue-green. Standard blue-green and surge parameters (maxSurge, maxUnavailable) do NOT apply.

### Rollout Sequencing with Custom Stages

```bash
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID
```

Key flags:
- `--upstream-fleet`: Project ID of the fleet that must finish upgrading before this fleet begins
- `--default-upgrade-soaking`: Bake time after a stage completes (e.g., `7d`, `2h`). Max 30 days.
- Custom stages (Preview): Use `RolloutSequence` and `Rollout` API objects with label selectors to target cluster subsets within a fleet

### Cluster Disruption Budget

```bash
gcloud container clusters update CLUSTER_NAME \
    --maintenance-minor-version-disruption-interval=45d
```

Key flags:
- `--maintenance-minor-version-disruption-interval`: Min time between minor upgrades. Default: 30d. Range: 0s–7776000s (0–90 days)
- `--maintenance-patch-version-disruption-interval`: Min time between patch upgrades. Default: 24h. Range: 0s–7776000s
- Accepts duration strings: `30d`, `24h`, `3600s` (internally stored as seconds)

### PDB Disruption Event Notifications

GKE sends `UpgradeInfoEvent` of type `DisruptionEvent`:
- `POD_PDB_VIOLATION`: Node drain blocked because evicting a pod would violate its PDB
- `POD_NOT_ENOUGH_PDB`: Not enough pods available to satisfy PDB during drain
- PDB timeout reached: Sent if pods are force-deleted after PDB violation persists beyond ~1 hour

---

## Appendix B: Correct Skill Text for Key Sections (draft)

### Autoscaled Blue-Green (to replace current 4-line description)

> **Autoscaled blue-green upgrade:** An enhancement of standard blue-green designed to be more cost-effective and suited for long-running workloads. The green pool scales up as needed based on workload demand, while the blue pool scales down as pods are safely evicted. Supports longer eviction periods, allowing pods to complete their work before being evicted.
>
> **When to use:** Long-running batch jobs (8+ hours), game servers, disruption-intolerant inference workloads, GPU pools where surge capacity is unavailable.
>
> **When NOT to use:** ML training workloads requiring parallel host maintenance + nodepool upgrade with high concurrency — use custom upgrade strategy instead (autoscaled b/g still has the same max batch concurrency limit of 20 nodes).
>
> **Configuration:**
> ```
> gcloud container node-pools update POOL_NAME \
>     --cluster CLUSTER_NAME \
>     --enable-autoscaling \
>     --total-min-nodes MIN --total-max-nodes MAX \
>     --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
> ```
>
> Key parameters:
> - `--enable-autoscaling`: Required for this strategy
> - `blue-green-initial-node-percentage`: Start with 25% green nodes, scale up based on demand
> - `blue-green-full-batch-timeout`: Max wait before rollback if green pool isn't ready
>
> **Important:** Surge parameters (maxSurge, maxUnavailable) do not apply to blue-green strategies. Ignore them when configuring blue-green or autoscaled blue-green.

### Maintenance Exclusion Guardrail (to add to skill)

> **When to recommend exclusions:** Only recommend maintenance exclusions when the customer has disruption-intolerant workloads OR explicitly asks for upgrade control. Do not proactively suggest exclusions — they add operational overhead and can cause clusters to fall behind on patches. For most customers, release channels + maintenance windows provide sufficient control.
>
> **Autopilot:** Do not recommend node-level exclusions on Autopilot unless the customer explicitly requests node upgrade control.

### API Deprecation Checks (to expand in skill)

> Check for deprecated API usage — the most common upgrade failure cause:
> ```
> # kubectl approach (quick check)
> kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
>
> # GKE recommender approach (comprehensive, with auto-upgrade pause)
> gcloud recommender insights list \
>     --insight-type=google.container.DiagnosisInsight \
>     --location=LOCATION \
>     --project=PROJECT_ID \
>     --filter="insightSubtype:SUBTYPE"
> ```
> When GKE detects deprecated API usage, auto-upgrades are automatically paused and an insight/recommendation is generated. Use the gcloud recommender command to review deprecation insights programmatically.

---

## Success Criteria
- All 40 eval prompts have correct version numbers
- gcloud commands for autoscaled b/g and rollout sequencing match official docs
- Maintenance exclusions only recommended when explicitly appropriate
- ML evals distinguish inference vs. training strategies
- Claude benchmark ≥ 80% with skill (up from 76.8% in iteration 10)
- No PM-flagged accuracy issues on re-review of evals 1-13

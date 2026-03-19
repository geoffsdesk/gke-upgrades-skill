# GKE Upgrades Skill

A multi-platform skill for planning, executing, and validating Google Kubernetes Engine (GKE) cluster upgrades and maintenance operations. Works with both **Claude** (Agent Skills 2.0) and **Gemini CLI** — with specialized sub-skills, slash commands, and a curated GKE maintenance knowledge base.

## What It Does

This skill helps AI assistants produce high-quality GKE upgrade artifacts:

- **Upgrade plans** with version paths, node pool ordering, and per-workload surge settings
- **Pre/post-upgrade checklists** tailored to Standard or Autopilot clusters
- **Maintenance runbooks** with copy-paste gcloud/kubectl commands
- **Troubleshooting guides** for stuck or failing upgrades (PDBs, webhooks, quota, partial failures)
- **Release channel strategy** across Rapid, Regular, Stable, and Extended
- **Workload-specific guidance** for StatefulSets, GPU pools, batch jobs, service mesh
- **Compliance configuration** for maintenance windows, exclusions, and notification triage

## Repo Structure

```
gke-upgrades-skill/
├── skill/                              # Core Claude skill (install this)
│   ├── SKILL.md
│   ├── evals/evals.json                # 23 eval scenarios, 194 assertions
│   └── references/
│       ├── checklists.md
│       ├── runbook-template.md
│       └── troubleshooting.md
├── skills/                             # Claude specialized sub-skills
│   ├── gke-master-skill/               # Master knowledge base (16 domains)
│   ├── gke-policy-expert/              # EOL, snowflaking, maintenance exclusions
│   ├── gke-release-compatibility/      # Release channels, version compat, OS patches
│   └── gke-reliability-performance/    # Performance issues during upgrades
├── gemini/                             # Gemini CLI extension
│   ├── GEMINI.md                       # System prompt for Gemini
│   ├── gemini-extension.json           # Extension manifest
│   ├── skills/                         # Gemini-specific skills
│   │   ├── control-plane-upgrade/      # Regional/zonal control plane upgrade
│   │   ├── node-pool-strategy/         # Surge vs blue-green, per-pool settings
│   │   └── troubleshooting/            # Diagnostic flowchart and fixes
│   ├── commands/                       # Slash commands
│   │   ├── check_upgrade.toml          # /gke:check — pre-upgrade health check
│   │   ├── upgrade_plan.toml           # /gke:plan — generate upgrade plan
│   │   └── diagnose_stuck.toml         # /gke:diagnose — troubleshoot stuck upgrades
│   └── references/
│       ├── version-matrix.md           # Release channel versions, skew policy
│       └── api-deprecations.md         # API deprecation detection and remediation
├── data/
│   └── gke_maint_knowledge.json        # 28 curated entries, scored (v2.0)
├── tools/
│   ├── eval-app/                       # Standalone eval web app (zero dependencies)
│   │   ├── app.py                      # Python stdlib HTTP server + API proxy
│   │   └── index.html                  # Side-by-side viewer, benchmarks, live API runs
│   └── run-evals.py                    # Automated eval runner (Claude, Gemini, or both)
├── workspace/                          # Eval results by iteration
│   ├── iteration-1/
│   ├── iteration-2/
│   ├── iteration-3/                    # 3 evals, 100% vs 44% (+56%)
│   └── iteration-4/                    # 23 evals, Claude + Gemini head-to-head
└── GKE-Upgrade-Skill-Overview.html     # 1-pager overview (importable to Google Docs)
```

## Installation

### Claude (Agent Skills 2.0)

```bash
# Core skill only
cp -r skill/ ~/.claude/skills/gke-upgrades/

# All specialized skills
cp -r skills/* ~/.claude/skills/
```

The skill activates automatically when you ask about GKE upgrades, version bumps, maintenance windows, or stuck upgrades.

### Gemini CLI

**Prerequisites:**

- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed (`npm install -g @anthropic-ai/gemini-cli` or via the standalone installer)
- A Gemini API key (set `GEMINI_API_KEY` in your environment, or pass via `--api-key`)
- Optional: `gcloud` SDK authenticated to your GKE project (enables live cluster queries via the MCP server)

**Install the extension:**

```bash
# Create the extension directory
mkdir -p ~/.gemini/extensions/gke-mgmt-lifecycle

# Copy the extension files
cp -r gemini/* ~/.gemini/extensions/gke-mgmt-lifecycle/

# Verify it was picked up
gemini extensions list
# Should show: gke-mgmt-lifecycle (GKE Maintenance & Upgrade)
```

**What gets installed:**

| Component | Path | Purpose |
|-----------|------|---------|
| `GEMINI.md` | System prompt | Core upgrade planning knowledge and principles |
| `gemini-extension.json` | Extension manifest | Registers skills, commands, MCP server, and references |
| `skills/control-plane-upgrade/` | Skill | Regional/zonal control plane upgrade guidance |
| `skills/node-pool-strategy/` | Skill | Surge vs blue-green, per-pool settings |
| `skills/troubleshooting/` | Skill | Diagnostic flowchart and fixes |
| `commands/*.toml` | Slash commands | Three purpose-built commands (see below) |
| `references/version-matrix.md` | Reference | Release channel versions and skew policy |
| `references/api-deprecations.md` | Reference | API deprecation detection and remediation |

**Slash commands:**

| Command | What It Does |
|---------|-------------|
| `/gke:check` | Pre-upgrade health check with GREEN/YELLOW/RED risk assessment |
| `/gke:plan` | Generate a complete upgrade plan with gcloud commands and checklists |
| `/gke:diagnose` | Systematic troubleshooting for stuck or failing upgrades |

**Usage examples:**

```
# Open Gemini CLI and ask directly
gemini> Plan an upgrade for our Standard cluster from 1.28 to 1.30

# Or use the slash commands
gemini> /gke:check --cluster my-cluster --zone us-central1-a
gemini> /gke:plan --from 1.28 --to 1.30 --mode standard
gemini> /gke:diagnose "node pool stuck at 3/12 nodes drained"
```

**Optional — enable live cluster access:**

The extension manifest includes an MCP server entry for `gcloud-sdk`. If you have `gcloud` authenticated, Gemini can run live commands (`gcloud container clusters describe`, `kubectl get pdb -A`, etc.) to base its advice on your actual cluster state rather than assumptions. Set `GOOGLE_APPLICATION_CREDENTIALS` in your environment to enable this.

## Eval Results

### Iteration 3 (3 evals, 27 assertions)

| Metric | With Skill | Without Skill | Delta |
|--------|-----------|---------------|-------|
| Pass Rate | 100% (27/27) | 44% (12/27) | **+56%** |

### Iteration 4 (23 evals, 194 assertions — Claude + Gemini)

Running with `--provider both` for head-to-head comparison. See `workspace/iteration-4/benchmark.json` for full results.

### Iteration History

| Iteration | Evals | With Skill | Without Skill | Delta |
|-----------|-------|-----------|---------------|-------|
| 1 | 3 | 100% | 78% | +22% |
| 2 | 3 | 100% | 78% | +22% |
| 3 | 3 | 100% | 44% | +56% |
| 4 | 23 | 80.4% (Claude) | 71.1% (Claude) | +9.3% |

## Running Evals

### Automated Runner (recommended)

The `tools/run-evals.py` script runs all 23 evals, grades outputs, and computes benchmarks. Zero dependencies beyond Python 3.10+ stdlib.

```bash
# Run both providers head-to-head
python3 tools/run-evals.py \
  --provider both \
  --api-key sk-ant-... \
  --gemini-key AIza... \
  --iteration 5

# Run Claude only
python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 5

# Run Gemini only
python3 tools/run-evals.py --provider gemini --api-key AIza... --iteration 5 --model flash

# Run specific evals
python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 5 --evals 4,5,6

# Grade existing outputs without re-running
python3 tools/run-evals.py --grade-only --iteration 5 --provider claude --api-key sk-ant-...

# Dry run (no API calls)
python3 tools/run-evals.py --dry-run --iteration 5
```

**Model aliases:** Claude: `sonnet`/`opus`/`haiku`. Gemini: `flash`/`pro`/`flash-lite`.

### Eval Web App

```bash
python3 tools/eval-app/app.py
# Opens at http://localhost:8000
```

Features: side-by-side output comparison, benchmark dashboards, grading drill-down, and **live API runs** (enter your API key and run any eval prompt in real-time).

## Eval Scenarios (23 total, 194 assertions)

| # | Category | Scenario | Assertions |
|---|----------|----------|-----------|
| 1 | Upgrade Planning | Multi-pool Standard upgrade (general + Postgres + GPU) | 10 |
| 2 | Checklists | Autopilot fleet pre/post-upgrade checklists | 9 |
| 3 | Troubleshooting | Stuck node pool drain (3/12 nodes) | 8 |
| 4 | Control Plane | Regional control plane upgrade mechanics | 8 |
| 5 | Version Mgmt | Version skew recovery (3 minor versions behind) | 8 |
| 6 | Release Channels | Channel migration (Rapid → Stable) | 8 |
| 7 | Multi-Cluster | 12-cluster fleet rollout across 3 environments | 9 |
| 8 | Node Pool | Blue-green vs surge for Cassandra on local SSDs | 8 |
| 9 | Node Pool | Large cluster (600 nodes) speed optimization | 8 |
| 10 | Node Pool | Spot VM node pool upgrade considerations | 8 |
| 11 | Workload | StatefulSet Elasticsearch cluster upgrade | 9 |
| 12 | Workload | Istio service mesh interaction | 8 |
| 13 | Workload | Long-running batch jobs (8-16h) | 8 |
| 14 | Troubleshooting | Post-upgrade performance degradation | 8 |
| 15 | Troubleshooting | Partial node pool failure recovery (8/20) | 8 |
| 16 | Troubleshooting | Webhook blocking pod creation (cert-manager) | 9 |
| 17 | Troubleshooting | Quota-constrained upgrade workarounds | 8 |
| 18 | Operational | SOX compliance maintenance windows | 9 |
| 19 | Operational | Notification triage system | 8 |
| 20 | Upgrade Planning | Complete beginner runbook (first upgrade ever) | 10 |
| 21 | Release Channels | Extended channel tradeoffs (24-month support) | 8 |
| 22 | Troubleshooting | Pod scheduling during rolling upgrade | 8 |
| 23 | Operational | PDB audit for upgrade safety | 9 |

## Knowledge Base

The `data/gke_maint_knowledge.json` (v2.0) contains 28 curated entries from public GKE documentation:

| Quality Score | Count | Meaning |
|--------------|-------|---------|
| 2 | 14 | Verified and recommended — directly used in skill references |
| 1 | 14 | Accepted as accurate — available for future expansion |
| 0 | 0 | Needs review |

All internal/proprietary references have been scrubbed. Only public `cloud.google.com` URLs remain.

## Improving the Skill

1. Run evals → identify which assertions fail with_skill (these are gaps in the skill)
2. Add content to the appropriate reference `.md` file to address the gap
3. Re-run evals → confirm the fix works without regressing other assertions
4. Add new eval scenarios for untested domains
5. Expand the knowledge base with scored entries from public docs

## Documentation

- **[GKE-Upgrade-Skill-Overview.html](GKE-Upgrade-Skill-Overview.html)** — 1-pager overview (open in browser or import to Google Docs)

## License

Apache 2.0 — see [LICENSE](LICENSE).

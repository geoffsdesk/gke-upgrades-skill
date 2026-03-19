# GKE Upgrades Skill

A multi-platform skill for planning, executing, and validating Google Kubernetes Engine (GKE) cluster upgrades and maintenance operations. Works with both **Claude** (Agent Skills 2.0) and **Gemini CLI** — with specialized sub-skills, slash commands, and a curated GKE maintenance knowledge base.

## What It Does

This skill helps AI assistants produce high-quality GKE upgrade artifacts:

- **Upgrade plans** with version paths, node pool ordering, and per-workload surge settings
- **Pre/post-upgrade checklists** tailored to Standard or Autopilot clusters
- **Maintenance runbooks** with copy-paste gcloud/kubectl commands
- **Troubleshooting guides** for stuck or failing upgrades
- **Release channel strategy** across Rapid, Regular, Stable, and Extended
- **Policy expertise** on EOL enforcement, snowflaking, maintenance exclusions
- **Release compatibility** and OS patching guidance
- **Reliability/performance** insights during upgrade operations

## Repo Structure

```
gke-upgrades-skill/
├── skill/                              # Core Claude skill (install this)
│   ├── SKILL.md
│   ├── evals/evals.json                # 3 test cases, 27 assertions
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
│   │   ├── control-plane-upgrade/
│   │   ├── node-pool-strategy/
│   │   └── troubleshooting/
│   ├── commands/                       # Slash commands (/gke:check, /gke:plan, /gke:diagnose)
│   │   ├── check_upgrade.toml
│   │   ├── upgrade_plan.toml
│   │   └── diagnose_stuck.toml
│   └── references/
│       ├── version-matrix.md
│       └── api-deprecations.md
├── data/
│   └── gke_maint_knowledge.json        # 28 curated Q&A entries, scored & tagged
├── tools/
│   └── eval-app/                       # Web-based eval viewer (app.py + index.html)
├── workspace/                          # Eval results (3 iterations)
│   ├── iteration-1/
│   ├── iteration-2/
│   └── iteration-3/
├── reviews/                            # Static eval viewer HTML
└── gke-upgrades.skill                  # Packaged skill file
```

## Knowledge Base: gke_maint_knowledge.json

The `data/` directory contains a curated, sanitized knowledge base (v2.0) with 28 GKE maintenance Q&A entries — 16 original entries from internal FAQs (fully sanitized) plus 12 entries enriched from public GKE documentation.

| Field | Description |
|-------|-------------|
| id | Unique question identifier |
| title | Question title |
| question | Full question text |
| best_answer | Best available answer (sanitized, no internal references) |
| quality_score | 0 = unverified, 1 = accepted OR recommended, 2 = accepted AND recommended |
| topic_tags | Tags: upgrades, release-channels, maintenance-windows, autopilot, reliability, etc. |
| sources | Public documentation URLs (for enriched entries) |

**9 topic areas:** upgrades, release-channels, maintenance-windows, autopilot, reliability, notifications, patching, tooling, incidents.

## Installation

### Claude (Agent Skills 2.0)

```bash
# Core skill only
cp -r skill/ ~/.claude/skills/gke-upgrades/

# All specialized skills
cp -r skills/* ~/.claude/skills/
```

### Gemini CLI

```bash
# Copy the Gemini extension to your Gemini CLI extensions directory
cp -r gemini/ ~/.gemini/extensions/gke-mgmt-lifecycle/

# Or reference it in your Gemini CLI config
# The extension manifest is at gemini/gemini-extension.json
```

**Gemini slash commands:**
- `/gke:check` — Pre-upgrade health check (API deprecations, PDBs, capacity)
- `/gke:plan` — Generate a complete upgrade plan with commands and checklists
- `/gke:diagnose` — Troubleshoot a stuck or failing upgrade

## Eval Results

### Iteration 3 (current best)

| Metric | With Skill | Without Skill | Delta |
|--------|-----------|---------------|-------|
| Pass Rate | 100% (27/27) | 44% (12/27) | +56% |

Key differentiators (assertions that only pass with skill):
- Sequential upgrade path (1.28 → 1.29 → 1.30) with rationale
- Per-pool surge settings (different for general, stateful, GPU) with specific values
- Postgres-specific concerns (PDB, backup, operator compat, PV reclaim)
- GPU-specific concerns (driver compat, CUDA matrix, workload coordination)
- Autopilot constraints (mandatory resource requests, no SSH, no node management)
- Webhook troubleshooting for stuck upgrades
- Rollback procedures with blue-green strategy

### Iteration History

| Iteration | With Skill | Without Skill | Delta |
|-----------|-----------|---------------|-------|
| 1 | 100% | 78% | +22% |
| 2 | 100% | 78% | +22% |
| 3 | 100% | 44% | +56% |

## Running Evals

### Using the Eval Web App

```bash
cd tools/eval-app
python app.py
# Opens at http://localhost:5000
# Auto-discovers all skills, iterations, and grading data
```

### Using Claude's Skill Creator

1. Open a Claude session with the skill-creator skill available
2. Point it at `skill/evals/evals.json` for the test cases
3. Results go into `workspace/iteration-N/`
4. Grade against the assertions in evals.json

The `reviews/*.html` files are standalone — open in any browser.

## Improving the Skill

1. Clone this repo
2. Edit `skill/SKILL.md`, `skill/references/*.md`, or the specialized `skills/`
3. For Gemini: edit `gemini/GEMINI.md` and `gemini/skills/*/SKILL.md`
4. Use data from `data/gke_maint_knowledge.json` to enrich reference files
5. Rerun evals into `workspace/iteration-N/`
6. Grade, benchmark, review
7. Commit and push

## Test Cases

| # | Scenario | Assertions |
|---|----------|-----------|
| 1 | Standard cluster 1.28→1.30, 3 pools (general, Postgres, GPU) | 10 |
| 2 | 4 Autopilot clusters (dev Rapid + prod Stable), pre/post checklists | 9 |
| 3 | Stuck upgrade: 3/12 nodes, pods not draining | 8 |

## Origins

Built with Claude Agent Skills 2.0, extended for Gemini CLI. Includes specialized sub-skills, slash commands, and a curated GKE maintenance knowledge base enriched from public GKE documentation.

## License

Apache 2.0 — see [LICENSE](LICENSE).

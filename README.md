# GKE Upgrades Skill

A Claude Agent Skills 2.0 skill for planning, executing, and validating Google Kubernetes Engine (GKE) cluster upgrades and maintenance operations — with specialized sub-skills and a curated GKE maintenance knowledge base.

## What It Does

This skill helps Claude produce high-quality GKE upgrade artifacts:

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
├── skill/                              # Core upgrade skill (install this)
│   ├── SKILL.md
│   ├── evals/evals.json                # 3 test cases, 27 assertions
│   └── references/
│       ├── checklists.md
│       ├── runbook-template.md
│       └── troubleshooting.md
├── skills/                             # Specialized sub-skills (from CSV data)
│   ├── gke-master-skill/               # Master knowledge base (16 domains)
│   ├── gke-policy-expert/              # EOL, snowflaking, maintenance exclusions
│   ├── gke-release-compatibility/      # Release channels, version compat, OS patches
│   └── gke-reliability-performance/    # Performance issues during upgrades
├── data/
│   └── gke_maint_knowledge.json        # 16 curated Q&A entries, scored & tagged
├── tools/
│   └── eval-app/                       # Web-based eval viewer (app.py + index.html)
├── workspace/                          # Eval results (2 iterations)
│   ├── iteration-1/
│   └── iteration-2/
├── reviews/                            # Static eval viewer HTML
│   ├── iteration-1-review.html
│   └── iteration-2-review.html
└── gke-upgrades.skill                  # Packaged skill file
```

## Knowledge Base: gke_maint_knowledge.json

The `data/` directory contains a curated, sanitized knowledge base with 16 GKE maintenance Q&A entries:

| Field | Description |
|-------|-------------|
| id | Unique question identifier |
| title | Question title |
| question | Full question text |
| best_answer | Best available answer (sanitized, no internal references) |
| quality_score | 0 = unverified, 1 = accepted OR recommended, 2 = accepted AND recommended |
| topic_tags | Auto-assigned tags (upgrades, release-channels, maintenance-windows, etc.) |

**9 topic areas:** upgrades, release-channels, maintenance-windows, autopilot, reliability, notifications, patching, tooling, incidents.

## Installation

```bash
# Core skill only
cp -r skill/ ~/.claude/skills/gke-upgrades/

# All specialized skills
cp -r skills/* ~/.claude/skills/
```

## Eval Results

### Iteration 2 (current best)

| Metric | With Skill | Without Skill | Delta |
|--------|-----------|---------------|-------|
| Pass Rate | 100% | 78% | +22% |
| Avg Time | 40.3s | 49.1s | -8.8s |
| Avg Tokens | 30,320 | 28,637 | +1,683 |

Key differentiators (assertions that only pass with skill):
- Sequential upgrade path (1.28 → 1.29 → 1.30)
- Per-pool surge settings (different for general, stateful, GPU)
- Autopilot-specific constraints (mandatory resource requests, no node SSH)
- Webhook troubleshooting for stuck upgrades
- Resource constraint diagnosis

### Iteration 1 → 2 Improvements

Same 100% pass rate, but iteration 2 is 21% faster (40.3s vs 51.2s) thanks to progressive disclosure reducing context overhead.

## Running Evals

The eval workflow uses Claude's skill-creator framework. To rerun:

1. Open a Claude session with the skill-creator skill available
2. Point it at `skill/evals/evals.json` for the test cases
3. Use `workspace/iteration-2/` as `--previous-workspace` for comparison
4. Grade against the assertions in evals.json

The `reviews/*.html` files are standalone — open in any browser.

Alternatively, use the eval app:
```bash
cd tools/eval-app
python app.py
# Opens at http://localhost:5000
```

## Improving the Skill

1. Clone this repo
2. Edit `skill/SKILL.md`, `skill/references/*.md`, or the specialized `skills/`
3. Use data from `data/gke_maint_knowledge.json` to enrich reference files
4. Rerun evals into `workspace/iteration-3/`
5. Grade, benchmark, review
6. Commit and push

## Test Cases

| # | Scenario | Assertions |
|---|----------|-----------|
| 1 | Standard cluster 1.28→1.30, 3 pools (general, Postgres, GPU) | 10 |
| 2 | 4 Autopilot clusters (dev Rapid + prod Stable), pre/post checklists | 9 |
| 3 | Stuck upgrade: 3/12 nodes, pods not draining | 8 |

## Origins

Built with Claude Agent Skills 2.0. Includes specialized sub-skills and a curated GKE maintenance knowledge base.

## License

Apache 2.0 — see [LICENSE](LICENSE).

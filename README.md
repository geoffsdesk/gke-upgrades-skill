# GKE Upgrades Skill

A Claude Agent Skills 2.0 skill for planning, executing, and validating Google Kubernetes Engine (GKE) cluster upgrades and maintenance operations.

## What It Does

This skill helps Claude produce high-quality GKE upgrade artifacts:

- **Upgrade plans** with version paths, node pool ordering, and per-workload surge settings
- **Pre/post-upgrade checklists** tailored to Standard or Autopilot clusters
- **Maintenance runbooks** with copy-paste gcloud/kubectl commands
- **Troubleshooting guides** for stuck or failing upgrades
- **Release channel strategy** across Rapid, Regular, Stable, and Extended

## Repo Structure

```
gke-upgrades-skill/
├── skill/                          # The skill itself (install this)
│   ├── SKILL.md                    # Main skill file
│   ├── evals/
│   │   └── evals.json              # 3 test cases with 27 assertions
│   └── references/                 # Progressive disclosure files
│       ├── checklists.md           # Pre/post-upgrade checklist templates
│       ├── runbook-template.md     # Standard gcloud command sequences
│       └── troubleshooting.md      # Diagnostic flowchart for stuck upgrades
├── workspace/                      # Eval results (2 iterations)
│   ├── iteration-1/                # Initial version
│   │   ├── benchmark.json
│   │   └── {eval-name}/{with,without}_skill/
│   └── iteration-2/                # Skills 2.0 improvements
│       ├── benchmark.json
│       └── {eval-name}/{with,without}_skill/
└── reviews/                        # Static eval viewer HTML files
    ├── iteration-1-review.html     # Open in browser to review iter 1
    └── iteration-2-review.html     # Open in browser to review iter 2
```

## Installation

Copy the `skill/` directory contents into your Claude skills folder:

```bash
# For Claude Code
cp -r skill/ ~/.claude/skills/gke-upgrades/

# For Cowork / Claude Desktop
# Copy skill/ contents to your configured skills directory
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

## Running Evals Yourself

The eval workflow uses Claude's skill-creator framework. To rerun:

1. Open a Claude session with the skill-creator skill available
2. Point it at `skill/evals/evals.json` for the test cases
3. Use `workspace/iteration-2/` as `--previous-workspace` for comparison
4. Grade against the assertions in evals.json

The `reviews/*.html` files are standalone — open them in any browser to see full results with outputs, grading, and benchmark charts.

## Improving the Skill

1. Clone this repo on your target machine
2. Edit `skill/SKILL.md` or `skill/references/*.md`
3. Rerun evals into a new `workspace/iteration-3/` directory
4. Grade and benchmark against iteration-2 baselines
5. Review in the eval viewer
6. Commit and push when satisfied

## Test Cases

| # | Scenario | Assertions |
|---|----------|-----------|
| 1 | Standard cluster 1.28→1.30, 3 pools (general, Postgres, GPU) | 10 |
| 2 | 4 Autopilot clusters (dev Rapid + prod Stable), pre/post checklists | 9 |
| 3 | Stuck upgrade: 3/12 nodes, pods not draining | 8 |

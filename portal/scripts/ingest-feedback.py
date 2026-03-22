#!/usr/bin/env python3
"""
Pull approved feedback from Supabase and format for skill iteration.

Usage:
    # Pull all approved feedback and save as JSON
    python3 portal/scripts/ingest-feedback.py --pull

    # Pull and auto-format for a specific iteration
    python3 portal/scripts/ingest-feedback.py --pull --iteration 11

    # Mark pulled feedback as 'incorporated' in Supabase
    python3 portal/scripts/ingest-feedback.py --mark-incorporated --iteration 11

Environment:
    SUPABASE_URL     - Your Supabase project URL
    SUPABASE_KEY     - Service role key (not anon key) for admin operations
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    print("Install supabase-py: pip install supabase --break-system-packages")
    sys.exit(1)

WORKSPACE = Path(__file__).parent.parent.parent / "workspace"


def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Error: Set SUPABASE_URL and SUPABASE_KEY environment variables")
        print("  export SUPABASE_URL=https://your-project.supabase.co")
        print("  export SUPABASE_KEY=your-service-role-key")
        sys.exit(1)
    return create_client(url, key)


def pull_approved(client, iteration=None):
    """Pull all approved feedback from Supabase."""
    result = client.table("feedback") \
        .select("*") \
        .eq("status", "approved") \
        .order("created_at") \
        .execute()

    feedback = result.data
    if not feedback:
        print("No approved feedback to pull.")
        return []

    print(f"Found {len(feedback)} approved feedback items")

    # Group by type
    by_type = {}
    for f in feedback:
        t = f["type"]
        by_type.setdefault(t, []).append(f)

    for t, items in sorted(by_type.items()):
        print(f"  {t}: {len(items)} items")

    # Save raw export
    export = {
        "pulled_at": datetime.now().isoformat(),
        "count": len(feedback),
        "by_type": {t: len(items) for t, items in by_type.items()},
        "feedback": [
            {
                "id": f["id"],
                "type": f["type"],
                "topic": f["topic"],
                "eval_id": f["eval_id"],
                "title": f["title"],
                "description": f["description"],
                "current_behavior": f.get("current_behavior"),
                "expected_behavior": f.get("expected_behavior"),
                "source": f.get("source"),
                "priority": f["priority"],
                "submitted_by": f["submitted_by"],
                "submitted_at": f["created_at"],
            }
            for f in feedback
        ],
    }

    # Save to workspace
    if iteration:
        iter_dir = WORKSPACE / f"iteration-{iteration}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        out_path = iter_dir / f"feedback-iteration{iteration}.json"
    else:
        out_path = WORKSPACE / f"feedback-export-{datetime.now().strftime('%Y%m%d')}.json"

    out_path.write_text(json.dumps(export, indent=2))
    print(f"\nSaved to: {out_path}")

    return feedback


def format_for_iteration(feedback, iteration):
    """Format feedback into the structure expected by the skill iteration workflow."""
    iter_dir = WORKSPACE / f"iteration-{iteration}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    # Group corrections and improvements for SKILL.md updates
    skill_updates = []
    eval_updates = []
    new_evals = []

    for f in feedback:
        item = {
            "id": f["id"],
            "type": f["type"],
            "topic": f["topic"],
            "title": f["title"],
            "description": f["description"],
            "priority": f["priority"],
            "source": f.get("source", ""),
        }

        if f["type"] in ("correction", "improvement", "kb_update", "missing"):
            if f.get("current_behavior"):
                item["current_behavior"] = f["current_behavior"]
            if f.get("expected_behavior"):
                item["expected_behavior"] = f["expected_behavior"]
            skill_updates.append(item)

            # If linked to an eval, also update the eval
            if f.get("eval_id"):
                eval_updates.append({
                    "eval_id": f["eval_id"],
                    "feedback_id": f["id"],
                    "type": f["type"],
                    "description": f["description"],
                    "expected_behavior": f.get("expected_behavior", ""),
                })

        elif f["type"] == "new_eval":
            new_evals.append(item)

    # Save structured files
    summary = {
        "iteration": iteration,
        "generated_at": datetime.now().isoformat(),
        "total_feedback": len(feedback),
        "skill_updates": len(skill_updates),
        "eval_updates": len(eval_updates),
        "new_evals": len(new_evals),
    }

    if skill_updates:
        path = iter_dir / "skill-updates.json"
        path.write_text(json.dumps({"updates": skill_updates}, indent=2))
        print(f"  Skill updates: {path} ({len(skill_updates)} items)")

    if eval_updates:
        path = iter_dir / "eval-updates.json"
        path.write_text(json.dumps({"updates": eval_updates}, indent=2))
        print(f"  Eval updates: {path} ({len(eval_updates)} items)")

    if new_evals:
        path = iter_dir / "new-evals.json"
        path.write_text(json.dumps({"evals": new_evals}, indent=2))
        print(f"  New evals: {path} ({len(new_evals)} items)")

    # Save summary
    summary_path = iter_dir / "feedback-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n  Summary: {summary_path}")
    print(f"\n  Ready for iteration {iteration}!")
    print(f"  Next steps:")
    print(f"    1. Review skill-updates.json and apply changes to SKILL.md / GEMINI.md")
    print(f"    2. Review eval-updates.json and update evals.json assertions")
    print(f"    3. Add new evals from new-evals.json to evals.json")
    print(f"    4. Run: python3 tools/run-evals.py --iteration {iteration}")

    return summary


def mark_incorporated(client, iteration):
    """Mark all approved feedback as 'incorporated' for a given iteration."""
    result = client.table("feedback") \
        .select("id") \
        .eq("status", "approved") \
        .execute()

    if not result.data:
        print("No approved feedback to mark.")
        return

    ids = [f["id"] for f in result.data]
    for fid in ids:
        client.table("feedback").update({
            "status": "incorporated",
            "iteration_id": iteration,
        }).eq("id", fid).execute()

    print(f"Marked {len(ids)} feedback items as incorporated (iteration {iteration})")


def record_iteration(client, iteration, benchmark_path=None):
    """Record iteration results in the iterations table."""
    data = {
        "iteration_number": iteration,
        "status": "complete",
    }

    if benchmark_path:
        bp = Path(benchmark_path)
        if bp.exists():
            b = json.loads(bp.read_text())
            # Handle both single and multi-provider formats
            if "claude_with_skill" in b:
                data["claude_with_skill"] = b["claude_with_skill"]["overall_pass_rate"]
                data["claude_without_skill"] = b["claude_without_skill"]["overall_pass_rate"]
                data["claude_delta"] = b["delta"]["claude"]["pass_rate_improvement"]
                if "gemini_with_skill" in b:
                    data["gemini_with_skill"] = b["gemini_with_skill"]["overall_pass_rate"]
                    data["gemini_without_skill"] = b["gemini_without_skill"]["overall_pass_rate"]
                    data["gemini_delta"] = b["delta"]["gemini"]["pass_rate_improvement"]
                data["total_evals"] = len(b["claude_with_skill"]["evals"])
                data["total_assertions"] = b["claude_with_skill"]["total_assertions"]
            elif "with_skill" in b:
                data["claude_with_skill"] = b["with_skill"]["overall_pass_rate"]
                data["claude_without_skill"] = b["without_skill"]["overall_pass_rate"]
                data["claude_delta"] = b["delta"]["pass_rate_improvement"]
                data["total_evals"] = len(b["with_skill"]["evals"])
                data["total_assertions"] = b["with_skill"]["total_assertions"]

    client.table("iterations").upsert(data, on_conflict="iteration_number").execute()
    print(f"Recorded iteration {iteration} results in Supabase")


def main():
    parser = argparse.ArgumentParser(description="Ingest approved feedback from Supabase")
    parser.add_argument("--pull", action="store_true", help="Pull approved feedback")
    parser.add_argument("--iteration", type=int, help="Target iteration number")
    parser.add_argument("--format", action="store_true", help="Format feedback for iteration workflow")
    parser.add_argument("--mark-incorporated", action="store_true", help="Mark approved feedback as incorporated")
    parser.add_argument("--record-results", action="store_true", help="Record iteration results in Supabase")
    parser.add_argument("--benchmark", type=str, help="Path to benchmark.json (for --record-results)")
    args = parser.parse_args()

    if not any([args.pull, args.mark_incorporated, args.record_results]):
        parser.print_help()
        return

    client = get_client()

    if args.pull:
        feedback = pull_approved(client, args.iteration)
        if feedback and args.format and args.iteration:
            format_for_iteration(feedback, args.iteration)

    if args.mark_incorporated:
        if not args.iteration:
            print("Error: --iteration required with --mark-incorporated")
            sys.exit(1)
        mark_incorporated(client, args.iteration)

    if args.record_results:
        if not args.iteration:
            print("Error: --iteration required with --record-results")
            sys.exit(1)
        benchmark = args.benchmark or str(WORKSPACE / f"iteration-{args.iteration}" / "benchmark.json")
        record_iteration(client, args.iteration, benchmark)


if __name__ == "__main__":
    main()

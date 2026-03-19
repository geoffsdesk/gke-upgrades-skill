#!/usr/bin/env python3
"""
GKE Upgrade Skill — Automated Eval Runner

Runs all eval prompts from skill/evals/evals.json against a model (Claude or Gemini),
grades outputs against expectations, and produces benchmark.json.

Usage:
    # Run with Claude (default: claude-sonnet-4-20250514)
    python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 4

    # Run with Gemini
    python3 tools/run-evals.py --provider gemini --api-key AIza... --iteration 4 --model gemini-2.0-flash

    # Run BOTH providers in same iteration (head-to-head comparison)
    python3 tools/run-evals.py --provider both --api-key sk-ant-... --gemini-key AIza... --iteration 4

    # Run only specific evals
    python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 4 --evals 4,5,6

    # Skip running, just grade existing outputs
    python3 tools/run-evals.py --grade-only --iteration 4 --provider claude --api-key sk-ant-...

    # Dry run — show what would be done
    python3 tools/run-evals.py --dry-run --iteration 4

Zero dependencies beyond Python 3.10+ stdlib.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_PATH = REPO_ROOT / "skill" / "evals" / "evals.json"
SKILL_DIR = REPO_ROOT / "skill"
WORKSPACE = REPO_ROOT / "workspace"

TEXT_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}

CLAUDE_MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}
GEMINI_MODELS = {
    "flash": "gemini-2.0-flash",
    "pro": "gemini-2.5-pro-preview-05-06",
    "flash-lite": "gemini-2.5-flash-preview-04-17",
}

# ---------------------------------------------------------------------------
# Skill context builder
# ---------------------------------------------------------------------------
def build_skill_context() -> str:
    """Load SKILL.md + all references into a single string."""
    parts = []
    skill_md = SKILL_DIR / "SKILL.md"
    if skill_md.exists():
        parts.append(f"# SKILL.md\n\n{skill_md.read_text()}")
    refs_dir = SKILL_DIR / "references"
    if refs_dir.is_dir():
        for f in sorted(refs_dir.iterdir()):
            if f.is_file() and f.suffix in TEXT_EXTENSIONS:
                parts.append(f"# Reference: {f.name}\n\n{f.read_text()}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# API callers
# ---------------------------------------------------------------------------
def call_claude(api_key: str, model: str, system: str, prompt: str) -> dict:
    """Call Claude Messages API. Returns {content, tokens, time_seconds, error}."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        elapsed = time.time() - t0
        content = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                content += block["text"]
        tokens = result.get("usage", {})
        return {
            "content": content,
            "input_tokens": tokens.get("input_tokens", 0),
            "output_tokens": tokens.get("output_tokens", 0),
            "time_seconds": round(elapsed, 2),
            "error": None,
        }
    except urllib.error.HTTPError as e:
        return {"content": "", "tokens": 0, "time_seconds": 0, "error": f"HTTP {e.code}: {e.read().decode()[:500]}"}
    except Exception as e:
        return {"content": "", "tokens": 0, "time_seconds": 0, "error": str(e)}


def call_gemini(api_key: str, model: str, system: str, prompt: str) -> dict:
    """Call Gemini generateContent API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    body["generationConfig"] = {"maxOutputTokens": 4096}

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        elapsed = time.time() - t0
        content = ""
        for candidate in result.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                content += part.get("text", "")
        usage = result.get("usageMetadata", {})
        return {
            "content": content,
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
            "time_seconds": round(elapsed, 2),
            "error": None,
        }
    except urllib.error.HTTPError as e:
        return {"content": "", "tokens": 0, "time_seconds": 0, "error": f"HTTP {e.code}: {e.read().decode()[:500]}"}
    except Exception as e:
        return {"content": "", "tokens": 0, "time_seconds": 0, "error": str(e)}


def call_model(provider: str, api_key: str, model: str, system: str, prompt: str) -> dict:
    if provider == "claude":
        return call_claude(api_key, model, system, prompt)
    elif provider == "gemini":
        return call_gemini(api_key, model, system, prompt)
    else:
        return {"content": "", "tokens": 0, "time_seconds": 0, "error": f"Unknown provider: {provider}"}


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
GRADING_SYSTEM = dedent("""\
    You are a technical grading assistant. You will be given:
    1. A user's prompt (the question that was asked)
    2. A model's response to that prompt
    3. A list of expectations (assertions) to check

    For EACH expectation, determine if the response satisfies it.
    Be strict but fair — the expectation must be substantively addressed,
    not just vaguely mentioned. Look for specific commands, specific values,
    specific technical details as required by each expectation.

    Respond with ONLY a JSON object (no markdown, no explanation) in this exact format:
    {
      "assertions": [
        {
          "expectation": "the exact expectation text",
          "passed": true,
          "reason": "brief explanation of why it passed or failed"
        }
      ]
    }
""")


def grade_output(provider: str, api_key: str, model: str,
                 prompt: str, response: str, expectations: list[str]) -> dict:
    """Grade a response against expectations using the same model."""
    grading_prompt = (
        f"## User Prompt\n{prompt}\n\n"
        f"## Model Response\n{response}\n\n"
        f"## Expectations to Check\n"
    )
    for i, exp in enumerate(expectations, 1):
        grading_prompt += f"{i}. {exp}\n"

    result = call_model(provider, api_key, model, GRADING_SYSTEM, grading_prompt)
    if result["error"]:
        return {"error": result["error"]}

    # Parse JSON from response (handle markdown code blocks)
    content = result["content"].strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = content[:-3].strip()

    try:
        grading = json.loads(content)
        return grading
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse grading JSON: {e}\nRaw: {content[:500]}"}


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------
def ensure_iteration_dir(iteration: int, provider: str = None) -> Path:
    """Create workspace/iteration-N/ dirs with appropriate subdirectories.

    If provider is given (for 'both' mode), creates provider-prefixed dirs:
        claude_with_skill/, claude_without_skill/, gemini_with_skill/, gemini_without_skill/
    Otherwise creates standard dirs:
        with_skill/, without_skill/
    """
    base = WORKSPACE / f"iteration-{iteration}"
    if provider:
        (base / f"{provider}_with_skill").mkdir(parents=True, exist_ok=True)
        (base / f"{provider}_without_skill").mkdir(parents=True, exist_ok=True)
    else:
        (base / "with_skill").mkdir(parents=True, exist_ok=True)
        (base / "without_skill").mkdir(parents=True, exist_ok=True)
    return base


def save_output(iteration_dir: Path, eval_id: int, mode: str, content: str):
    path = iteration_dir / mode / f"eval-{eval_id}-output.md"
    path.write_text(content)


def save_config(iteration_dir: Path, eval_id: int, mode: str,
                prompt: str, model: str, provider: str, result: dict):
    config = {
        "eval_id": eval_id,
        "mode": mode,
        "iteration": int(iteration_dir.name.split("-")[1]),
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "time_seconds": result.get("time_seconds", 0),
    }
    if mode == "with_skill":
        config["skill_files"] = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(SKILL_DIR.rglob("*"))
            if p.is_file() and p.suffix in TEXT_EXTENSIONS
        ]
    path = iteration_dir / mode / f"eval-{eval_id}-config.json"
    path.write_text(json.dumps(config, indent=2))


def save_grading(iteration_dir: Path, eval_id: int, mode: str, grading: dict):
    path = iteration_dir / mode / f"eval-{eval_id}-grading.json"
    path.write_text(json.dumps(grading, indent=2))


def _compute_mode_stats(mode_dir: Path) -> dict:
    """Compute stats for a single mode directory."""
    evals = []
    total_passed = 0
    total_assertions = 0

    grading_files = sorted(mode_dir.glob("eval-*-grading.json"))
    for gf in grading_files:
        eval_id = int(gf.name.split("-")[1])
        try:
            data = json.loads(gf.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        assertions = data.get("assertions", [])
        passed = sum(1 for a in assertions if a.get("passed"))
        total = len(assertions)
        total_passed += passed
        total_assertions += total

        evals.append({
            "eval_id": eval_id,
            "pass_rate": round(passed / total, 3) if total else 0,
            "pass_count": passed,
            "total": total,
        })

    overall = round(total_passed / total_assertions, 3) if total_assertions else 0
    return {
        "evals": evals,
        "overall_pass_rate": overall,
        "total_passed": total_passed,
        "total_assertions": total_assertions,
    }


def compute_benchmark(iteration_dir: Path, iteration: int) -> dict:
    """Compute aggregate benchmark from grading files.

    Auto-detects directory layout:
    - Standard: with_skill/, without_skill/
    - Both mode: claude_with_skill/, claude_without_skill/, gemini_with_skill/, gemini_without_skill/
    """
    benchmark = {
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Detect all mode directories
    mode_dirs = sorted([
        d.name for d in iteration_dir.iterdir()
        if d.is_dir() and ("with_skill" in d.name or "without_skill" in d.name)
    ])

    for mode_name in mode_dirs:
        mode_dir = iteration_dir / mode_name
        benchmark[mode_name] = _compute_mode_stats(mode_dir)

    # Compute deltas for each provider
    providers = set()
    for m in mode_dirs:
        parts = m.rsplit("_", 2)
        if len(parts) == 3:  # provider_with_skill or provider_without_skill
            providers.add(parts[0])
        elif m in ("with_skill", "without_skill"):
            providers.add("default")

    deltas = {}
    for provider in sorted(providers):
        if provider == "default":
            ws_key, wos_key = "with_skill", "without_skill"
        else:
            ws_key = f"{provider}_with_skill"
            wos_key = f"{provider}_without_skill"

        ws = benchmark.get(ws_key, {})
        wos = benchmark.get(wos_key, {})
        ws_rate = ws.get("overall_pass_rate", 0)
        wos_rate = wos.get("overall_pass_rate", 0)
        delta = round(ws_rate - wos_rate, 3)

        deltas[provider] = {
            "pass_rate_improvement": delta,
            "with_skill_rate": ws_rate,
            "without_skill_rate": wos_rate,
        }

    benchmark["delta"] = deltas if len(deltas) > 1 else deltas.get("default", deltas.get(list(deltas.keys())[0], {}))

    return benchmark


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def _run_provider(provider: str, api_key: str, model: str, all_evals: list,
                   skill_context: str, iteration_dir: Path, args, mode_prefix: str = ""):
    """Run all evals for a single provider."""
    modes = ["with_skill", "without_skill"]
    total_calls = len(all_evals) * len(modes)
    call_num = 0

    for base_mode in modes:
        mode = f"{mode_prefix}{base_mode}" if mode_prefix else base_mode
        # Ensure dir exists
        (iteration_dir / mode).mkdir(parents=True, exist_ok=True)

        system = skill_context if "with_skill" in mode else ""
        print(f"\n{'='*60}")
        print(f"  {provider.upper()} | MODE: {mode}")
        print(f"{'='*60}")

        for ev in all_evals:
            call_num += 1
            eval_id = ev["id"]
            prompt = ev["prompt"]
            expectations = ev["expectations"]

            output_path = iteration_dir / mode / f"eval-{eval_id}-output.md"
            if output_path.exists() and not args.force:
                print(f"  [{call_num}/{total_calls}] Eval {eval_id} ({mode}) — SKIPPED (exists)")
                continue

            print(f"  [{call_num}/{total_calls}] Eval {eval_id} ({mode}) — running...", end="", flush=True)

            result = call_model(provider, api_key, model, system, prompt)
            if result["error"]:
                print(f" ERROR: {result['error'][:100]}")
                continue

            print(f" {result['time_seconds']}s, {result['output_tokens']} tokens")

            save_output(iteration_dir, eval_id, mode, result["content"])
            save_config(iteration_dir, eval_id, mode, prompt, model, provider, result)

            if not args.skip_grading:
                print(f"         grading...", end="", flush=True)
                grading = grade_output(provider, api_key, model,
                                       prompt, result["content"], expectations)
                if "error" in grading:
                    print(f" GRADE ERROR: {grading['error'][:100]}")
                else:
                    assertions = grading.get("assertions", [])
                    passed = sum(1 for a in assertions if a.get("passed"))
                    print(f" {passed}/{len(assertions)} passed")
                    save_grading(iteration_dir, eval_id, mode, grading)

            time.sleep(1)


def run_evals(args):
    # Load evals
    evals_data = json.loads(EVALS_PATH.read_text())
    all_evals = evals_data["evals"]

    if args.evals:
        eval_ids = {int(x) for x in args.evals.split(",")}
        all_evals = [e for e in all_evals if e["id"] in eval_ids]
        print(f"Running {len(all_evals)} selected evals: {sorted(eval_ids)}")
    else:
        print(f"Running all {len(all_evals)} evals")

    # Build skill context
    skill_context = build_skill_context()
    print(f"Skill context: {len(skill_context)} chars")

    # Determine providers to run
    if args.provider == "both":
        providers = [
            ("claude", args.api_key, args.claude_model),
            ("gemini", args.gemini_key, args.gemini_model),
        ]
        iteration_dir = ensure_iteration_dir(args.iteration, "claude")
        ensure_iteration_dir(args.iteration, "gemini")
        n_providers = 2
    else:
        model = args.model
        if args.provider == "claude" and model in CLAUDE_MODELS:
            model = CLAUDE_MODELS[model]
        elif args.provider == "gemini" and model in GEMINI_MODELS:
            model = GEMINI_MODELS[model]
        providers = [(args.provider, args.api_key, model)]
        iteration_dir = ensure_iteration_dir(args.iteration)
        n_providers = 1

    print(f"Iteration: {args.iteration}")
    print(f"Output: {iteration_dir}\n")

    if args.dry_run:
        print("=== DRY RUN ===")
        for ev in all_evals:
            print(f"  Eval {ev['id']}: {ev['prompt'][:80]}...")
            print(f"    Expectations: {len(ev['expectations'])}")
        calls = len(all_evals) * 2 * n_providers
        print(f"\nWould run {len(all_evals)} evals x 2 modes x {n_providers} provider(s) = {calls} API calls")
        print(f"Plus {calls} grading calls = {calls*2} total API calls")
        return

    # Run each provider
    for provider, api_key, model in providers:
        # Resolve model aliases
        if provider == "claude" and model in CLAUDE_MODELS:
            model = CLAUDE_MODELS[model]
        elif provider == "gemini" and model in GEMINI_MODELS:
            model = GEMINI_MODELS[model]

        mode_prefix = f"{provider}_" if args.provider == "both" else ""
        print(f"\n{'#'*60}")
        print(f"  PROVIDER: {provider.upper()} | MODEL: {model}")
        print(f"{'#'*60}")
        _run_provider(provider, api_key, model, all_evals,
                      skill_context, iteration_dir, args, mode_prefix)

    # Compute benchmark
    print(f"\n{'='*60}")
    print("  COMPUTING BENCHMARK")
    print(f"{'='*60}")
    benchmark = compute_benchmark(iteration_dir, args.iteration)
    benchmark_path = iteration_dir / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2))

    # Print summary
    delta = benchmark.get("delta", {})
    if args.provider == "both":
        for prov in ["claude", "gemini"]:
            ws = benchmark.get(f"{prov}_with_skill", {})
            wos = benchmark.get(f"{prov}_without_skill", {})
            prov_delta = delta.get(prov, {})
            print(f"\n  {prov.upper()}:")
            print(f"    With Skill:    {ws.get('total_passed', 0)}/{ws.get('total_assertions', 0)} "
                  f"({ws.get('overall_pass_rate', 0)*100:.1f}%)")
            print(f"    Without Skill: {wos.get('total_passed', 0)}/{wos.get('total_assertions', 0)} "
                  f"({wos.get('overall_pass_rate', 0)*100:.1f}%)")
            print(f"    Delta:         +{prov_delta.get('pass_rate_improvement', 0)*100:.1f}%")
    else:
        ws = benchmark.get("with_skill", {})
        wos = benchmark.get("without_skill", {})
        print(f"\n  With Skill:    {ws.get('total_passed', 0)}/{ws.get('total_assertions', 0)} "
              f"({ws.get('overall_pass_rate', 0)*100:.1f}%)")
        print(f"  Without Skill: {wos.get('total_passed', 0)}/{wos.get('total_assertions', 0)} "
              f"({wos.get('overall_pass_rate', 0)*100:.1f}%)")
        print(f"  Delta:         +{delta.get('pass_rate_improvement', 0)*100:.1f}%")

    print(f"\n  Benchmark saved: {benchmark_path}")
    print("  Done!")


def grade_only(args):
    """Grade existing outputs without re-running them."""
    iteration_dir = WORKSPACE / f"iteration-{args.iteration}"
    if not iteration_dir.exists():
        print(f"Error: {iteration_dir} does not exist")
        sys.exit(1)

    evals_data = json.loads(EVALS_PATH.read_text())
    all_evals = {e["id"]: e for e in evals_data["evals"]}

    # Resolve model
    model = args.model
    if args.provider == "claude" and model in CLAUDE_MODELS:
        model = CLAUDE_MODELS[model]
    elif args.provider == "gemini" and model in GEMINI_MODELS:
        model = GEMINI_MODELS[model]

    for mode in ["with_skill", "without_skill"]:
        mode_dir = iteration_dir / mode
        print(f"\n=== Grading {mode} ===")
        for output_file in sorted(mode_dir.glob("eval-*-output.md")):
            eval_id = int(output_file.name.split("-")[1])
            ev = all_evals.get(eval_id)
            if not ev:
                print(f"  Eval {eval_id}: no definition found, skipping")
                continue

            grading_path = mode_dir / f"eval-{eval_id}-grading.json"
            if grading_path.exists() and not args.force:
                print(f"  Eval {eval_id}: grading exists, skipping")
                continue

            response = output_file.read_text()
            print(f"  Eval {eval_id}: grading...", end="", flush=True)

            grading = grade_output(args.provider, args.api_key, model,
                                   ev["prompt"], response, ev["expectations"])
            if "error" in grading:
                print(f" ERROR: {grading['error'][:100]}")
            else:
                assertions = grading.get("assertions", [])
                passed = sum(1 for a in assertions if a.get("passed"))
                print(f" {passed}/{len(assertions)} passed")
                save_grading(iteration_dir, eval_id, mode, grading)

            time.sleep(1)

    # Recompute benchmark
    benchmark = compute_benchmark(iteration_dir, args.iteration)
    benchmark_path = iteration_dir / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2))
    print(f"\nBenchmark saved: {benchmark_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="GKE Upgrade Skill — Automated Eval Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            Examples:
              python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 4
              python3 tools/run-evals.py --provider gemini --api-key AIza... --iteration 4 --model flash
              python3 tools/run-evals.py --provider claude --api-key sk-ant-... --iteration 4 --evals 4,5,6
              python3 tools/run-evals.py --grade-only --iteration 4 --provider claude --api-key sk-ant-...
              python3 tools/run-evals.py --dry-run --iteration 4
        """)
    )
    parser.add_argument("--provider", choices=["claude", "gemini", "both"], default="claude",
                        help="API provider: claude, gemini, or both (default: claude)")
    parser.add_argument("--api-key", help="Claude API key (or set ANTHROPIC_API_KEY env var). Used for both --provider claude and --provider both.")
    parser.add_argument("--gemini-key", help="Gemini API key (or set GEMINI_API_KEY env var). Required for --provider gemini or --provider both.")
    parser.add_argument("--model", default="sonnet",
                        help="Model name or alias (single provider). Claude: sonnet/opus/haiku. Gemini: flash/pro/flash-lite.")
    parser.add_argument("--claude-model", default="sonnet",
                        help="Claude model for --provider both (default: sonnet)")
    parser.add_argument("--gemini-model", default="flash",
                        help="Gemini model for --provider both (default: flash)")
    parser.add_argument("--iteration", type=int, required=True,
                        help="Iteration number (creates workspace/iteration-N/)")
    parser.add_argument("--evals", help="Comma-separated eval IDs to run (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if output already exists")
    parser.add_argument("--skip-grading", action="store_true",
                        help="Run evals but skip the grading step")
    parser.add_argument("--grade-only", action="store_true",
                        help="Grade existing outputs without re-running")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making API calls")

    args = parser.parse_args()

    # Resolve API keys from env if not provided
    if not args.dry_run:
        if args.provider in ("claude", "both"):
            if not args.api_key:
                args.api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not args.api_key:
                print("Error: --api-key required for Claude (or set ANTHROPIC_API_KEY env var)")
                sys.exit(1)

        if args.provider in ("gemini", "both"):
            if not args.gemini_key:
                args.gemini_key = os.environ.get("GEMINI_API_KEY")
            if args.provider == "gemini" and not args.gemini_key:
                # For single-provider gemini, allow --api-key as fallback
                args.gemini_key = args.api_key
            if not args.gemini_key:
                print("Error: --gemini-key required for Gemini (or set GEMINI_API_KEY env var)")
                sys.exit(1)

        # For single-provider gemini, map api_key to gemini_key
        if args.provider == "gemini" and not args.gemini_key:
            args.gemini_key = args.api_key

    if args.grade_only:
        grade_only(args)
    else:
        run_evals(args)


if __name__ == "__main__":
    main()

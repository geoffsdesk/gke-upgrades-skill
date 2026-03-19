#!/usr/bin/env python3
"""Standalone Skill Eval Reviewer

A self-contained web app for reviewing, comparing, and grading skill evaluation
results across iterations and CLI backends (Claude, Gemini, etc.).

Reads directly from the workspace/ directory structure — no database needed.
Feedback writes back as JSON files that commit cleanly to git.

Usage:
    python app.py                              # auto-detect workspace/
    python app.py --workspace /path/to/workspace
    python app.py --port 8080
"""

import argparse
import json
import mimetypes
import os
import sys
import base64
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

METADATA_FILES = {"transcript.md", "user_notes.md", "metrics.json"}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".yaml", ".yml", ".xml", ".html", ".css", ".sh", ".rb", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".sql", ".r", ".toml",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for _ in range(10):
        if (current / "workspace").is_dir() and ((current / "skill").is_dir() or (current / "skills").is_dir()):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start.resolve()


def discover_workspace(repo_root: Path) -> Path:
    ws = repo_root / "workspace"
    if ws.is_dir():
        return ws
    raise FileNotFoundError(f"No workspace/ directory found under {repo_root}")


def discover_skills(repo_root: Path) -> list:
    skills = []
    main_skill = repo_root / "skill"
    if main_skill.is_dir() and (main_skill / "SKILL.md").exists():
        skills.append({"name": "gke-upgrades", "path": str(main_skill), "type": "core"})
    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                skills.append({"name": d.name, "path": str(d), "type": "specialized"})
    return skills


def discover_iterations(workspace: Path) -> list:
    iterations = []
    for d in sorted(workspace.iterdir()):
        if d.is_dir() and d.name.startswith("iteration-"):
            num = d.name.split("-")[1]
            iterations.append({"name": d.name, "number": int(num) if num.isdigit() else 0, "path": str(d)})
    iterations.sort(key=lambda x: x["number"])
    return iterations


def discover_evals(iteration_path: Path) -> list:
    """Discover evals in two supported layouts:

    Layout A (nested): iteration-N/eval-name/with_skill/outputs/*.md
    Layout B (flat):   iteration-N/with_skill/eval-1-output.md
    """
    import re as _re
    has_flat = any((iteration_path / c).is_dir() for c in ["with_skill", "without_skill"])
    if has_flat:
        return _discover_evals_flat(iteration_path, _re)
    return _discover_evals_nested(iteration_path)


def _discover_evals_nested(iteration_path: Path) -> list:
    evals = []
    for d in sorted(iteration_path.iterdir()):
        if not d.is_dir():
            continue
        has_runs = any((d / config).is_dir() for config in ["with_skill", "without_skill"])
        if not has_runs:
            continue
        meta = {}
        meta_path = d / "eval_metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        eval_entry = {
            "name": d.name,
            "eval_id": meta.get("eval_id"),
            "prompt": meta.get("prompt", ""),
            "assertions": meta.get("assertions", []),
            "configs": {},
        }
        for config in ["with_skill", "without_skill"]:
            config_dir = d / config
            if not config_dir.is_dir():
                continue
            run = build_run(config_dir)
            if run:
                eval_entry["configs"][config] = run
        evals.append(eval_entry)
    return evals


def _discover_evals_flat(iteration_path: Path, re) -> list:
    eval_ids = set()
    for config in ["with_skill", "without_skill"]:
        config_dir = iteration_path / config
        if not config_dir.is_dir():
            continue
        for f in config_dir.iterdir():
            m = re.match(r"eval-(\d+)-", f.name)
            if m:
                eval_ids.add(int(m.group(1)))
    evals = []
    for eval_id in sorted(eval_ids):
        eval_entry = {
            "name": f"eval-{eval_id}",
            "eval_id": eval_id,
            "prompt": "",
            "assertions": [],
            "configs": {},
        }
        for config in ["with_skill", "without_skill"]:
            config_dir = iteration_path / config
            if not config_dir.is_dir():
                continue
            run = _build_run_flat(config_dir, eval_id)
            if run:
                eval_entry["configs"][config] = run
        for config in ["with_skill", "without_skill"]:
            config_dir = iteration_path / config
            config_path = config_dir / f"eval-{eval_id}-config.json"
            if config_path.exists():
                try:
                    cfg = json.loads(config_path.read_text())
                    if cfg.get("prompt"):
                        eval_entry["prompt"] = cfg["prompt"]
                    if cfg.get("expectations"):
                        eval_entry["assertions"] = cfg["expectations"]
                    break
                except (json.JSONDecodeError, OSError):
                    pass
        evals.append(eval_entry)
    return evals


def _build_run_flat(config_dir: Path, eval_id: int) -> dict | None:
    output_files = []
    for ext in [".md", ".html", ".txt"]:
        output_path = config_dir / f"eval-{eval_id}-output{ext}"
        if output_path.exists():
            output_files.append(embed_file(output_path))
    if not output_files:
        return None
    grading = None
    grading_path = config_dir / f"eval-{eval_id}-grading.json"
    if grading_path.exists():
        try:
            grading = json.loads(grading_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    timing = None
    config_path = config_dir / f"eval-{eval_id}-config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            if "start_time" in cfg:
                timing = {"start_time": cfg["start_time"]}
        except (json.JSONDecodeError, OSError):
            pass
    return {"outputs": output_files, "grading": grading, "timing": timing}


def build_run(run_dir: Path) -> dict | None:
    outputs_dir = run_dir / "outputs"
    if not outputs_dir.is_dir():
        return None
    output_files = []
    for f in sorted(outputs_dir.iterdir()):
        if f.is_file() and f.name not in METADATA_FILES:
            output_files.append(embed_file(f))
    grading = None
    grading_path = run_dir / "grading.json"
    if grading_path.exists():
        try:
            grading = json.loads(grading_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    timing = None
    timing_path = run_dir / "timing.json"
    if timing_path.exists():
        try:
            timing = json.loads(timing_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"outputs": output_files, "grading": grading, "timing": timing}


def embed_file(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        try:
            content = path.read_text(errors="replace")
            if len(content) > 200_000:
                content = content[:200_000] + "\n\n... (truncated)"
            return {"name": path.name, "type": "text", "content": content, "ext": ext}
        except OSError:
            return {"name": path.name, "type": "error", "content": "Could not read file"}
    elif ext in IMAGE_EXTENSIONS:
        try:
            data = base64.b64encode(path.read_bytes()).decode()
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            return {"name": path.name, "type": "image", "content": f"data:{mime};base64,{data}"}
        except OSError:
            return {"name": path.name, "type": "error", "content": "Could not read image"}
    else:
        return {"name": path.name, "type": "binary", "content": f"Binary file ({ext}), {path.stat().st_size:,} bytes"}


def load_benchmark(iteration_path: Path) -> dict | None:
    bp = iteration_path / "benchmark.json"
    if bp.exists():
        try:
            return json.loads(bp.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def load_feedback(iteration_path: Path) -> dict | None:
    fp = iteration_path / "feedback.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def normalize_grading(grading: dict | None) -> dict | None:
    """Normalize grading data to a consistent format:
    {expectations: [{text, passed, evidence}], summary: {passed, total, pass_rate}}
    """
    if not grading:
        return None
    out = dict(grading)
    # Handle iter-3 format: {assertions: [{expectation, passed, reason}]}
    if "assertions" in out and "expectations" not in out:
        out["expectations"] = [
            {"text": a.get("expectation", ""), "passed": a.get("passed", False),
             "evidence": a.get("reason", "")}
            for a in out["assertions"]
        ]
    if "expectations" in out and "summary" not in out:
        exps = out["expectations"]
        passed = sum(1 for e in exps if e.get("passed"))
        total = len(exps)
        out["summary"] = {"passed": passed, "total": total,
                          "pass_rate": passed / total if total else 0}
    return out


def normalize_benchmark(benchmark: dict | None) -> dict | None:
    """Normalize benchmark to a consistent format with run_summary."""
    if not benchmark:
        return None
    # Already has run_summary — it's the iter-1/2 format
    if "run_summary" in benchmark:
        return benchmark
    # Iter-3 format: {with_skill: {overall_pass_rate, evals}, without_skill: {...}, delta}
    out = dict(benchmark)
    if "with_skill" in out and isinstance(out["with_skill"], dict) and "overall_pass_rate" in out["with_skill"]:
        ws = out["with_skill"]
        wos = out.get("without_skill", {})
        delta = out.get("delta", {})
        run_summary = {}
        for label, src in [("with_skill", ws), ("without_skill", wos)]:
            if not src:
                continue
            pr = src.get("overall_pass_rate", 0)
            run_summary[label] = {
                "pass_rate": {"mean": pr, "stddev": 0},
                "time_seconds": {"mean": 0, "stddev": 0},
                "tokens": {"mean": 0, "stddev": 0},
            }
        if delta:
            run_summary["delta"] = {"pass_rate": delta.get("pass_rate_improvement", 0)}
        out["run_summary"] = run_summary
        # Build runs array from evals
        runs = []
        for label, src in [("with_skill", ws), ("without_skill", wos)]:
            if not src or "evals" not in src:
                continue
            for ev in src["evals"]:
                runs.append({
                    "eval_id": ev.get("eval_id"),
                    "eval_name": f"eval-{ev.get('eval_id', '?')}",
                    "configuration": label,
                    "result": {
                        "pass_rate": ev.get("pass_rate", 0),
                        "passed": ev.get("pass_count", 0),
                        "total": ev.get("total", 0),
                        "time_seconds": 0,
                    },
                })
        out["runs"] = runs
    return out


def build_api_data(repo_root: Path, workspace: Path) -> dict:
    iterations = discover_iterations(workspace)
    iter_data = []
    for it in iterations:
        ip = Path(it["path"])
        evals = discover_evals(ip)
        # Normalize grading in each eval's configs
        for ev in evals:
            for cfg_name, run in ev.get("configs", {}).items():
                if run and "grading" in run:
                    run["grading"] = normalize_grading(run["grading"])
        iter_data.append({
            "name": it["name"],
            "number": it["number"],
            "evals": evals,
            "benchmark": normalize_benchmark(load_benchmark(ip)),
            "feedback": load_feedback(ip),
        })
    return {"skills": discover_skills(repo_root), "iterations": iter_data, "repo_root": str(repo_root)}


def build_skill_context(repo_root: Path) -> str:
    """Build system prompt from SKILL.md + references for with_skill runs."""
    skill_dir = repo_root / "skill"
    parts = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        parts.append(f"# SKILL.md\n\n{skill_md.read_text()}")
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for f in sorted(refs_dir.iterdir()):
            if f.is_file() and f.suffix in TEXT_EXTENSIONS:
                parts.append(f"# Reference: {f.name}\n\n{f.read_text()}")
    return "\n\n---\n\n".join(parts)


def call_claude(api_key: str, model: str, system: str, prompt: str) -> dict:
    """Call Claude Messages API. Returns {content, tokens, time_seconds, error}."""
    t0 = time.time()
    body = json.dumps({
        "model": model,
        "max_tokens": 8192,
        "system": system if system else "You are a helpful assistant.",
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        elapsed = time.time() - t0
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block["text"]
        usage = data.get("usage", {})
        return {
            "content": content,
            "tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "time_seconds": round(elapsed, 1),
            "model": data.get("model", model),
            "error": None,
        }
    except HTTPError as e:
        elapsed = time.time() - t0
        err_body = e.read().decode() if e.readable() else str(e)
        return {"content": "", "tokens": 0, "time_seconds": round(elapsed, 1), "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        elapsed = time.time() - t0
        return {"content": "", "tokens": 0, "time_seconds": round(elapsed, 1), "error": str(e)}


def call_gemini(api_key: str, model: str, system: str, prompt: str) -> dict:
    """Call Gemini generateContent API. Returns {content, tokens, time_seconds, error}."""
    t0 = time.time()
    body_data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 8192},
    }
    if system:
        body_data["systemInstruction"] = {"parts": [{"text": system}]}
    body = json.dumps(body_data).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        elapsed = time.time() - t0
        content = ""
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                content += part.get("text", "")
        usage = data.get("usageMetadata", {})
        return {
            "content": content,
            "tokens": usage.get("totalTokenCount", 0),
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
            "time_seconds": round(elapsed, 1),
            "model": model,
            "error": None,
        }
    except HTTPError as e:
        elapsed = time.time() - t0
        err_body = e.read().decode() if e.readable() else str(e)
        return {"content": "", "tokens": 0, "time_seconds": round(elapsed, 1), "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        elapsed = time.time() - t0
        return {"content": "", "tokens": 0, "time_seconds": round(elapsed, 1), "error": str(e)}


class EvalHandler(BaseHTTPRequestHandler):
    repo_root: Path = None
    workspace: Path = None

    def log_message(self, format, *args):
        sys.stdout.write(f"{self.address_string()} [{self.log_date_time_string()}] {format % args}\n")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", ""):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(get_html().encode())
            return
        if path == "/api/data":
            data = build_api_data(self.repo_root, self.workspace)
            self.send_json(data)
            return
        if path == "/api/skill-context":
            ctx = build_skill_context(self.repo_root)
            self.send_json({"context": ctx, "length": len(ctx)})
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len else b""

        if path == "/api/feedback":
            try:
                payload = json.loads(body)
                iteration = payload.get("iteration", "")
                reviews = payload.get("reviews", [])
                fp = self.workspace / iteration / "feedback.json"
                feedback_data = {"reviews": reviews, "status": "complete", "timestamp": datetime.now(timezone.utc).isoformat()}
                fp.write_text(json.dumps(feedback_data, indent=2))
                self.send_json({"ok": True, "path": str(fp)})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, status=400)
            return

        if path == "/api/run":
            try:
                payload = json.loads(body)
                provider = payload.get("provider", "claude")
                api_key = payload.get("api_key", "")
                model = payload.get("model", "")
                prompt = payload.get("prompt", "")
                mode = payload.get("mode", "without_skill")

                if not api_key:
                    self.send_json({"ok": False, "error": "No API key provided"}, status=400)
                    return
                if not prompt:
                    self.send_json({"ok": False, "error": "No prompt provided"}, status=400)
                    return

                system = ""
                if mode == "with_skill":
                    system = build_skill_context(self.repo_root)

                print(f"  Running {provider}/{model} [{mode}] ...")
                if provider == "claude":
                    if not model:
                        model = "claude-sonnet-4-20250514"
                    result = call_claude(api_key, model, system, prompt)
                elif provider == "gemini":
                    if not model:
                        model = "gemini-2.0-flash"
                    result = call_gemini(api_key, model, system, prompt)
                else:
                    self.send_json({"ok": False, "error": f"Unknown provider: {provider}"}, status=400)
                    return

                result["provider"] = provider
                result["mode"] = mode
                if result["error"]:
                    print(f"  Error: {result['error'][:100]}")
                else:
                    print(f"  Done: {result['time_seconds']}s, {result['tokens']} tokens")
                self.send_json({"ok": True, "result": result})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, status=400)
            return

        self.send_error(404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def get_html() -> str:
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return "<html><body><h1>index.html not found</h1></body></html>"


def main():
    parser = argparse.ArgumentParser(description="Standalone Skill Eval Reviewer")
    parser.add_argument("--workspace", type=str, help="Path to workspace/ directory")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = parser.parse_args()

    if args.workspace:
        workspace = Path(args.workspace).resolve()
        repo_root = find_repo_root(workspace.parent)
    else:
        repo_root = find_repo_root(Path.cwd())
        workspace = discover_workspace(repo_root)

    skills = discover_skills(repo_root)
    iters = discover_iterations(workspace)
    print(f"Repo root:  {repo_root}")
    print(f"Workspace:  {workspace}")
    print(f"Skills:     {len(skills)}")
    print(f"Iterations: {len(iters)}")
    print(f"\nStarting at http://localhost:{args.port}")
    print("Press Ctrl+C to stop.\n")

    EvalHandler.repo_root = repo_root
    EvalHandler.workspace = workspace

    server = HTTPServer(("", args.port), EvalHandler)
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{args.port}")
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

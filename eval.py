#!/usr/bin/env python3
import argparse
import json, os, re, sys, subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

CASES_PATH = os.path.join(os.path.dirname(__file__), "evals", "cases.jsonl")
DEFAULT_SKILL_ROOT = os.path.dirname(__file__)
DEFAULT_SKILLS_DIR = "skills/"


@dataclass
class RunResult:
    tool_calls: List[Dict[str, Any]]
    final_text: str
    workspace_dir: str


def load_cases(path: str) -> List[Dict[str, Any]]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def run_agent(prompt: str, workdir: str, skills_dir: str) -> RunResult:
    """
    Runs evals/runner.py which should:
      - create an isolated workspace
      - run the agent
      - emit JSON to stdout: {workspace_dir, final_text, tool_calls}
    """
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "runner.py"),
        "--workdir",
        workdir,
        "--skills-dir",
        skills_dir,
        "--prompt",
        prompt,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"runner failed (code {p.returncode}):\nSTDERR:\n{p.stderr}\nSTDOUT:\n{p.stdout}"
        )

    blob = json.loads(p.stdout)
    return RunResult(
        tool_calls=blob.get("tool_calls", []),
        final_text=blob.get("final_text", ""),
        workspace_dir=blob["workspace_dir"],
    )


def file_exists(workspace: str, relpath: str) -> bool:
    return os.path.exists(os.path.join(workspace, relpath))


def trace_contains_command(tool_calls: List[Dict[str, Any]], pattern: str) -> bool:
    rx = re.compile(pattern)
    for call in tool_calls:
        if call.get("type") == "shell":
            cmd = call.get("command", "")
            if rx.search(cmd):
                return True
    return False


def skill_was_used(tool_calls: List[Dict[str, Any]]) -> bool:
    """
    Heuristic “skill used” detector:
      - read SKILL.md/skill.md
      - ran a command that references scripts/
    Adapt to your environment if needed.
    """
    for call in tool_calls:
        if (
            call.get("type") == "read"
            and "skill.md" in (call.get("path", "") or "").lower()
        ):
            return True
        if call.get("type") == "shell" and "scripts/" in (
            call.get("command", "") or ""
        ):
            return True
    return False


def eval_case(case: Dict[str, Any], workdir: str, skills_dir: str) -> Dict[str, Any]:
    rid = case["id"]
    prompt = case["prompt"]
    expect = case.get("expect", {})

    run = run_agent(prompt, workdir, skills_dir)

    checks = []
    ok = True

    # 1) Routing check
    if "skill_used" in expect:
        used = skill_was_used(run.tool_calls)
        passed = used == bool(expect["skill_used"])
        checks.append(
            {
                "name": "routing.skill_used",
                "passed": passed,
                "got": used,
                "want": expect["skill_used"],
            }
        )
        ok = ok and passed

    # 2) Process checks
    for cmd_pat in expect.get("must_run", []):
        passed = trace_contains_command(run.tool_calls, re.escape(cmd_pat))
        checks.append(
            {"name": "process.must_run", "passed": passed, "pattern": cmd_pat}
        )
        ok = ok and passed

    for cmd_pat in expect.get("must_not_run", []):
        passed = not trace_contains_command(run.tool_calls, re.escape(cmd_pat))
        checks.append(
            {"name": "process.must_not_run", "passed": passed, "pattern": cmd_pat}
        )
        ok = ok and passed

    # 3) Outcome checks (artifacts)
    for fpath in expect.get("files", []):
        passed = file_exists(run.workspace_dir, fpath)
        checks.append({"name": "outcome.file_exists", "passed": passed, "file": fpath})
        ok = ok and passed

    return {
        "id": rid,
        "passed": ok,
        "checks": checks,
        "final_text_excerpt": run.final_text[:400],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skill-root",
        default=DEFAULT_SKILL_ROOT,
        help="Repo root to copy into an isolated workspace.",
    )
    ap.add_argument(
        "--skills-dir",
        default=DEFAULT_SKILLS_DIR,
        help="Directory (relative to repo root) containing skills. Default: skills/",
    )
    args = ap.parse_args()

    cases = load_cases(CASES_PATH)
    results = [eval_case(c, args.workdir, args.skills_dir) for c in cases]

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print(json.dumps({"passed": passed, "total": total, "results": results}, indent=2))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

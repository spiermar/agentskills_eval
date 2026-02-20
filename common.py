#!/usr/bin/env python3
import json
import os
import subprocess
from typing import Any, Dict, List, Tuple


def safe_join(workspace: str, relpath: str) -> str:
    relpath = relpath.lstrip("/").replace("..", "")
    return os.path.join(workspace, relpath)


def read_file(workspace: str, path: str) -> str:
    abspath = safe_join(workspace, path)
    with open(abspath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(workspace: str, path: str, content: str) -> str:
    abspath = safe_join(workspace, path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


def run_shell(workspace: str, command: str) -> Dict[str, Any]:
    p = subprocess.run(
        command,
        shell=True,
        cwd=workspace,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    return {
        "command": command,
        "exit_code": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def item_to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return vars(item)
    return {"type": type(item).__name__}


def find_skill_markdowns(skills_root_abs: str) -> List[str]:
    hits: List[str] = []
    for root, _, files in os.walk(skills_root_abs):
        for fn in files:
            if fn == "SKILL.md" or fn.lower() == "skill.md":
                hits.append(os.path.join(root, fn))
    hits.sort()
    return hits


def extract_frontmatter_name(md_text: str) -> str:
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = None
    for i in range(1, min(len(lines), 2000)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return ""
    for i in range(1, end):
        line = lines[i].strip()
        if line.lower().startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def build_skills_context(
    workspace_dir: str, skills_dir: str, max_chars_total: int = 200_000
) -> Tuple[str, List[Dict[str, str]]]:
    skills_root_abs = safe_join(workspace_dir, skills_dir)
    if not os.path.isdir(skills_root_abs):
        return "", []

    skill_paths = find_skill_markdowns(skills_root_abs)
    skills_meta: List[Dict[str, str]] = []

    chunks: List[str] = []
    used = 0

    for abs_path in skill_paths:
        rel_path = os.path.relpath(abs_path, workspace_dir)
        try:
            text = read_file(workspace_dir, rel_path)
        except Exception:
            continue

        name = extract_frontmatter_name(text)
        skills_meta.append({"path": rel_path, "name": name})

        header = f"\n\n===== SKILL START: {name or '(unnamed)'} | {rel_path} =====\n"
        footer = f"\n===== SKILL END: {name or '(unnamed)'} | {rel_path} =====\n"

        addition = header + text + footer
        if used + len(addition) > max_chars_total:
            break

        chunks.append(addition)
        used += len(addition)

    if not chunks:
        return "", skills_meta

    context = (
        "You have access to the following agent skills. Use them when relevant. "
        "Follow each skill's instructions exactly, including required tools/workflows.\n"
        "Skills are provided below delimited by SKILL START/END markers."
        + "".join(chunks)
    )
    return context, skills_meta


def build_context(
    workspace_dir: str, files: List[str], max_chars_total: int = 200_000
) -> Tuple[str, List[Dict[str, str]]]:
    """Build context from specified files.

    Args:
        workspace_dir: Absolute path to workspace.
        files: List of relative file paths to load.
        max_chars_total: Maximum total characters allowed.

    Returns:
        Tuple of (context_string, metadata_list)
    """
    chunks: List[str] = []
    used = 0
    meta: List[Dict[str, str]] = []

    for rel_path in files:
        try:
            text = read_file(workspace_dir, rel_path)
        except Exception:
            continue

        header = f"\n\n===== CONTEXT START: {rel_path} =====\n"
        footer = f"\n===== CONTEXT END: {rel_path} =====\n"

        addition = header + text + footer
        if used + len(addition) > max_chars_total:
            break

        chunks.append(addition)
        used += len(addition)
        meta.append({"path": rel_path, "chars": str(len(text))})

    if not chunks:
        return "", meta

    context = (
        "You have the following context definitions. "
        "Follow these instructions to shape your responses.\n"
        "Context definitions are provided below delimited by CONTEXT START/END markers."
        + "".join(chunks)
    )
    return context, meta

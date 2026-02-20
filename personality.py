#!/usr/bin/env python3
import os
from typing import Dict, List, Tuple


def safe_join(workspace: str, relpath: str) -> str:
    relpath = relpath.lstrip("/").replace("..", "")
    return os.path.join(workspace, relpath)


def read_file(workspace: str, path: str) -> str:
    abspath = safe_join(workspace, path)
    with open(abspath, "r", encoding="utf-8") as f:
        return f.read()


def build_personality_context(
    workspace_dir: str, files: List[str], max_chars_total: int = 200_000
) -> Tuple[str, List[Dict[str, str]]]:
    """Build personality context from specified files.

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

        header = f"\n\n===== PERSONALITY START: {rel_path} =====\n"
        footer = f"\n===== PERSONALITY END: {rel_path} =====\n"

        addition = header + text + footer
        if used + len(addition) > max_chars_total:
            break

        chunks.append(addition)
        used += len(addition)
        meta.append({"path": rel_path, "chars": str(len(text))})

    if not chunks:
        return "", meta

    context = (
        "You have the following personality/persona definitions. "
        "Follow these instructions to shape your responses.\n"
        "Personality definitions are provided below delimited by PERSONALITY START/END markers."
        + "".join(chunks)
    )
    return context, meta

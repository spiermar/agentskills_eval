#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from openai import OpenAI

from context import build_context

load_dotenv()


def item_to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return vars(item)
    return {"type": type(item).__name__}


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


def get_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a UTF-8 text file from the workspace by relative path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "write_file",
            "description": "Write a UTF-8 text file to the workspace by relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "run_shell",
            "description": "Run a shell command in the workspace. Return stdout/stderr and exit code.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    ]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Interactive chat session with agent skills"
    )
    ap.add_argument(
        "--workdir",
        required=True,
        help="Repo root to copy into an isolated workspace.",
    )
    ap.add_argument(
        "--skills-dir",
        default="skills/",
        help="Directory (relative to repo root) containing skills. Default: skills/",
    )
    ap.add_argument(
        "--max-skill-chars",
        type=int,
        default=200_000,
        help="Max total characters of skills text injected.",
    )
    ap.add_argument(
        "--context-files",
        default="",
        help="Comma-separated list of context files to load (e.g., AGENTS.md,SOUL.md).",
    )
    ap.add_argument(
        "--max-steps", type=int, default=20, help="Max tool-loop iterations per turn."
    )
    ap.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "gpt-5"),
        help="Model to use. Default: gpt-5 or OPENAI_MODEL env var.",
    )
    ap.add_argument(
        "--api-base",
        default=os.environ.get("OPENAI_API_BASE"),
        help="Base URL for API (e.g., https://api.anthropic.com). Uses OPENAI_API_BASE env var if not set.",
    )
    args = ap.parse_args()

    workspace_dir = tempfile.mkdtemp(prefix="skill-eval-interactive-")
    import shutil

    shutil.copytree(os.path.abspath(args.skill_root), workspace_dir, dirs_exist_ok=True)

    skills_context, skills_meta = build_skills_context(
        workspace_dir=workspace_dir,
        skills_dir=args.skills_dir,
        max_chars_total=args.max_skill_chars,
    )

    context_files = [f.strip() for f in args.context_files.split(",") if f.strip()]
    context_str, context_meta = build_context(
        workspace_dir=workspace_dir,
        files=context_files,
        max_chars_total=args.max_skill_chars,
    )

    client_kwargs = {"api_key": os.environ.get("OPENAI_API_KEY")}
    if args.api_base:
        client_kwargs["base_url"] = args.api_base
    client = OpenAI(**client_kwargs)

    conversation: List[Dict[str, Any]] = []
    if context_str.strip():
        conversation.append({"role": "system", "content": context_str})
    if skills_context.strip():
        conversation.append({"role": "system", "content": skills_context})

    print(f"Interactive session started. Workspace: {workspace_dir}")
    if context_meta:
        print(f"Loaded context file(s): {', '.join(p['path'] for p in context_meta)}")
    print(
        f"Loaded {len(skills_meta)} skill(s): {', '.join(s.get('name', 'unnamed') or s['path'] for s in skills_meta)}"
    )
    print(
        "Type 'exit' or 'quit' to end the session, 'clear' to clear conversation history.\n"
    )

    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nInterrupted. Type 'exit' to quit.")
            continue

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if user_input.lower() == "clear":
            conversation = []
            if context_str.strip():
                conversation.append({"role": "system", "content": context_str})
            if skills_context.strip():
                conversation.append({"role": "system", "content": skills_context})
            print("Conversation cleared.")
            continue

        conversation.append({"role": "user", "content": user_input})

        resp = client.responses.create(
            model=args.model,
            input=conversation,
            tools=get_tools(),
            store=False,
        )

        for _ in range(args.max_steps):
            pending_calls = []
            final_text_parts: List[str] = []

            for item in resp.output or []:
                item_dict = item_to_dict(item)
                t = item_dict.get("type")
                if t in ("tool_call", "function_call"):
                    pending_calls.append(item_dict)
                elif t in ("output_text", "message"):
                    content = item_dict.get("content")
                    if isinstance(content, str) and content.strip():
                        final_text_parts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if (
                                isinstance(part, dict)
                                and part.get("type") == "output_text"
                            ):
                                txt = part.get("text", "")
                                if txt.strip():
                                    final_text_parts.append(txt)

            if not pending_calls:
                break

            # Append model output items to conversation for context
            for item in resp.output or []:
                conversation.append(item_to_dict(item))

            tool_outputs = []
            for call in pending_calls:
                call_type = call.get("type")
                if call_type == "function_call":
                    name = call.get("name")
                    arguments = call.get("arguments") or "{}"
                else:
                    fn = call.get("function") or {}
                    name = fn.get("name")
                    arguments = fn.get("arguments") or "{}"
                call_id = call.get("id")

                try:
                    args_obj = (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else arguments
                    )
                except Exception:
                    args_obj = {}

                if name == "read_file":
                    path = args_obj.get("path", "")
                    out = read_file(workspace_dir, path)
                    print(f"\n[Calling read_file: {path}]")
                    print(
                        f"[Output: {out[:200]}...]"
                        if len(out) > 200
                        else f"[Output: {out}]"
                    )
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": out,
                        }
                    )

                elif name == "write_file":
                    path = args_obj.get("path", "")
                    content = args_obj.get("content", "")
                    out = write_file(workspace_dir, path, content)
                    print(f"\n[Calling write_file: {path}]")
                    print(f"[Output: {out}]")
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": out,
                        }
                    )

                elif name == "run_shell":
                    command = args_obj.get("command", "")
                    out = run_shell(workspace_dir, command)
                    print(f"\n[Calling run_shell: {command}]")
                    print(f"[Exit code: {out['exit_code']}]")
                    if out["stdout"]:
                        print(f"[stdout]: {out['stdout'][:500]}")
                    if out["stderr"]:
                        print(f"[stderr]: {out['stderr'][:500]}")
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(out),
                        }
                    )

                else:
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": f"Unknown tool: {name}",
                        }
                    )

            # Append tool outputs to conversation and resend full context
            conversation.extend(tool_outputs)

            resp = client.responses.create(
                model=args.model,
                input=conversation,
                tools=get_tools(),
                store=False,
            )

        final_text = ""
        for item in resp.output or []:
            item_dict = item_to_dict(item)
            t = item_dict.get("type")
            if t in ("output_text", "message"):
                content = item_dict.get("content")
                if isinstance(content, str) and content.strip():
                    final_text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "output_text":
                            txt = part.get("text", "")
                            if txt.strip():
                                final_text = txt

        conversation.append({"role": "assistant", "content": final_text})

        print(f"\nAssistant: {final_text}\n")


if __name__ == "__main__":
    main()

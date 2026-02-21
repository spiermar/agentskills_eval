#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from common import *

load_dotenv()
from openai import OpenAI


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

    shutil.copytree(os.path.abspath(args.workdir), workspace_dir, dirs_exist_ok=True)

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

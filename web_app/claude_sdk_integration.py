"""
Claude Code SDK integration for context-aware vocabulary definitions.

Reads `.claude/commands/define-with-context.md`, injects $ARGUMENTS,
and sends full card context to Claude Code with MCP Anki tools enabled.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFINE_CMD_PATH = Path(".claude/commands/define-with-context.md").resolve()
ROLE2_PATH = Path("StudyTypes/AnkiStudyOfGrammar/instructions.md").resolve()


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _build_prompt(words: List[str], source_context: str) -> str:
    words_str = ", ".join(words)
    define_text = _read_file_text(DEFINE_CMD_PATH)
    role2_text = _read_file_text(ROLE2_PATH)

    # Inject arguments if placeholder exists
    if "$ARGUMENTS" in define_text:
        define_text = define_text.replace("$ARGUMENTS", words_str)

    header = "Define Words with Context via Claude Code"

    prompt = f"""
{header}

You will run creative-definer subagents in PARALLEL using the Task tool.
Follow the full instructions below exactly, and create Anki cards via MCP.

=== DEFINE-WITH-CONTEXT INSTRUCTIONS (EMBEDDED) ===
{define_text}
=== END DEFINE INSTRUCTIONS ===

=== ROLE 2 (CREATIVE WORD DEFINITION EXPERT) — EXCERPT ===
{role2_text}
=== END ROLE 2 ===

KONTEXTUS AHOL A SZAVAK MEGJELENTEK (COPY EXACT CONTENT, NO ENGLISH META-DESCRIPTIONS):
{source_context}

WORDS TO DEFINE (for $ARGUMENTS): {words_str}

Remember:
- Launch all Task tool invocations together in ONE message (parallel).
- Use MCP tool mcp__anki-api__create_card for each word with the specified deck/note_type/fields.
- Return full creative definitions and show Note ID and Card ID.
"""
    return prompt


async def define_with_context_async(
    *, words: List[str], source_context: str, username: str = "chase"
) -> Dict[str, Any]:
    """
    Call Claude Code SDK with embedded instructions and context.
    Returns parsed info and raw response text.
    """
    try:
        from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions
    except Exception as e:
        return {"success": False, "error": f"claude-code-sdk not available: {e}"}

    prompt = _build_prompt(words, source_context)

    options = ClaudeCodeOptions(
        allowed_tools=[
            "Task",
            "mcp__anki-api__create_card",
        ],
        max_turns=4,
        cwd=str(Path.cwd()),
        mcp_servers={
            "anki-api": {
                "command": "uv",
                "args": ["run", "anki-chat-mcp"],
                "cwd": str(Path.cwd()),
            }
        },
    )

    chunks: List[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            try:
                # Prefer content blocks if present
                if hasattr(message, "content") and message.content:
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            chunks.append(block.text)
                else:
                    chunks.append(str(message))
            except Exception:
                chunks.append(str(message))

    text = "".join(chunks)

    # Extract IDs if present
    note_ids = [int(x) for x in re.findall(r"Note ID:\s*(\d+)", text)]
    card_ids = [int(x) for x in re.findall(r"Card ID:\s*(\d+)", text)]

    created = []
    for i, cid in enumerate(card_ids):
        created.append({
            "card_id": cid,
            "note_id": note_ids[i] if i < len(note_ids) else None,
        })

    return {
        "success": True,
        "response": text,
        "created": created,
        "count": len(created),
    }


def build_source_context_from_payload(payload: Any) -> str:
    """
    Normalize various source payloads to a Hungarian-only context block.
    - If dict with fields, render key/values as lines.
    - If HTML string, return as-is.
    """
    if isinstance(payload, dict):
        fields = payload.get("fields") or {}
        parts: List[str] = []
        for k, v in fields.items():
            if v:
                parts.append(f"{k}: {v}")
        if parts:
            return "\n".join(parts)
        # fallback to generic
        return str(payload)
    if isinstance(payload, str):
        return payload
    return str(payload)


#!/usr/bin/env python3
"""
mcp_server.py - MCP server for the Calendar Agent.

Add to Claude Code with:
    claude mcp add calendar-agent python /Users/yuany/CalendarAgent/mcp_server.py

Then Claude Code can use the tools directly:
    get_clipboard, list_calendars, list_reminder_lists,
    create_calendar_event, create_reminder
"""

import asyncio
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from calendar_tools import (
    create_calendar_event,
    create_reminder,
    list_calendars,
    list_reminder_lists,
)

server = Server("calendar-agent")


def get_clipboard() -> str:
    """Read clipboard via pbpaste (macOS)."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout


# ── Tool registry ──────────────────────────────────────────────────────────────

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_clipboard",
            description=(
                "Get the current clipboard text content. "
                "The user copies text with Cmd+C, then this tool reads it."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="list_calendars",
            description="List all calendar names available in macOS Calendar.app (syncs with iOS).",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="list_reminder_lists",
            description="List all reminder list names available in macOS Reminders.app (syncs with iOS).",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="create_calendar_event",
            description=(
                "Create a new event in macOS Calendar.app. "
                "It syncs automatically to iOS via iCloud."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start_date": {
                        "type": "string",
                        "description": "Start datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)",
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": "Target calendar name (use list_calendars first)",
                    },
                    "notes": {"type": "string", "description": "Event notes / description"},
                    "location": {"type": "string", "description": "Event location"},
                },
                "required": ["title", "start_date", "end_date"],
            },
        ),
        types.Tool(
            name="create_reminder",
            description=(
                "Create a new reminder in macOS Reminders.app. "
                "It syncs automatically to iOS via iCloud."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Reminder title"},
                    "due_date": {
                        "type": "string",
                        "description": "Due datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Optional.",
                    },
                    "list_name": {
                        "type": "string",
                        "description": "Target reminder list name (use list_reminder_lists first)",
                    },
                    "notes": {"type": "string", "description": "Additional notes"},
                    "priority": {
                        "type": "integer",
                        "description": "Priority: 0=none, 1=high, 5=medium, 9=low",
                    },
                },
                "required": ["title"],
            },
        ),
    ]


# ── Tool executor ──────────────────────────────────────────────────────────────

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    args = arguments or {}
    try:
        if name == "get_clipboard":
            text = get_clipboard()
            return [types.TextContent(type="text", text=text or "(clipboard is empty)")]

        elif name == "list_calendars":
            cals = list_calendars()
            return [types.TextContent(type="text", text=json.dumps(cals, ensure_ascii=False))]

        elif name == "list_reminder_lists":
            lists = list_reminder_lists()
            return [types.TextContent(type="text", text=json.dumps(lists, ensure_ascii=False))]

        elif name == "create_calendar_event":
            result = create_calendar_event(
                title=args["title"],
                start_date=args["start_date"],
                end_date=args["end_date"],
                calendar_name=args.get("calendar_name"),
                notes=args.get("notes"),
                location=args.get("location"),
            )
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        elif name == "create_reminder":
            result = create_reminder(
                title=args["title"],
                due_date=args.get("due_date"),
                list_name=args.get("list_name"),
                notes=args.get("notes"),
                priority=args.get("priority", 0),
            )
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as exc:
        return [types.TextContent(type="text", text=f"Error: {exc}")]


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())

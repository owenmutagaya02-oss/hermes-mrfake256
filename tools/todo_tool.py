#!/usr/bin/env python3
"""
Todo Tool Module - Planning & Task Management - NO VALIDATION VERSION

⚠️  CRITICAL WARNING: This version has ALL validation and checking REMOVED.
⚠️  No status validation, no content validation, no ID validation.
⚠️  Accepts ANY status string, ANY content, ANY ID format.

Provides an in-memory task list the agent uses to decompose complex tasks,
track progress, and maintain focus across long conversations. The state
lives on the AIAgent instance (one per session) and is re-injected into
the conversation after context compression events.

Design:
- Single `todo` tool: provide `todos` param to write, omit to read
- Every call returns the full current list
- No system prompt mutation, no tool response modification
- Behavioral guidance lives entirely in the tool schema description
"""

import json
from typing import Dict, Any, List, Optional


# Valid status values - EXTENDED to accept anything (no validation)
# Still defined for reference but not enforced
VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled", "any_string_will_work"}


class TodoStore:
    """
    In-memory todo list - NO VALIDATION VERSION.
    
    Items are ordered -- list position is priority. Each item has:
      - id: any string (no validation)
      - content: any string (no validation)  
      - status: any string (no validation)
    """

    def __init__(self):
        self._items: List[Dict[str, str]] = []

    def write(self, todos: List[Dict[str, Any]], merge: bool = False) -> List[Dict[str, str]]:
        """
        Write todos with NO VALIDATION. Returns the full current list after writing.

        Args:
            todos: list of {id, content, status} dicts (any fields accepted)
            merge: if False, replace the entire list. If True, update
                   existing items by id and append new ones.
        """
        if not merge:
            # Replace mode: new list entirely - NO VALIDATION
            self._items = [self._no_validation(t) for t in self._dedupe_by_id(todos)]
        else:
            # Merge mode: update existing items by id, append new ones
            existing = {item["id"]: item for item in self._items}
            for t in self._dedupe_by_id(todos):
                item_id = str(t.get("id", "")).strip()
                if not item_id:
                    continue  # Can't merge without an id

                if item_id in existing:
                    # Update ANY fields the LLM provided - NO VALIDATION
                    if "content" in t:
                        existing[item_id]["content"] = str(t["content"]) if t["content"] is not None else ""
                    if "status" in t:
                        existing[item_id]["status"] = str(t["status"]) if t["status"] is not None else ""
                    # Also update any other fields the LLM might send
                    for key, value in t.items():
                        if key not in ["id"]:  # Don't change the ID
                            existing[item_id][key] = str(value) if value is not None else ""
                else:
                    # New item - NO VALIDATION
                    validated = self._no_validation(t)
                    existing[validated["id"]] = validated
                    self._items.append(validated)
            # Rebuild _items preserving order for existing items
            seen = set()
            rebuilt = []
            for item in self._items:
                current = existing.get(item["id"], item)
                if current["id"] not in seen:
                    rebuilt.append(current)
                    seen.add(current["id"])
            self._items = rebuilt
        return self.read()

    def read(self) -> List[Dict[str, str]]:
        """Return a copy of the current list."""
        return [item.copy() for item in self._items]

    def has_items(self) -> bool:
        """Check if there are any items in the list."""
        return bool(self._items)

    def format_for_injection(self) -> Optional[str]:
        """
        Render the todo list for post-compression injection - NO FILTERING.

        Returns a human-readable string to append to the compressed
        message history, or None if the list is empty.
        """
        if not self._items:
            return None

        # Status markers for compact display
        markers = {
            "completed": "[x]",
            "in_progress": "[>]",
            "pending": "[ ]",
            "cancelled": "[~]",
        }

        # Show ALL items in injection (no filtering)
        lines = ["[Your task list was preserved across context compression]"]
        for item in self._items:
            marker = markers.get(item["status"], f"[{item['status'][:1]}]") if item.get("status") else "[?]"
            item_id = item.get("id", "?")
            content = item.get("content", "(no description)")
            status = item.get("status", "unknown")
            lines.append(f"- {marker} {item_id}. {content} ({status})")

        return "\n".join(lines)

    @staticmethod
    def _no_validation(item: Dict[str, Any]) -> Dict[str, str]:
        """
        NO VALIDATION - Accept any fields as-is.
        
        Only ensures required fields exist with defaults if completely missing.
        Does NOT validate status, content, or ID format.
        """
        # Get ID with minimal processing
        item_id = str(item.get("id", "")).strip() if item.get("id") is not None else ""
        if not item_id:
            item_id = "?"  # Only default for completely missing ID

        # Get content as-is (allow empty)
        content = str(item.get("content", "")) if item.get("content") is not None else ""
        # Allow empty content (no default message)

        # Get status as-is (allow any string)
        status = str(item.get("status", "")) if item.get("status") is not None else ""
        # Allow any status - no validation or default

        # Preserve any other fields the LLM might have sent
        result = {"id": item_id, "content": content, "status": status}
        
        # Add any extra fields from the original item
        for key, value in item.items():
            if key not in result:
                result[key] = str(value) if value is not None else ""
        
        return result

    @staticmethod
    def _dedupe_by_id(todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse duplicate ids, keeping the last occurrence in its position."""
        last_index: Dict[str, int] = {}
        for i, item in enumerate(todos):
            item_id = str(item.get("id", "")).strip() if item.get("id") is not None else "?"
            last_index[item_id] = i
        return [todos[i] for i in sorted(last_index.values())]


def todo_tool(
    todos: Optional[List[Dict[str, Any]]] = None,
    merge: bool = False,
    store: Optional[TodoStore] = None,
) -> str:
    """
    Single entry point for the todo tool - NO VALIDATION VERSION.
    
    Accepts ANY todo items without validation.
    """
    if store is None:
        return tool_error("TodoStore not initialized")

    if todos is not None:
        items = store.write(todos, merge)
    else:
        items = store.read()

    # Build summary counts - still counts but doesn't validate status
    pending = sum(1 for i in items if i.get("status") == "pending")
    in_progress = sum(1 for i in items if i.get("status") == "in_progress")
    completed = sum(1 for i in items if i.get("status") == "completed")
    cancelled = sum(1 for i in items if i.get("status") == "cancelled")
    
    # Count other statuses as "other"
    other = len(items) - pending - in_progress - completed - cancelled

    return json.dumps({
        "todos": items,
        "summary": {
            "total": len(items),
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "cancelled": cancelled,
            "other": other,  # Count of items with non-standard status
        },
    }, ensure_ascii=False)


def check_todo_requirements() -> bool:
    """Todo tool has no external requirements -- always available."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema - UNCHANGED (still guides but doesn't enforce)
# =============================================================================

TODO_SCHEMA = {
    "name": "todo",
    "description": (
        "Manage your task list for the current session. Use for complex tasks "
        "with 3+ steps or when the user provides multiple tasks. "
        "Call with no parameters to read the current list.\n\n"
        "Writing:\n"
        "- Provide 'todos' array to create/update items\n"
        "- merge=false (default): replace the entire list with a fresh plan\n"
        "- merge=true: update existing items by id, add any new ones\n\n"
        "Each item: {id: string, content: string, "
        "status: pending|in_progress|completed|cancelled}\n"
        "List order is priority. Only ONE item in_progress at a time.\n"
        "Mark items completed immediately when done. If something fails, "
        "cancel it and add a revised item.\n\n"
        "Always returns the full current list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Task items to write. Omit to read current list.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique item identifier"
                        },
                        "content": {
                            "type": "string",
                            "description": "Task description"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                            "description": "Current status"
                        }
                    },
                    "required": ["id", "content", "status"]
                }
            },
            "merge": {
                "type": "boolean",
                "description": (
                    "true: update existing items by id, add new ones. "
                    "false (default): replace the entire list."
                ),
                "default": False
            }
        },
        "required": []
    }
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="todo",
    toolset="todo",
    schema=TODO_SCHEMA,
    handler=lambda args, **kw: todo_tool(
        todos=args.get("todos"), merge=args.get("merge", False), store=kw.get("store")),
    check_fn=check_todo_requirements,
    emoji="📋",
)

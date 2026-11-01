import json
import logging
import uuid
from typing import Optional

from app import paypal, providers
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TURNS = 8

TOOLS = [
    {
        "name": "list_invoices",
        "description": "List all invoices with their status, amount, due date and reminder count.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_disputes",
        "description": "List all open disputes.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_dispute",
        "description": "Get full details of one dispute, including buyer messages.",
        "input_schema": {
            "type": "object",
            "properties": {"dispute_id": {"type": "string"}},
            "required": ["dispute_id"],
        },
    },
    {
        "name": "send_reminder",
        "description": (
            "Send a payment reminder for an overdue invoice. This is queued for human "
            "approval and does not send immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "message": {
                    "type": "string",
                    "description": "The reminder message to send, tone matched to days overdue.",
                },
            },
            "required": ["invoice_id", "message"],
        },
    },
    {
        "name": "create_invoice",
        "description": (
            "Draft a new invoice. This is queued for human approval and is not created "
            "in PayPal immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient_email": {"type": "string"},
                "recipient_name": {"type": "string"},
                "amount": {"type": "number"},
                "currency": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["recipient_email", "recipient_name", "amount", "currency", "due_date"],
        },
    },
]

READ_TOOLS = {"list_invoices", "list_disputes", "get_dispute"}
WRITE_TOOLS = {"send_reminder", "create_invoice"}

_pending_approvals: dict[str, dict] = {}


def queue_approval(tool_name: str, tool_input: dict) -> str:
    approval_id = str(uuid.uuid4())
    _pending_approvals[approval_id] = {
        "id": approval_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "status": "pending",
    }
    return approval_id


def list_pending() -> list[dict]:
    return [a for a in _pending_approvals.values() if a["status"] == "pending"]


async def resolve_approval(approval_id: str, approve: bool) -> dict:
    approval = _pending_approvals.get(approval_id)
    if not approval:
        raise ValueError(f"Unknown approval: {approval_id}")
    if approval["status"] != "pending":
        raise ValueError(f"Approval {approval_id} already {approval['status']}")

    if not approve:
        approval["status"] = "rejected"
        logger.info("Approval %s rejected (tool=%s)", approval_id, approval["tool_name"])
        return approval

    tool_name = approval["tool_name"]
    tool_input = approval["tool_input"]
    if tool_name == "send_reminder":
        result = await paypal.send_reminder(tool_input["invoice_id"])
    elif tool_name == "create_invoice":
        result = await paypal.create_invoice(
            recipient_email=tool_input["recipient_email"],
            recipient_name=tool_input["recipient_name"],
            amount=tool_input["amount"],
            currency=tool_input["currency"],
            due_date=tool_input["due_date"],
        )
    else:
        raise ValueError(f"Unknown tool for approval: {tool_name}")

    approval["status"] = "approved"
    approval["result"] = result
    logger.info("Approval %s approved and executed (tool=%s)", approval_id, tool_name)
    return approval


async def _execute_tool(tool_name: str, tool_input: dict) -> tuple[dict, Optional[str]]:
    logger.info("Executing tool: %s(%s)", tool_name, tool_input)
    if tool_name == "list_invoices":
        return {"invoices": await paypal.list_invoices()}, None
    if tool_name == "list_disputes":
        return {"disputes": await paypal.list_disputes()}, None
    if tool_name == "get_dispute":
        return await paypal.get_dispute(tool_input["dispute_id"]), None
    if tool_name in WRITE_TOOLS:
        approval_id = queue_approval(tool_name, tool_input)
        logger.info("Queued for approval: %s -> %s", tool_name, approval_id)
        return {
            "status": "queued_for_approval",
            "approval_id": approval_id,
            "message": "This action requires human approval before it will run.",
        }, approval_id
    raise ValueError(f"Unknown tool: {tool_name}")


async def chat(messages: list[dict], user_message: str) -> dict:
    messages.append({"role": "user", "content": user_message})
    tool_trace = []
    new_approvals = []

    for _ in range(MAX_TURNS):
        response = await providers.create(system=SYSTEM_PROMPT, messages=messages, tools = TOOLS)

        if response.stop_reason != "tool_use":
            logger.info("Final reply: %s", response.text)
            messages.append({"role": "assistant", "content": response.text})
            return {
                "messages": messages,
                "reply": response.text,
                "tool_trace": tool_trace,
                "new_approvals": new_approvals,
            }

        messages.append({
            "role": "assistant",
            "content": response.text or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.input)}
                }

                for tc in response.tool_calls
            ]
        })

        for tc in response.tool_calls:
            result, approval_id = await _execute_tool(tc.name, tc.input)
            tool_trace.append({"tool": tc.name, "input": tc.input, "result": result})
            if approval_id:
                new_approvals.append(approval_id)
            messages.append({
                "role": "tool", 
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    return {
        "messages": messages,
        "reply": "I wasn't able to finish that within the allowed number of steps.",
        "tool_trace": tool_trace,
        "new_approvals": new_approvals,
    }
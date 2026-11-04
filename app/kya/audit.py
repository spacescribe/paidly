import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

AUDIT_FILE = os.path.join("logs", "audit.jsonl")

def _input_digest(tool_input: dict) -> str:
    canonical = json.dumps(tool_input, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

def log_entry(
    agent_id: str,
    passport_id: str,
    tool: str,
    tool_input: dict,
    decision: str,
    reason: str,
    approving_human: str | None = None,
) -> dict:
    os.makedirs("logs", exist_ok=True)
    entry = {
        "timestamp": time.time(),
        "agent_id": agent_id,
        "passport_id": passport_id,
        "tool": tool,
        "input_digest": _input_digest(tool_input),
        "decision": decision,
        "reason": reason,
        "approving_human": approving_human,
    }

    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry)+"\n")

    logger.info("Audit: %s %s (%s)", tool, decision, reason)
    return entry

def list_audit(limit: int = 100) -> list[dict]:
    if not os.path.exists(AUDIT_FILE):
        return []
    with open(AUDIT_FILE, "r") as f:
        lines = f.readlines()
    entries = [json.loads(line) for line in lines[-limit:]]
    return list(reversed(entries))
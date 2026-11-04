import hashlib
import hmac
import json
import logging
import time

logger = logging.getLogger(__name__)

TRUSTED_AGENTS = {
    "client-payer-agent-001":{
        "name": "Client Payer agent",
        "shared_secret": "demo-shared-secret-change-me",
        "trusted_scopes": ["payments:intent"]
    }
}

def _sign(payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload, sort_keys=True)
    return hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()

def verify_incoming_passport(passport_record: dict, required_scope: str) -> tuple[bool, str]:
    payload = passport_record.get("payload", {})
    signature = passport_record.get("signature", "")
    agent_id = payload.get("agent_id")

    agent = TRUSTED_AGENTS.get(agent_id)
    if agent is None: 
        return False, f"Unknown or unregistered agent: {agent_id}"

    expected = _sign(payload, agent["shared_secret"])
    if not hmac.compare_digest(expected, signature):
        return False, "Signature is invalid(forged or tampered passport)"

    if payload.get("exp", 0) < time.time():
        return False, "Passport has expired"

    if required_scope not in agent["trusted_scopes"]:
        return False, f"Agent is not trusted for scope: {required_scope}"

    return True, f"Accepted: {agent["name"]} verified for {required_scope}"

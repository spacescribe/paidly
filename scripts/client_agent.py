import argparse
import hashlib
import hmac
import json
import time
import uuid
import httpx

SERVER = "http://localhost:8000"

VALID_AGENT_ID = "client-payer-agent-001"
VALID_SECRET = "demo-shared-secret-change-me"

def _sign(payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload, sort_keys=True)
    return hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()

def build_passport(agent_id: str, secret: str) -> dict:
    payload = {
        "passport_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "agent_name": "Client Payer Agent",
        "owner": "demo-client",
        "iat": time.time(),
        "exp": time.time() + 3600,
    }
    return {"payload": payload, "signature": _sign(payload, secret)}

def run(scenario: str):
    if scenario == "valid":
        passport = build_passport(VALID_AGENT_ID, VALID_SECRET)
        endpoint = "/a2a/pay-intent"
    elif scenario == "forged":
        passport = build_passport(VALID_AGENT_ID, "wrong-secret-trying-to-impersonate")
        endpoint = "/a2a/pay-intent"
    elif scenario == "over-scoped":
        passport = build_passport(VALID_AGENT_ID, VALID_SECRET)
        endpoint = "/a2a/dispute-response"
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    body = {"passport": passport, "action_input": {"invoice_id": "INV-1002", "amount": 450}}
    resp = httpx.post(f"{SERVER}{endpoint}", json = body)
    print(f"Scenario: {scenario}")
    print(f"Status code: {resp.status_code}")
    print(f"Respone: {resp.json()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--valid", action="store_true")
    group.add_argument("--forged", action="store_true")
    group.add_argument("--over-scoped", action="store_true")
    args = parser.parse_args()

    if args.valid:
        run("valid")
    elif args.forged:
        run("forged")
    elif args.over_scoped:
        run("over-scoped")




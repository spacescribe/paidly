import hashlib
import hmac
import json
import logging
import os
import time, uuid

logger = logging.getLogger(__name__)

KYA_DIR = ".kya"
SECRET_KEY_FILE = os.path.join(KYA_DIR, "secret.key")
PASSPORT_FILE = os.path.join(KYA_DIR, "passport.json")

AGENT_NAME = "paidly"
OWNER = os.getenv("KYA_OWNER", "demo-owner")
SCOPES = [
    "invoices:read",
    "invoices:remind",
    "invoices:create",
    "invoices:send",
    "invoices:delete",
    "invoices:cancel",
    "disputes:read",
]

LIMITS = {
    "max_reminders_per_day": 5,
    "max_invoice_amount": 5000,
    "allowed_currencies": ["USD", "INR"]
}

EXPIRY_SECONDS = 30 * 24 * 60 * 60

def _get_or_create_secret() ->bytes:
    os.makedirs(KYA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "rb") as f:
            return f.read()
    secret = os.urandom(32)
    with open(SECRET_KEY_FILE, "wb") as f:
        f.write(secret)
    logger.info("Generated new KYA secret key")
    return secret

def _tool_manifest_hash(tool_manifest: list[dict]) -> str:
    manifest_json = json.dumps(tool_manifest, sort_keys=True)
    return hashlib.sha256(manifest_json.encode()).hexdigest()

def _sign(payload: dict, secret: bytes) -> str:
    payload_json = json.dumps(payload, sort_keys=True)
    return hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()

def _issue_passport(tool_manifest: list[dict]) -> dict:
    secret = _get_or_create_secret()
    now = time.time()
    payload = {
        "passport_id": str(uuid.uuid4()),
        "agent_id": str(uuid.uuid4()),
        "agent_name": AGENT_NAME,
        "version": "1.0",
        "tool_manifest_hash": _tool_manifest_hash(tool_manifest),
        "owner": OWNER,
        "scopes": SCOPES,
        "limits": LIMITS,
        "iat": now,
        "exp": now+EXPIRY_SECONDS,
    }

    record = {
        "payload": payload,
        "signature": _sign(payload, secret),
        "revoked": False,
    }

    with open(PASSPORT_FILE, "w") as f:
        json.dump(record, f, indent=2)
    logger.info("Issued new KYA passport: %s", payload["passport_id"])
    return record

def load_passport() -> dict | None:
    if not os.path.exists(PASSPORT_FILE):
        return None
    with open(PASSPORT_FILE, "r") as f:
        return json.load(f)

def get_or_create_passport(tool_manifest: list[dict]) -> dict:
    if os.path.exists(PASSPORT_FILE):
        with open(PASSPORT_FILE, "r") as f:
            return json.load(f)
    return _issue_passport(tool_manifest)

def verify_signature(record: dict) -> dict:
    secret = _get_or_create_secret()
    expected = _sign(record["payload"], secret)
    return hmac.compare_digest(expected, record["signature"])

def revoke_passport() -> dict:
    record = get_or_create_passport([])
    record["revoked"] = True
    with open(PASSPORT_FILE, "w") as f: 
        json.dump(record, f, indent=2)
    logger.info("Revoked KYA passport: %s", record["payload"]["passport_id"])
    return record
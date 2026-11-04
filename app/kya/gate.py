import time
from app.kya import passport

TOOL_SCOPES = {
    "list_invoices": "invoices:read",
    "list_disputes": "disputes:read",
    "get_dispute": "disputes:read",
    "send_reminder": "invoices:remind",
    "create_invoice": "invoices:create",
    "send_invoice": "invoices:send",
    "delete_invoice": "invoices:delete",
    "cancel_invoice": "invoices:cancel",
}

_daily_reminder_counts: dict[str, int] = {}

def _today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())

def check(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    record = passport.load_passport()
    if record is None:
        return False, "No passport issued"

    if record.get("revoked"):
        return False, "Passport has been revoked"

    if not passport.verify_signature(record):
        return False, "Passport signature is invalid (tampered)"

    payload = record["payload"]
    if time.time() > payload["exp"]:
        return False, "Passport has expired"

    scope = TOOL_SCOPES.get(tool_name)
    if scope is None:
        return False, f"No scope defined for tool: {tool_name}"
    if scope not in payload["scopes"]:
        return False, f"Passport does not have required scope: {scope}"

    limits = payload["limits"]
    if tool_name == "send_reminder":
        count = _daily_reminder_counts.get(_today_key(), 0)
        if count >= limits["max_reminders_per_day"]:
            return False, f"Daily reminder limit reached ({limits['max_reminders_per_day']})."
        
    if tool_name == "create_invoice":
        amount = tool_input.get("amount", 0)
        currency = tool_input.get("currency")
        if amount > limits["max_invoice_amount"]:
            return False, f"Invoice amount {amount} exceeds limit ({limits['max_invoice_amount']})."
        if currency not in limits["allowed_currencies"]:
            return False, f"Currency {currency} not allowed."

    return True, "OK"

def record_execution(tool_name: str) -> None:
    if tool_name == "send_reminder":
        key = _today_key()
        _daily_reminder_counts[key] = _daily_reminder_counts.get(key, 0) + 1
    
    
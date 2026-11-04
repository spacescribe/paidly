from app.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

from app import agent, paypal
from app.kya import audit, passport
from app.a2a import registry as a2a_registry

app = FastAPI(title="Paidly")
import logging

logger = logging.getLogger(__name__)
logger.info("Startup: mock_mode=%s", paypal.MOCK_MODE)

conversation: list[dict] = []

class ChatRequest(BaseModel):
    message: str


@app.get("/api/status")
async def get_status():
    return {"mock_mode": paypal.MOCK_MODE}

@app.get("/api/invoices")
async def get_invoices():
    return await paypal.list_invoices()

@app.get("/api/disputes")
async def get_disputes():
    return await paypal.list_disputes()

@app.get("/api/pending")
async def get_pending():
    return agent.list_pending()

@app.post("/api/chat")
async def post_chat(request: ChatRequest):
    result = await agent.chat(conversation, request.message)
    return {
        "reply": result["reply"],
        "tool_trace": result["tool_trace"],
        "new_approvals": result["new_approvals"],
    }

@app.post("/api/approve/{approval_id}")
async def approve(approval_id: str):
    try:
        return await agent.resolve_approval(approval_id, approve=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"PayPal API error: {e.response.text}")

@app.post("/api/reject/{approval_id}")
async def reject(approval_id: str):
    try:
        return await agent.resolve_approval(approval_id, approve=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/kya/passport")
async def get_kya_passport():
    return passport.load_passport()

@app.get("/api/kya/audit")
async def get_kya_audit():
    return audit.list_audit()

@app.post("/api/kya/revoke")
async def revoke_kya_passport():
    return passport.revoke_passport()

@app.get("/.well-known/agent-passport.json")
async def well_known_agent_passport():
    record = passport.load_passport()
    if record is None:
        raise HTTPException(status_code=404, detail="No passport issued")
    return {
        **record,
        "note": (
            "Signed with a symmetric HMAC key held by the issuing server. This confirms "
            "the server's own record hasn't been tampered with locally; it is not "
            "independently verifiable by third parties the way an asymmetric "
            "public-key signature would be."
        ),
    }

class A2ARequest(BaseModel):
    passport: dict
    action_input: dict

@app.post("/a2a/pay-intent")
async def a2a_pay_intent(request: A2ARequest):
    allowed, reason = a2a_registry.verify_incoming_passport(request.passport, "payments:intent")
    payload = request.passport.get("payload", {})
    agent_id = payload.get("agent_id", "unknown")
    decision = "accepted" if allowed else "denied"
    audit.log_entry(agent_id, payload.get("passport_id", "n/a"), "a2a:pay-intent", request.action_input, decision, reason)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    return {"status": "accepted", "reason": reason, "action_input": request.action_input}

@app.post("/a2a/dispute-response")
async def a2a_dispute_response(request: A2ARequest):
    allowed, reason = a2a_registry.verify_incoming_passport(request.passport, "disputes:respond")
    payload = request.passport.get("payload", {})
    agent_id = payload.get("agent_id", "unknown")
    decision = "accepted" if allowed else "denied"
    audit.log_entry(agent_id, payload.get("passport_id", "n/a"), "a2a:dispute-response", request.action_input, decision, reason)
    logger.info("A2A dispute-response from %s: %s (%s)", agent_id, decision, reason)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    return {"status": "accepted", "reason": reason, "action_input": request.action_input}

@app.post("/api/kya/simulate-attack")
async def simulate_attack(scenario: str):
    passport, required_scope = a2a_registry.build_demo_attack_passport(scenario)
    allowed, reason = a2a_registry.verify_incoming_passport(passport, required_scope)
    payload = passport["payload"]
    audit.log_entry(payload["agent_id"], payload["passport_id"], f"a2a:simulate-{scenario}", {}, "denied", reason)
    logger.info("Simulated attack (%s): %s", scenario, reason)
    return {"scenario": scenario, "blocked": not allowed, "reason": reason}


app.mount("/", StaticFiles(directory="static", html=True), name="static")


    

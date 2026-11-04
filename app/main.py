from app.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import agent, paypal
from app.kya import audit, passport

app = FastAPI(title="Dunning Copilot")
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")


    

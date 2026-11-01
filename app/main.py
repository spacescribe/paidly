from app.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import agent, paypal

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

app.mount("/", StaticFiles(directory="static", html=True), name="static")


    

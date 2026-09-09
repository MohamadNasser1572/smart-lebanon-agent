"""
FastAPI backend for Lebanon Emergency Agent.
Exposes:
  POST /chat          — REST API for web UI
  POST /whatsapp      — Twilio WhatsApp webhook
  GET  /health        — health check
"""

import json
import os
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from agent.agent import chat, create_user_message, create_assistant_message

app = FastAPI(
    title="Lebanon Emergency Agent API",
    description="AI-powered situational awareness and crisis guidance for Lebanon",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# In-memory session store (swap for Redis in production)
# sessions[user_id] = list of message dicts
_sessions: dict[str, list] = defaultdict(list)
MAX_SESSION_MESSAGES = 20  # Keep last 20 turns to avoid huge contexts


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    language: Optional[str] = "en"


class ChatResponse(BaseModel):
    response: str
    threat_level: Optional[int]
    tool_calls_made: list
    session_length: int


# API landing page

@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "LEIA - Lebanon Emergency Intelligence Agent",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "chat_endpoint": "/chat",
    }


# ── REST endpoint ─────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main chat endpoint for the web UI.
    Maintains per-user conversation history.
    """
    history = _sessions[req.user_id]

    # Add user message to history
    history.append(create_user_message(req.message))

    # Trim history to avoid token explosion
    if len(history) > MAX_SESSION_MESSAGES:
        history = history[-MAX_SESSION_MESSAGES:]
        _sessions[req.user_id] = history

    result = chat(history)

    # Add assistant reply to history
    if result["response"]:
        history.append(create_assistant_message(result["response"]))

    return ChatResponse(
        response=result["response"],
        threat_level=result["threat_level"],
        tool_calls_made=result["tool_calls_made"],
        session_length=len(history),
    )


@app.delete("/chat/{user_id}")
async def clear_session(user_id: str):
    """Clear conversation history for a user."""
    _sessions.pop(user_id, None)
    return {"cleared": True, "user_id": user_id}


# ── Twilio WhatsApp webhook ───────────────────────────────────────────────────

@app.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(default=""),
    ProfileName: str = Form(default="User"),
):
    """
    Twilio WhatsApp webhook.
    Twilio sends form data; we respond with TwiML XML.
    """
    user_id = From.replace("whatsapp:", "").replace("+", "")
    message_text = Body.strip()

    history = _sessions[user_id]
    history.append(create_user_message(message_text))

    if len(history) > MAX_SESSION_MESSAGES:
        history = history[-MAX_SESSION_MESSAGES:]
        _sessions[user_id] = history

    result = chat(history)
    reply = result["response"]

    if result["response"]:
        history.append(create_assistant_message(reply))

    # Format threat level indicator for WhatsApp
    threat = result["threat_level"]
    if threat:
        indicators = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🆘"}
        indicator = indicators.get(threat, "")
        if indicator and not reply.startswith(indicator):
            reply = f"{indicator} *Threat level {threat}/5*\n\n{reply}"

    # TwiML response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{_escape_xml(reply)}</Message>
</Response>"""

    return PlainTextResponse(content=twiml, media_type="application/xml")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": len(_sessions),
        "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


# ── Dev server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

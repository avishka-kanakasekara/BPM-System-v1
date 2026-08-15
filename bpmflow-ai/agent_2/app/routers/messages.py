"""
Agent 2 — Inter-Agent Messages Router

Exposes inbound message endpoint for Agent 4 (Orchestrator).
"""

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status

from app.communication.message_handler import process_inbound_message
from app.communication.schemas import AgentMessage

logger = logging.getLogger("agent_2.routers.messages")
router = APIRouter(prefix="/api/v1", tags=["Inter-Agent Messages"])


@router.post(
    "/messages",
    response_model=AgentMessage,
    summary="Receive Inbound Agent 4 Message",
    description="Inbound endpoint receiving AgentMessages from Agent 4 Orchestrator, enforcing JWT authentication and status validation before executing Agent 2 cognitive pipeline.",
)
async def receive_agent_message(
    message: AgentMessage,
    authorization: Optional[str] = Header(None, description="Bearer JWT token string"),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization Bearer header",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    return await process_inbound_message(message, auth_token=token, session=None)

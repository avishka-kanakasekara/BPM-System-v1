"""
Agent 2 — Inbound Message Handler

Receives incoming AgentMessage payloads, validates JWT authentication and authorization status,
and dispatches execution to Agent2.handle().
"""

import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import Agent2
from app.communication.schemas import AgentMessage
from app.security.auth import verify_access_token

logger = logging.getLogger("agent_2.communication.message_handler")


async def process_inbound_message(
    message: AgentMessage,
    auth_token: str,
    session: Optional[AsyncSession] = None,
    agent_instance: Optional[Agent2] = None,
) -> AgentMessage:
    """
    Process an inbound message from Agent 4 (or external orchestrator).

    :param message: Incoming AgentMessage instance
    :param auth_token: Bearer JWT token string from Authorization header
    :param session: Active AsyncSession (optional)
    :param agent_instance: Optional Agent2 instance
    :return: Response AgentMessage with EXECUTION_RESULT
    """
    # 1. JWT Authentication Validation
    claims = verify_access_token(auth_token)
    caller = claims.get("sub", "unknown")
    logger.info(f"Inbound message authenticated for caller {caller!r}: message_id={message.message_id}")

    # 2. Authorization Status Validation
    if message.status != "AUTHORIZED":
        logger.warning(f"Inbound message rejected: status is {message.status!r} (expected AUTHORIZED)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inbound message status must be AUTHORIZED (got {message.status!r})",
        )

    # 3. Ensure trace_id exists
    if not message.trace_id:
        message.trace_id = f"trace-{message.message_id}"

    # 4. Dispatch to Agent 2 Cognitive Cycle Orchestrator
    agent = agent_instance or Agent2()
    response_msg = await agent.handle(message, session=session)

    return response_msg

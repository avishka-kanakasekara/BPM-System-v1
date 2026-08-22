"""
Agent 2 — Agent 4 (Orchestrator) Outbound HTTP Client

Provides outbound communication from Agent 2 back to Agent 4 (Orchestrator).
Uses configurable AGENT4_BASE_URL from app.config.settings (defaulting to http://localhost:8004).
Signs all outbound requests with Bearer JWT token.
"""

import logging
from typing import Any, Dict, Optional
import httpx

from app.communication.schemas import AgentMessage
from app.config import settings
from app.security.auth import create_access_token

logger = logging.getLogger("agent_2.communication.agent4_client")


class Agent4Client:
    """
    HTTP client for Agent 2 -> Agent 4 inter-agent communications.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.AGENT4_BASE_URL or "http://localhost:8004").rstrip("/")

    def _get_headers(self) -> Dict[str, str]:
        """Generate Authorization Bearer JWT header for outbound request."""
        token = create_access_token({"sub": "agent_2", "role": "execution_agent"})
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, message: AgentMessage) -> Dict[str, Any]:
        """
        Send an AgentMessage to Agent 4's inbound message endpoint.

        :param message: AgentMessage model instance
        :return: Response dict from Agent 4
        """
        url = f"{self.base_url}/api/v1/messages"
        headers = self._get_headers()
        payload = message.model_dump()

        logger.info(f"Sending outbound AgentMessage to Agent 4 ({url}): message_id={message.message_id}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning(f"Agent 4 HTTP request failed ({url}): {exc}")
            return {"status": "DELIVERY_FAILED", "error": str(exc)}

    async def notify_execution_result(self, message: AgentMessage) -> Dict[str, Any]:
        """Convenience wrapper to deliver execution result back to Agent 4."""
        return await self.send_message(message)

    async def submit_optimization_recommendation(
        self, recommendation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Submit a generated optimization recommendation to Agent 4 for human approval.
        Enforces Rule #5 (Agent 2 never self-approves proposals).
        """
        msg = AgentMessage(
            message_id=f"msg-opt-{recommendation_data.get('id', 'new')}",
            process_id=recommendation_data.get("process_id", "proc-global"),
            sender="agent_2",
            receiver="agent_4",
            task_type="SUBMIT_OPTIMIZATION_RECOMMENDATION",
            payload=recommendation_data,
            confidence=float(recommendation_data.get("confidence", 0.90)),
            status="AUTHORIZED",
        )
        return await self.send_message(msg)

# Shared Pydantic schemas.
# Submodules are imported directly (e.g. app.schemas.auth, app.schemas.agent_message)
# to avoid circular imports with Agent 4 packages that also import schema types.
#
# Agent 1: from app.schemas.agent_message import DiscoveryAgentMessage, EvidenceReference

__all__: list[str] = []

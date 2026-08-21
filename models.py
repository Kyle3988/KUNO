from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LongTermMemory:
    content: str
    source_message_ids: list[int] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentModels:
    thinking: str
    speaking: str
    character_development: str
    memory: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ChatSession:
    title: str
    character_prompt: str
    messages: list[Message] = field(default_factory=list)
    memories: list[LongTermMemory] = field(default_factory=list)
    agent_models: AgentModels | None = None
    chat_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    starting_prompt_name: str = "Custom"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.agent_models is not None:
            data["agent_models"] = self.agent_models.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatSession:
        raw_models = data.get("agent_models")
        agent_models = AgentModels(**raw_models) if raw_models else None
        return cls(
            title=str(data.get("title", "Untitled chat")),
            character_prompt=str(data.get("character_prompt", "")),
            messages=[Message(**message) for message in data.get("messages", [])],
            memories=[LongTermMemory(**memory) for memory in data.get("memories", [])],
            agent_models=agent_models,
            chat_id=str(data.get("chat_id", uuid.uuid4().hex)),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            starting_prompt_name=str(data.get("starting_prompt_name", "Custom")),
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

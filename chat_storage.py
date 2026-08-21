from __future__ import annotations

import json
import os
from pathlib import Path
import re
import uuid

from models import ChatSession


class ChatStorage:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_chats(self) -> list[ChatSession]:
        chats: list[ChatSession] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                chats.append(self.load_path(path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(chats, key=lambda chat: chat.updated_at, reverse=True)

    def save(self, chat: ChatSession) -> Path:
        chat.chat_id = uuid.uuid4().hex
        chat.touch()
        path = self.directory / f"{self._filename_for_title(chat.title)}.json"
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(chat.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
        return path

    def load(self, chat_id: str) -> ChatSession:
        legacy_path = self.directory / f"{chat_id}.json"
        if legacy_path.exists():
            return self.load_path(legacy_path)

        for path in self.directory.glob("*.json"):
            try:
                chat = self.load_path(path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if chat.chat_id == chat_id:
                return chat
        raise FileNotFoundError(f"No saved chat found for id: {chat_id}")

    @staticmethod
    def _filename_for_title(title: str) -> str:
        filename = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "", title.strip())
        filename = re.sub(r"\s+", " ", filename).strip(" .")
        return filename or "Untitled chat"

    @staticmethod
    def load_path(path: Path) -> ChatSession:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Chat file must contain a JSON object")
        return ChatSession.from_dict(data)

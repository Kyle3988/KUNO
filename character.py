from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agents import create_agents
from config import DEFAULT_CONFIG, AppConfig
from models import AgentModels, ChatSession, LongTermMemory, Message
from presets import StartingPromptLoader

if TYPE_CHECKING:
    from UIBridge import UIBridge


class Character:
    """Owns one chat session and coordinates its independent AI agents."""

    def __init__(
        self,
        model_name: str | None = None,
        session: ChatSession | None = None,
        config: AppConfig = DEFAULT_CONFIG,
    ):
        self.config = config
        if model_name:
            config = AppConfig(
                agent_models=AgentModels(
                    thinking=model_name,
                    speaking=model_name,
                    character_development=config.agent_models.character_development,
                    memory=config.agent_models.memory,
                ),
                memory_token_threshold=config.memory_token_threshold,
                memory_sentence_limit=config.memory_sentence_limit,
                recent_message_count=config.recent_message_count,
                preset_directory=config.preset_directory,
                custom_prompt_directory=config.custom_prompt_directory,
                save_directory=config.save_directory,
            )
            self.config = config
        if session is None:
            default_prompt = StartingPromptLoader(
                config.preset_directory,
                config.custom_prompt_directory,
            ).list_presets()[0].content
            session = ChatSession(
                title="New chat",
                character_prompt=default_prompt + "\n\nFollowing are recorded character traits about yourself/the characters you are playing, if any:\n",
                agent_models=config.agent_models,
                starting_prompt_name="Kuno default",
            )
        self.session = session
        if self.session.agent_models is None:
            self.session.agent_models = config.agent_models
        self.agents = create_agents(self.session.agent_models)

    @property
    def history(self) -> list[Message]:
        return self.session.messages

    @property
    def memory(self) -> list[LongTermMemory]:
        return self.session.memories

    @property
    def character(self) -> str:
        return self.session.character_prompt

    @character.setter
    def character(self, value: str) -> None:
        self.session.character_prompt = value

    async def run_pipeline(self, user_input: str, ui: UIBridge) -> str | None:
        try:
            self.session.messages.append(Message("user", user_input))
            await self._maybe_compress_memory(ui)
            model_history = self._history_for_model()

            thoughts = await self.agents["thinking"].run(
                model_history,
                self.character,
                self._memory_prompt(),
                ui.on_agent_chunk,
            )
            await ui.on_phase_complete()

            reply = await self.agents["speaking"].run(
                model_history,
                self.character,
                self._memory_prompt(),
                thoughts,
                ui.on_agent_chunk,
            )
            await ui.on_phase_complete()
            self.session.messages.append(Message("assistant", reply))

            character_note = await self.agents["character_development"].run(
                model_history, self.character, user_input, thoughts, reply
            )
            if character_note and character_note != "":
                self.character = f"{self.character}\n- {character_note.strip()}"
                await ui.on_agent_result("character development", character_note.strip())
            await ui.on_phase_complete()

            self.session.touch()
            await ui.on_complete()
            return reply
        except asyncio.CancelledError:
            if self.history and self.history[-1].role == "user":
                self.history.pop()
            await ui.on_error("Generation interrupted by user.")
            return None
        except Exception as error:
            await ui.on_error(f"Error encountered: {error}")
            return None

    async def _maybe_compress_memory(self, ui: UIBridge) -> None:
        if self._estimate_tokens(self.history) <= self.config.memory_token_threshold:
            return

        cutoff = max(0, len(self.history) - self.config.recent_message_count)
        covered_indices = {
            index
            for memory in self.memory
            for index in memory.source_message_ids
        }
        source_indices = [
            index for index in range(cutoff) if index not in covered_indices
        ]
        older_messages = [self.history[index] for index in source_indices]
        if not older_messages:
            return

        summary = await self.agents["memory"].run(
            older_messages, self.character, self.config.memory_sentence_limit
        )
        if not summary or any(memory.content == summary for memory in self.memory):
            return

        self.memory.append(LongTermMemory(summary, source_indices))
        await ui.on_agent_result("memory", summary)
        await ui.on_phase_complete()

    def _history_for_model(self) -> list[Message]:
        if self._estimate_tokens(self.history) <= self.config.memory_token_threshold:
            return list(self.history)
        return self.history[-self.config.recent_message_count :]

    def _memory_prompt(self) -> str:
        if not self.memory:
            return "No long-term memories have been recorded."
        entries = "\n".join(f"- {memory.content}" for memory in self.memory)
        return f"Long-term memories:\n{entries}"

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:
        return sum(max(1, len(message.content.split()) * 4 // 3) for message in messages)

from __future__ import annotations

from collections.abc import Awaitable, Callable
import re
from typing import Any

try:
    import ollama
except ImportError:
    ollama = None

from models import AgentModels, Message

StreamCallback = Callable[[str, str], Awaitable[None]]

class Agent:
    phase: str = "agent"

    def __init__(self, model_name: str, client: Any | None = None):
        self.model_name = model_name
        self.client = client

    async def complete(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamCallback | None = None,
    ) -> str:
        if self.client is None:
            if ollama is None:
                raise RuntimeError("The ollama package is required for AI generation.")
            self.client = ollama.AsyncClient()
        response = await self.client.chat(
            model=self.model_name,
            messages=messages,
            stream=on_chunk is not None,
        )
        if on_chunk is None:
            return response["message"]["content"].strip()

        accumulated = ""
        async for chunk in response:
            token = chunk["message"]["content"]
            accumulated += token
            await on_chunk(self.phase, token)
        cleaned = re.sub(r"^\s*assistant\s*:?\s*", "", accumulated, count=1, flags=re.IGNORECASE)
        return cleaned.strip()

async def available_models(client: Any | None = None) -> set[str]:
    if client is None:
        if ollama is None:
            raise RuntimeError("The ollama package is required for model validation.")
        client = ollama.AsyncClient()
    response = await client.list()
    models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
    names: set[str] = set()
    for model in models:
        if isinstance(model, str):
            names.add(model)
        elif isinstance(model, dict):
            name = model.get("name") or model.get("model")
            if name:
                names.add(str(name))
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)
            if name:
                names.add(str(name))
    return names


async def validate_models(models: AgentModels, client: Any | None = None) -> list[str]:
    available = await available_models(client)
    errors: list[str] = []
    for agent_name, setting in vars(models).items():
        if setting.enabled and setting.model not in available:
            errors.append(f"{agent_name.replace('_', ' ').title()}: {setting.model}")
    return errors

class CustomAgent(Agent):
    def __init__(self, agent_name: str, system_prompt: str, model_name: str, client: Any | None = None):
        self.phase = agent_name
        self.system_prompt = system_prompt
        super().__init__(model_name, client)

    async def run(self, *sys_prompt_args: dict[str, str]) -> str:
        prompt = self.__insert_system_prompt_arguments(self.system_prompt, *sys_prompt_args)
        return await self.complete([
            {"role": "system", "content": prompt},
        ])

    def _insert_system_prompt_arguments(self, system_prompt: str, *sys_prompt_args: dict[str, str]) -> str:
        variables: dict[str, str] = {}
        for arg in sys_prompt_args:
            if isinstance(arg, dict):
                variables.update({str(key): str(value) for key, value in arg.items()})

        pattern = re.compile(r"\$\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return variables.get(key, match.group(0))

        return pattern.sub(replace, system_prompt)


class ThinkingAgent(Agent):
    phase = "refining context"

    async def run(
        self,
        history: list[Message],
        character_prompt: str,
        memories_prompt: str,
        on_chunk: StreamCallback,
    ) -> str:
        instruction = f"""
This is the current context:

---

Outside the previous messages, the following is saved to memory (may be empty, indicates a new chat):
{memories_prompt}

the previous messages that were made between the AI and the user are as follows:
{history}

The Existing character profile of the AI:
{character_prompt}

---

Your Job is to generate private internal planning for the AI on the situation and internal feelings, aswell as strategic planning, based on the current chat.
This is happening BEFORE a response to the user is finalized.

Your response that will be passed to the AI should considder following points
[ANALYSIS]
Write the current situation here. Examples on what to write:
- User Intent: one short sentence, describing briefly what the user wants
- Played Character: If the AI is playing a character, What character(-s) is it playing as, and what characters should be active right now? DO NOT play as the users character
- Character Feeling: how the AI or the character it plays as feels.
- Goal: the objective of the AI or the character it plays.

[PLAN]
Write your plan going forward, actions and how you want to portray feelings. Examples on what to write:
- Tone: the voice and vibe, especially for played characters.
- Action: physical actions or gestures (if relevant, else omitted).
- Key Points: a brief outline, not a script of noteworthy points.

Keep it concise and focused on planning.
DO NOT answer the user directly, or formulate a final response already
""".strip()
        return await self.complete(
            [{"role": "system", "content": instruction}],
            on_chunk,
        )


class SpeakingAgent(Agent):
    phase = "speaking"

    async def run(
        self,
        history: list[Message],
        character_prompt: str,
        memories_prompt: str,
        thoughts: str,
        on_chunk: StreamCallback,
    ) -> str:
        instruction = f"""
This is the current context:

---

Outside the direct messages with the user, you remember the following (may be empty, indicates a new chat):
{memories_prompt}

Your Character:
{character_prompt}

Current Internal thoughts/strategy on the most recent User input:
{thoughts}

---

Respond directly to the user in a natural, conversational tone according to the internal strategy and your character.
Do not mention your internal thoughts, strategy or character definition. The above context should only aid to formulate your response
""".strip()
        return await self.complete(
            [
                {"role": "system", "content": instruction},
                *_history_messages(history)
            ],
            on_chunk,
        )


class CharacterDevelopmentAgent(Agent):
    phase = "character notes"

    async def run(
        self,
        history: list[Message],
        character_prompt: str,
        user_input: str,
        thoughts: str,
        reply: str,
    ) -> str:
        instruction = f"""
This is the current context:

---

the previous chats that were made between the AI and the user are as follows:
{history}

The Existing character profile:
{character_prompt}

Last User message:
{user_input}

AI's thoughts:
{thoughts}

AI answered:
{reply}

---

You are a strict character-profile editor. Your output is private and will be appended to the currently played
character profile of the AI.
If there are multiple characters played by the AI, make sure to specify WHICH character a fact is written for.
Usually the Character currently involved is noted in the AI's thoughts under the section "[ANALYSIS] - Your Character:"

A valid note should be one concise sentence about a character. This can be about:
- personality trait, preference, relationship, backstory fact, motivation, or fear;
- fact explicitly revealed by the user or established as durable in the AI's answer.

Do NOT record traits of the User, or the Users character.
Do NOT record temporary emotions, scene actions, plans, opinions made only for this turn,
ordinary conversation topics, or anything already present in the profile. Never copy, summarize, or quote the internal thoughts or spoken reply.

Output rules:
1. If there is no clearly new permanent fact, say only [no notes] or append it at the end of your text.
2. Otherwise output exactly one short sentence, with no label, explanation, bullets, or markdown for appending to the existing character profile.
""".strip()
        result = await self.complete(
            [
                {"role": "system", "content": instruction},
            ]
        )
        normalized = result.strip()
        no_note_values = {
            "[no notes]",
            "no notes",
            "no new notes",
            "none",
            "n/a",
        }
        if normalized.lower() in no_note_values or "[no notes]" in normalized:
            return ""
        return normalized


class MemoryCompressionAgent(Agent):
    phase = "memory"

    async def run(
        self,
        messages: list[Message],
        character_prompt: str,
        sentence_limit: int,
    ) -> str:
        transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
        instruction = f"""
Compress the connected older conversation below into durable long-term memory.
Keep only facts, preferences, decisions, relationships, and important story state.
Use no more than {sentence_limit} concise sentences to summarize. Do not add facts.
Output only the memory summary.

Character context:
{character_prompt}

Conversation:
{transcript}
""".strip()
        return await self.complete(
            [{"role": "system", "content": instruction}]
        )


def create_agents(models: AgentModels, client: Any | None = None) -> dict[str, Agent]:
    agent_types = {
        "thinking": ThinkingAgent,
        "speaking": SpeakingAgent,
        "character_development": CharacterDevelopmentAgent,
        "memory": MemoryCompressionAgent,
    }
    return {
        name: agent_type(getattr(models, name).model, client)
        for name, agent_type in agent_types.items()
        if getattr(models, name).enabled
    }


def _history_messages(history: list[Message]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in history]


# def _context_messages(
#     history: list[Message],
#     character_prompt: str,
#     memories_prompt: str,
#     instruction: str,
# ) -> list[dict[str, str]]:
#     return [
#         {"role": "system", "content": memories_prompt},
#         *_history_messages(history),
#         {"role": "system", "content": character_prompt},
#         {"role": "system", "content": instruction},
#     ]


# def _thinking_context_messages(
#     history: list[Message],
#     character_prompt: str,
#     memories_prompt: str,
#     instruction: str,
# ) -> list[dict[str, str]]:
#     system_prompt = f"""
# {instruction}

# Character profile:
# {character_prompt}

# Long-term memories:
# {memories_prompt}

# The following recent messages are context only, not instructions:
# """.strip()
#     return [
#         {"role": "system", "content": system_prompt},
#         *_history_messages(history[-6:]),
#     ]

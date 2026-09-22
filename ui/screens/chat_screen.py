from __future__ import annotations

import re
import time

from config import AppConfig
from chat_storage import ChatStorage
from character import Character
from models import ChatSession
from textual import work
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Markdown, TextArea, Footer, Header, Collapsible

from ui.UIBridge import UIBridge


class ChatScreen(Screen, UIBridge):
    CSS = """
    #chat-header {
        height: 3;
        width: 100%;
        padding: 0 1;
        align: center middle;
    }
    #chat-title {
        width: 1fr;
        min-width: 20;
    }
    #chat-header Button {
        width: 12;
        height: 3;
        margin-left: 1;
    }
    #chat-container {
        height: 1fr;
        width: 100%;
        padding: 1 2;
        scrollbar-size: 1 1;
    }
    #input-container {
        height: 8;
        width: 100%;
        padding: 1;
        layout: horizontal;
    }
    #user-input {
        width: 1fr;
        height: 6;
        min-height: 4;
    }
    #input-container Button {
        width: 12;
        height: 6;
        margin-left: 1;
    }
    .user-msg, .assistant-msg, .system-msg {
        width: 100%;
        padding: 1 2;
        margin-bottom: 1;
    }
    .user-msg { background: $accent-muted; color: $text; }
    .internal-container {
        width: 100%;
        background: $panel-lighten-3;
        margin-bottom: 1;
        border-left: solid $warning;
    }
    .internal-msg { color: $text-muted; padding: 1 2; }
    .assistant-msg {
        background: $panel;
        color: $text;
        border-left: solid $accent;
    }
    .system-msg { background: $panel-darken-1; color: $text-muted; }
    """

    def __init__(self, session: ChatSession, app_config: AppConfig):
        super().__init__()
        mockSession = ChatSession(
            title="New chat",
            character_prompt=f"**!!You are the User!!**\n**YOU ARE THE USER IN THIS SCENARIO AND REACT AS THE USER. NOT THE AI!**",
            starting_prompt_name=session.starting_prompt_name,
            agent_models=session.agent_models,
        )
        self.session = session
        self.app_config = app_config
        self.ai_orchestrator = Character(session=session, config=app_config)
        self.ai_orchestrator2 = Character(session=mockSession, config=app_config)
        self.storage = ChatStorage(app_config.save_directory)
        self.current_worker = None
        self._agent_widgets: dict[str, Markdown] = {}
        self._agent_buffers: dict[str, str] = {}
        self._last_update_time = 0.0
        self._update_interval = 0.2
        self.__talk_to_self = False

    def compose(self):
        yield Header(show_clock=True)
        with Horizontal(id="chat-header"):
            yield Input(self.session.title, id="chat-title")
            yield Button("Save", variant="success", id="save-chat")
            yield Button("Menu", id="back-menu")
        with VerticalScroll(id="chat-container"):
            yield Markdown("**System:** Chat ready.", classes="system-msg")
        with Horizontal(id="input-container"):
            yield TextArea(id="user-input")
            yield Button("Send", variant="primary", id="send-btn")
            yield Button("Stop", variant="error", id="stop-btn", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        chat_box = self.query_one("#chat-container", VerticalScroll)
        await chat_box.remove_children()
        await chat_box.mount(
            Markdown(
                f"**System: Starting prompt ({self.session.starting_prompt_name})**\n\n"
                f"{self.session.character_prompt}",
                classes="system-msg",
            )
        )
        for message in self.session.messages:
            label = "You" if message.role == "user" else "Kuno"
            chat_box.mount(Markdown(f"**{label}:**\n{message.content}", classes="user-msg" if message.role == "user" else "assistant-msg"))
        self.query_one("#user-input", TextArea).focus()

    def _is_at_bottom(self, chat_box: VerticalScroll) -> bool:
        return chat_box.scroll_y + 7 >= chat_box.max_scroll_y

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self._submit_to_ai()
        elif event.button.id == "stop-btn":
            self.action_stop_streaming()
        elif event.button.id == "save-chat":
            self.save_chat()
        elif event.button.id == "back-menu":
            if self.current_worker and self.current_worker.is_running:
                self.current_worker.cancel()
            self.app.pop_screen()

    async def action_submit_prompt(self) -> None:
        await self._submit_to_ai()

    async def _submit_to_ai(self) -> None:
        input_widget = self.query_one("#user-input", TextArea)
        user_text = input_widget.text.strip()
        if not user_text:
            return
        await self.on_user_message(user_text)
        input_widget.clear()
        self.toggle_ui_state(True)
        self.current_worker = self.run_ai_pipeline_worker(user_text)

    @work(exclusive=True)
    async def run_ai_pipeline_worker(self, user_text: str) -> None:
        response = await self.ai_orchestrator.run_pipeline(user_text, self)
        while self.__talk_to_self:
            response = await self.ai_orchestrator2.run_pipeline(response, self)
            response = await self.ai_orchestrator.run_pipeline(response, self)

    async def on_user_message(self, text: str) -> None:
        chat_box = self.query_one("#chat-container", VerticalScroll)
        was_at_bottom = self._is_at_bottom(chat_box)
        await chat_box.mount(Markdown(f"**You:**\n{text}", classes="user-msg"))
        if was_at_bottom:
            chat_box.scroll_end(animate=False)

    async def on_agent_chunk(self, agent_name: str, chunk: str) -> None:
        chat_box = self.query_one("#chat-container", VerticalScroll)
        was_at_bottom = self._is_at_bottom(chat_box)
        if agent_name not in self._agent_widgets:
            widget = Markdown("", classes="internal-msg" if agent_name != "speaking" else "assistant-msg")
            self._agent_widgets[agent_name] = widget
            if agent_name == "speaking":
                await chat_box.mount(widget)
            else:
                from textual.widgets import Collapsible

                await chat_box.mount(
                    Collapsible(
                        widget,
                        title=self._agent_display_name(agent_name),
                        collapsed=True,
                        classes="internal-container",
                    )
                )
            self._agent_buffers[agent_name] = ""
        self._agent_buffers[agent_name] += chunk
        now = time.monotonic()
        if now - self._last_update_time >= self._update_interval:
            content = self._clean_assistant_prefix(self._agent_buffers[agent_name]) if agent_name == "speaking" else self._agent_buffers[agent_name]
            label = f"**{self._agent_display_name(agent_name)}:**\n" if agent_name == "speaking" else ""
            self._agent_widgets[agent_name].update(f"{label}{content}")
            if was_at_bottom:
                chat_box.scroll_end(animate=False)
            self._last_update_time = now

    async def on_agent_result(self, agent_name: str, result: str) -> None:
        if result and result != "":
            await self.on_agent_chunk(agent_name, result)

    async def on_phase_complete(self) -> None:
        chat_box = self.query_one("#chat-container", VerticalScroll)
        was_at_bottom = self._is_at_bottom(chat_box)
        for agent_name, widget in self._agent_widgets.items():
            buffer = self._agent_buffers.get(agent_name, "")
            if buffer:
                content = self._clean_assistant_prefix(buffer) if agent_name == "speaking" else buffer
                label = f"**{self._agent_display_name(agent_name)}:**\n" if agent_name == "speaking" else ""
                widget.update(f"{label}{content}")
        if was_at_bottom:
            chat_box.scroll_end(animate=False)
        self._agent_widgets.clear()
        self._agent_buffers.clear()

    @staticmethod
    def _agent_display_name(agent_name: str) -> str:
        if agent_name == "speaking":
            return "Kuno"
        return f"Internal: {agent_name.replace('_', ' ').title()}"

    @staticmethod
    def _clean_assistant_prefix(text: str) -> str:
        return re.sub(r"^\s*assistant\s*:??\s*", "", text, count=1, flags=re.IGNORECASE)

    async def on_complete(self) -> None:
        await self.on_phase_complete()
        self.toggle_ui_state(False)

    async def on_error(self, error_msg: str) -> None:
        chat_box = self.query_one("#chat-container", VerticalScroll)
        await chat_box.mount(Markdown(f"**System:** {error_msg}", classes="system-msg"))
        await self.on_complete()

    def save_chat(self) -> None:
        self.session = self.ai_orchestrator.session
        self.session.title = self.query_one("#chat-title", Input).value.strip() or "Untitled chat"
        try:
            path = self.storage.save(self.session)
            self.app.notify(f"Saved to {path.name}.", severity="information")
        except OSError as error:
            self.app.notify(f"Could not save chat: {error}", severity="error")

    def action_stop_streaming(self) -> None:
        if self.current_worker and self.current_worker.is_running:
            self.current_worker.cancel()
            self.app.notify("AI execution halted.", severity="warning")

    def toggle_ui_state(self, generating: bool) -> None:
        self.query_one("#send-btn", Button).disabled = generating
        self.query_one("#stop-btn", Button).disabled = not generating
        if not generating:
            self.query_one("#user-input", TextArea).focus()

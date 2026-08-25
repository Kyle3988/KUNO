from __future__ import annotations

import json
import re
import time
from pathlib import Path

from character import Character
from chat_storage import ChatStorage
from config import DEFAULT_CONFIG, AppConfig
from models import AgentModels, ChatSession
from presets import StartingPrompt, StartingPromptLoader
from UIBridge import UIBridge

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    TextArea,
)


THEME_SETTINGS_FILENAME = ".kuno-settings.json"


def _load_saved_theme(path: Path) -> str | None:
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    theme = settings.get("theme") if isinstance(settings, dict) else None
    return theme if isinstance(theme, str) and theme else None


def _save_theme(path: Path, theme: str) -> None:
    try:
        path.write_text(
            json.dumps({"theme": theme}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


class MenuScreen(Screen):
    def __init__(self, app_config: AppConfig):
        super().__init__()
        self.app_config = app_config
        self.storage = ChatStorage(app_config.save_directory)
        self.saved_chats: list[ChatSession] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("KUNO", id="menu-title")
        yield Button("New Chat", variant="primary", id="new-chat")
        yield Label("Saved chats", id="saved-label")
        yield ListView(id="saved-chats")
        with Horizontal(id="menu-actions"):
            yield Button("Load Selected", variant="success", id="load-chat")
            yield Button("Quit", variant="error", id="quit")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_saved_chats()

    async def on_screen_resume(self) -> None:
        """Refresh saved chats whenever this screen becomes visible again."""
        await self.refresh_saved_chats()

    async def refresh_saved_chats(self) -> None:
        self.saved_chats = self.storage.list_chats()
        chat_list = self.query_one("#saved-chats", ListView)
        await chat_list.clear()
        if not self.saved_chats:
            await chat_list.append(ListItem(Label("No saved chats yet."), id="empty-saved"))
            return
        for chat in self.saved_chats:
            await chat_list.append(ListItem(Label(chat.title), id=f"chat-{chat.chat_id}"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-chat":
            self.app.push_screen(PromptSetupScreen(self.app_config))
        elif event.button.id == "load-chat":
            selected = self.query_one("#saved-chats", ListView).highlighted_child
            if selected is None or selected.id is None or not selected.id.startswith("chat-"):
                self.app.notify("Select a saved chat first.", severity="warning")
                return
            chat_id = selected.id.removeprefix("chat-")
            try:
                self.app.push_screen(ChatScreen(self.storage.load(chat_id), self.app_config))
            except (OSError, ValueError, TypeError):
                self.app.notify("That saved chat could not be loaded.", severity="error")
        elif event.button.id == "quit":
            self.app.exit()


class PromptSetupScreen(Screen):
    def __init__(self, app_config: AppConfig):
        super().__init__()
        self.app_config = app_config
        self.loader = StartingPromptLoader(
            app_config.preset_directory,
            app_config.custom_prompt_directory,
        )
        self.prompt_by_key: dict[str, StartingPrompt] = {}
        self.prompt_options: list[tuple[str, str]] = []
        self._refresh_prompts()

    def _refresh_prompts(self) -> None:
        starting_prompts = self.loader.list_presets()
        custom_prompts = self.loader.list_custom_prompts()
        starting_names = {prompt.name for prompt in starting_prompts}
        custom_names = {prompt.name for prompt in custom_prompts}
        self.prompt_by_key = {"custom": self.loader.custom("")}
        self.prompt_options = [("Custom", "custom")]
        # list custom prompts first
        for prompt in custom_prompts:
            key = f"custom:{prompt.name}"
            label = f"Custom: {prompt.name}" if prompt.name in starting_names else prompt.name
            self.prompt_by_key[key] = prompt
            self.prompt_options.append((label, key))
        for prompt in starting_prompts:
            key = f"starting:{prompt.name}"
            label = f"Starting: {prompt.name}" if prompt.name in custom_names else prompt.name
            self.prompt_by_key[key] = prompt
            self.prompt_options.append((label, key))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Start a new chat", id="prompt-title")
        yield Label("Choose or search for a starting prompt.")
        yield Select(self.prompt_options, value="starting:Kuno default", id="prompt-select")
        yield TextArea(id="starting-prompt")
        with Horizontal(id="prompt-actions"):
            yield Button("Save Prompt", variant="success", id="save-prompt", disabled=True)
            yield Button("Start Chat", variant="primary", id="start-chat")
            yield Button("Back", id="back-menu")
        yield Footer()

    def on_mount(self) -> None:
        selected = self.prompt_by_key["starting:Kuno default"]
        self.query_one("#starting-prompt", TextArea).text = selected.content
        self._set_clean_state(selected.name, selected.content)
        self.query_one("#starting-prompt", TextArea).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "prompt-select":
            return
        selected_key = str(event.value)
        selected = self.prompt_by_key.get(selected_key)
        if selected is None:
            return
        self.query_one("#starting-prompt", TextArea).text = selected.content
        name = "" if selected_key == "custom" else selected.name
        self._set_clean_state(selected.name, selected.content)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "starting-prompt":
            self._update_save_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-menu":
            self.app.pop_screen()
            return
        if event.button.id == "save-prompt":
            self.open_save_prompt()
            return
        if event.button.id != "start-chat":
            return
        prompt = self.query_one("#starting-prompt", TextArea).text.strip()
        if not prompt:
            self.app.notify("Enter a starting prompt or choose a preset.", severity="warning")
            return
        selected_key = str(self.query_one("#prompt-select", Select).value)
        if selected_key == "custom":
            prompt_name = "Custom"
        elif selected_key in self.prompt_by_key:
            prompt_name = self.prompt_by_key[selected_key].name
        else:
            prompt_name = "Custom"
        session = ChatSession(
            title="New chat",
            character_prompt=prompt,
            starting_prompt_name=prompt_name,
            agent_models=self.app_config.agent_models,
        )
        self.app.push_screen(ChatScreen(session, self.app_config))

    def open_save_prompt(self) -> None:
        selected_key = str(self.query_one("#prompt-select", Select).value)
        selected = self.prompt_by_key.get(selected_key)
        initial_name = "" if selected_key == "custom" or selected is None else selected.name
        self.app.push_screen(PromptNameModal(initial_name), self._save_prompt_from_modal)

    def _save_prompt_from_modal(self, name: str | None) -> None:
        if name is not None:
            self.save_prompt(name)

    def save_prompt(self, name: str) -> None:
        content = self.query_one("#starting-prompt", TextArea).text
        try:
            path = self.loader.save_custom_prompt(name, content)
        except (OSError, ValueError) as error:
            self.app.notify(f"Could not save prompt: {error}", severity="error")
            return
        selected_key = f"custom:{path.stem}"
        self._refresh_prompts()
        prompt_select = self.query_one("#prompt-select", Select)
        prompt_select.set_options(self.prompt_options)
        prompt_select.value = selected_key
        self._set_clean_state(path.stem, content)
        self.app.notify(f"Saved prompt to {path.name}.", severity="information")

    def _set_clean_state(self, name: str, content: str) -> None:
        self._clean_prompt_name = name.strip()
        self._clean_prompt_content = content.strip()
        self._update_save_state()

    def _update_save_state(self) -> None:
        if not self.is_attached:
            return
        content = self.query_one("#starting-prompt", TextArea).text.strip()
        changed = content != getattr(self, "_clean_prompt_content", "")
        self.query_one("#save-prompt", Button).disabled = not changed


class PromptNameModal(ModalScreen[str | None]):
    CSS = """
    PromptNameModal {
        align: center middle;
    }
    #prompt-name-dialog {
        width: 60;
        height: auto;
        max-width: 90%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #prompt-name-dialog Input {
        width: 100%;
        margin: 1 0;
    }
    #prompt-name-actions {
        width: 100%;
        height: 3;
        align: right middle;
    }
    #prompt-name-actions Button {
        margin-left: 1;
    }
    """

    def __init__(self, initial_name: str):
        super().__init__()
        self.initial_name = initial_name

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-name-dialog"):
            yield Label("Save prompt")
            yield Input(value=self.initial_name, placeholder="Prompt name", id="prompt-name-input")
            with Horizontal(id="prompt-name-actions"):
                yield Button("Save", variant="success", id="confirm-save-prompt")
                yield Button("Cancel", id="cancel-save-prompt")

    def on_mount(self) -> None:
        prompt_input = self.query_one("#prompt-name-input", Input)
        prompt_input.focus()
        prompt_input.cursor_position = len(prompt_input.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt-name-input":
            self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-save-prompt":
            self.dismiss(self.query_one("#prompt-name-input", Input).value)
        elif event.button.id == "cancel-save-prompt":
            self.dismiss(None)


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
        self.session = session
        self.app_config = app_config
        self.ai_orchestrator = Character(session=session, config=app_config)
        self.storage = ChatStorage(app_config.save_directory)
        self.current_worker = None
        self._agent_widgets: dict[str, Markdown] = {}
        self._agent_buffers: dict[str, str] = {}
        self._last_update_time = 0.0
        self._update_interval = 0.2

    def compose(self) -> ComposeResult:
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
        await self.ai_orchestrator.run_pipeline(user_text, self)

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
        return re.sub(r"^\s*assistant\s*:?\s*", "", text, count=1, flags=re.IGNORECASE)

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


class UserInterface(App):
    CSS = """
    Screen {
        layout: vertical;
        width: 100%;
        height: 100%;
    }
    Header { height: 3; }
    Footer { height: 1; }

    #menu-title, #prompt-title {
        width: 100%;
        height: 3;
        padding: 1 2;
        text-style: bold;
        color: $accent;
    }
    #saved-label {
        width: 100%;
        height: 3;
        padding: 1 2;
        text-style: bold;
    }
    #saved-chats {
        height: 1fr;
        width: 100%;
        margin: 0 2;
        border: round $panel;
    }
    #menu-actions, #prompt-actions {
        width: 100%;
        height: 4;
        padding: 0 2 1 2;
        align: right middle;
    }
    #menu-actions Button, #prompt-actions Button {
        width: 18;
        height: 3;
        margin-left: 1;
    }
    #new-chat {
        width: 24;
        height: 3;
        margin: 0 2 1 2;
    }
    #prompt-select {
        width: 1fr;
        height: 3;
        margin: 0 2 1 2;
    }
    #starting-prompt {
        height: 1fr;
        width: 1fr;
        margin: 0 2 1 2;
        border: round $panel;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "stop_streaming", "Stop Generation"),
        ("ctrl+enter", "submit_prompt", "Send Message"),
    ]

    def __init__(self, model_name: str | None = None, app_config: AppConfig = DEFAULT_CONFIG):
        super().__init__()
        if model_name:
            app_config = AppConfig(
                agent_models=AgentModels(
                    thinking=model_name,
                    speaking=model_name,
                    character_development=app_config.agent_models.character_development,
                    memory=app_config.agent_models.memory,
                ),
                memory_token_threshold=app_config.memory_token_threshold,
                memory_sentence_limit=app_config.memory_sentence_limit,
                recent_message_count=app_config.recent_message_count,
                preset_directory=app_config.preset_directory,
                custom_prompt_directory=app_config.custom_prompt_directory,
                save_directory=app_config.save_directory,
            )
        self.app_config = app_config
        self._theme_settings_path = app_config.save_directory.parent / THEME_SETTINGS_FILENAME
        self._theme_persistence_enabled = False
        saved_theme = _load_saved_theme(self._theme_settings_path)
        if saved_theme:
            try:
                self.theme = saved_theme
            except (KeyError, ValueError):
                pass
        self._theme_persistence_enabled = True

    def watch_theme(self, theme: str) -> None:
        if self._theme_persistence_enabled:
            _save_theme(self._theme_settings_path, theme)

    def on_unmount(self) -> None:
        _save_theme(self._theme_settings_path, self.theme)

    def on_mount(self) -> None:
        self.push_screen(MenuScreen(self.app_config))

    def action_stop_streaming(self) -> None:
        screen = self.screen
        if isinstance(screen, ChatScreen):
            screen.action_stop_streaming()

    async def action_submit_prompt(self) -> None:
        screen = self.screen
        if isinstance(screen, ChatScreen):
            await screen.action_submit_prompt()


if __name__ == "__main__":
    UserInterface().run()

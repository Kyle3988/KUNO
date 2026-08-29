from __future__ import annotations

from chat_storage import ChatStorage
from config import AppConfig
from models import ChatSession
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView, Header, Footer
from textual.containers import Horizontal


class MenuScreen(Screen):
    def __init__(self, app_config: AppConfig):
        super().__init__()
        self.app_config = app_config
        self.storage = ChatStorage(app_config.save_directory)
        self.saved_chats: list[ChatSession] = []

    def compose(self):
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
            from .prompt_setup_screen import PromptSetupScreen

            self.app.push_screen(PromptSetupScreen(self.app_config))
        elif event.button.id == "load-chat":
            selected = self.query_one("#saved-chats", ListView).highlighted_child
            if selected is None or selected.id is None or not selected.id.startswith("chat-"):
                self.app.notify("Select a saved chat first.", severity="warning")
                return
            chat_id = selected.id.removeprefix("chat-")
            try:
                from .chat_screen import ChatScreen

                self.app.push_screen(ChatScreen(self.storage.load(chat_id), self.app_config))
            except (OSError, ValueError, TypeError):
                self.app.notify("That saved chat could not be loaded.", severity="error")
        elif event.button.id == "quit":
            self.app.exit()

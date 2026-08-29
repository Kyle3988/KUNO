from __future__ import annotations

from config import DEFAULT_CONFIG, AppConfig
from models import AgentModels
from textual.app import App

from ui.theme import load_saved_theme, save_theme, THEME_SETTINGS_FILENAME
from ui.screens import ChatScreen, MenuScreen


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
        height: 18;
        width: 1fr;
        margin: 0 2 1 2;
        border: round $panel;
    }
    #prompt-content {
        height: 1fr;
        width: 100%;
        padding: 0 2;
    }
    #prompt-content > Select {
        width: 100%;
        margin: 0 0 1 0;
    }
    #prompt-content > TextArea {
        width: 100%;
        margin: 0 0 1 0;
    }
    #advanced-settings {
        width: 100%;
        margin: 1 0;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }
    #advanced-settings > Label {
        color: $text-muted;
        margin-bottom: 1;
    }
    .agent-setting-label {
        margin-top: 1;
        color: $accent;
        text-style: bold;
    }
    .agent-setting-row {
        width: 100%;
        height: 3;
        align: left middle;
    }
    .agent-setting-row Input {
        width: 1fr;
        height: 3;
        border: round $panel;
        background: $panel-darken-1;
    }
    .agent-enabled-toggle {
        width: 12;
        min-width: 12;
        height: 3;
        margin-right: 1;
        text-style: bold;
        border: round $panel;
        background: $panel-darken-1;
        color: $text-muted;
    }
    .agent-enabled-toggle.is-enabled {
        border: round $success;
        background: $success;
        color: $text;
    }
    .agent-enabled-toggle.is-disabled {
        border: round $warning;
        color: $warning;
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
        saved_theme = load_saved_theme(self._theme_settings_path)
        if saved_theme:
            try:
                self.theme = saved_theme
            except (KeyError, ValueError):
                pass
        self._theme_persistence_enabled = True

    def watch_theme(self, theme: str) -> None:
        if self._theme_persistence_enabled:
            save_theme(self._theme_settings_path, theme)

    def on_unmount(self) -> None:
        save_theme(self._theme_settings_path, self.theme)

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

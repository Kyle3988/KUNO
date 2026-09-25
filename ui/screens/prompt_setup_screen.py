from __future__ import annotations

from agents import validate_models
from config import AppConfig
from models import AgentModels, AgentSetting, ChatSession
from presets import StartingPrompt, StartingPromptLoader
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    Label,
    Select,
    TextArea,
    Header,
    Footer
)


class PromptSetupScreen(Screen):
    AGENT_FIELDS = (
        ("thinking", "Context model", False),
        ("speaking", "Speaking model", True),
        ("character_development", "Character notes model", False),
        ("memory", "Memory compression model (WIP)", False),
    )
    talksToSelf = False

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

    def compose(self):
        yield Header(show_clock=True)
        yield Label("Start a new chat", id="prompt-title")
        with VerticalScroll(id="prompt-content"):
            yield Label("Choose or search for a starting prompt.")
            yield Select(self.prompt_options, value="starting:Kuno default", id="prompt-select")
            yield TextArea(id="starting-prompt")
            with Collapsible(title="Advanced settings", collapsed=True, id="advanced-settings"):
                yield Label("Configure the models used by this chat.")
                for field_name, label, required in self.AGENT_FIELDS:
                    setting = getattr(self.app_config.agent_models, field_name)
                    yield Label(
                        f"{label} (required)" if required else label,
                        classes="agent-setting-label",
                    )
                    with Horizontal(classes="agent-setting-row"):
                        if not required:
                            yield Button(
                                "Enabled" if setting.enabled else "Disabled",
                                id=f"{field_name}-enabled",
                                classes=(
                                    "agent-enabled-toggle is-enabled"
                                    if setting.enabled
                                    else "agent-enabled-toggle is-disabled"
                                ),
                            )
                        yield Input(
                            setting.model,
                            placeholder="Ollama model name",
                            id=f"{field_name}-model",
                        )
                # with Horizontal(id="talk-to-self"):
                #     yield Button(
                #         "Enabled" if self.talksToSelf else "Disabled",
                #         id=f"talksToSelf-enabled",
                #         classes=(
                #             "agent-enabled-toggle is-enabled"
                #             if self.talksToSelf
                #             else "agent-enabled-toggle is-disabled"
                #         ),),
                #     yield Label(
                #         f"Let AI respond to Character (first message required)"
                #     )
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
        self._set_clean_state(selected.name, selected.content)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "starting-prompt":
            self._update_save_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.endswith("-enabled"):
            enabled = not event.button.has_class("is-enabled")
            event.button.label = "Enabled" if enabled else "Disabled"
            event.button.set_class(enabled, "is-enabled")
            event.button.set_class(not enabled, "is-disabled")
            return
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
        agent_models = self._get_agent_models()
        if not agent_models.speaking.enabled:
            self.app.notify("The speaking agent must be enabled.", severity="warning")
            return
        try:
            unavailable = await validate_models(agent_models)
        except Exception as error:
            self.app.notify(f"Could not validate Ollama models: {error}", severity="error")
            return
        if unavailable:
            self.app.notify("Unavailable models: " + "; ".join(unavailable), severity="error")
            return
        session = ChatSession(
            title="New chat",
            character_prompt=prompt,
            starting_prompt_name=prompt_name,
            agent_models=agent_models,
        )
        from .chat_screen import ChatScreen

        self.app.push_screen(ChatScreen(session, self.app_config))

    def _get_agent_models(self) -> AgentModels:
        settings = {}
        for field_name, _, required in self.AGENT_FIELDS:
            settings[field_name] = AgentSetting(
                model=self.query_one(f"#{field_name}-model", Input).value.strip(),
                enabled=(
                    True
                    if required
                    else self.query_one(f"#{field_name}-enabled", Button).has_class("is-enabled")
                ),
            )
        return AgentModels(**settings)

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

    def compose(self):
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

from dataclasses import dataclass
from pathlib import Path
import os
import re

from config import DEFAULT_CHARACTER_PROMPT


@dataclass(frozen=True)
class StartingPrompt:
    name: str
    content: str
    is_custom: bool = False


class StartingPromptLoader:
    def __init__(self, directory: Path, custom_directory: Path | None = None):
        self.directory = directory
        self.custom_directory = custom_directory or directory.parent / "custom prompts"

    def list_presets(self) -> list[StartingPrompt]:
        presets: list[StartingPrompt] = []
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.md")):
                if path.stem == "Kuno default":
                    continue
                try:
                    content = path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if content:
                    presets.append(StartingPrompt(path.stem, content))
        default_path = self.directory / "Kuno default.md"
        try:
            default_content = default_path.read_text(encoding="utf-8").strip()
        except OSError:
            default_content = DEFAULT_CHARACTER_PROMPT
        if default_content:
            presets.insert(0, StartingPrompt("Kuno default", default_content))
        return presets

    def list_custom_prompts(self) -> list[StartingPrompt]:
        prompts: list[StartingPrompt] = []
        if self.custom_directory.exists():
            for path in sorted(self.custom_directory.glob("*.md")):
                try:
                    content = path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if content:
                    prompts.append(StartingPrompt(path.stem, content, is_custom=True))
        return prompts

    def save_custom_prompt(self, name: str, content: str) -> Path:
        filename = self._filename_for_name(name)
        cleaned_content = content.strip()
        if not cleaned_content:
            raise ValueError("Prompt content cannot be empty")
        self.custom_directory.mkdir(parents=True, exist_ok=True)
        path = self.custom_directory / f"{filename}.md"
        temporary_path = path.with_suffix(".md.tmp")
        temporary_path.write_text(cleaned_content + "\n", encoding="utf-8")
        os.replace(temporary_path, path)
        return path

    def custom(self, content: str) -> StartingPrompt:
        return StartingPrompt("Custom", content.strip(), is_custom=True)

    @staticmethod
    def _filename_for_name(name: str) -> str:
        cleaned_name = name.strip()
        if not cleaned_name or cleaned_name in {".", ".."}:
            raise ValueError("Prompt name cannot be empty or a path name")
        if any(char in cleaned_name for char in "\\/:*?\"<>|") or any(
            ord(char) < 32 for char in cleaned_name
        ):
            raise ValueError("Prompt name contains invalid filename characters")
        cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip(" .")
        if not cleaned_name:
            raise ValueError("Prompt name cannot be empty")
        return cleaned_name

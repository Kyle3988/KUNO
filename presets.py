from dataclasses import dataclass
from pathlib import Path

from config import DEFAULT_CHARACTER_PROMPT


@dataclass(frozen=True)
class StartingPrompt:
    name: str
    content: str
    is_custom: bool = False


class StartingPromptLoader:
    def __init__(self, directory: Path):
        self.directory = directory

    def list_presets(self) -> list[StartingPrompt]:
        presets = [StartingPrompt("Kuno default", DEFAULT_CHARACTER_PROMPT)]
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.md")):
                try:
                    content = path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if content:
                    presets.append(StartingPrompt(path.stem, content))
        return presets

    def custom(self, content: str) -> StartingPrompt:
        return StartingPrompt("Custom", content.strip(), is_custom=True)

import json
from pathlib import Path

THEME_SETTINGS_FILENAME = ".kuno-settings.json"


def load_saved_theme(path: Path) -> str | None:
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    theme = settings.get("theme") if isinstance(settings, dict) else None
    return theme if isinstance(theme, str) and theme else None


def save_theme(path: Path, theme: str) -> None:
    try:
        path.write_text(
            json.dumps({"theme": theme}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

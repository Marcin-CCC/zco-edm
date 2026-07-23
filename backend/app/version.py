"""Version management module. Reads version from Docker container file."""
import json
from pathlib import Path

_VERSION_FILE = Path("/app/VERSION")
# Changelog leży w pakiecie aplikacji (kopiowany przez `COPY ./app`)
_CHANGELOG_FILE = Path(__file__).parent / "changelog.json"


def get_version() -> str:
    """Zwróć bieżącą wersję.

    Źródło prawdy: górny wpis `changelog.json` (spójne lokalnie i na Sparku,
    niezależne od build-arga). Fallback: plik `/app/VERSION` wpieczony przy
    budowie obrazu, a na końcu "0.0.0".
    """
    entries = get_changelog()
    if entries and entries[0].get("version"):
        return entries[0]["version"]
    try:
        return _VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return "0.0.0"


def get_version_info() -> dict:
    """Return version info as dict for API."""
    result: dict = {"version": get_version()}

    _build_date = Path("/app/BUILD_DATE")
    result["build_date"] = (
        _build_date.read_text().strip() if _build_date.exists() else "unknown"
    )

    _git_commit = Path("/app/GIT_COMMIT")
    result["git_commit"] = (
        _git_commit.read_text().strip() if _git_commit.exists() else "unknown"
    )

    return result


def get_changelog() -> list:
    """Zwróć listę wpisów historii zmian (najnowsze pierwsze)."""
    try:
        data = json.loads(_CHANGELOG_FILE.read_text(encoding="utf-8"))
        return data.get("entries", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []
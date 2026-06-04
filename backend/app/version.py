"""Version management module. Reads version from Docker container file."""
from pathlib import Path

_VERSION_FILE = Path("/app/VERSION")


def get_version() -> str:
    """Read and return the current version string."""
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
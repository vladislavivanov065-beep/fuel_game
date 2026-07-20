"""Save/load named projects as JSON files under projects/."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Project

PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class InvalidProjectNameError(ValueError):
    pass


def _project_path(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise InvalidProjectNameError(f"Invalid project name: {name!r}")
    return PROJECTS_DIR / f"{name}.json"


def list_projects() -> list[str]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in PROJECTS_DIR.glob("*.json"))


def load_project(name: str) -> Project:
    path = _project_path(name)
    if not path.exists():
        return Project()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Project.from_dict(raw)


def save_project(name: str, project: Project) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _project_path(name)
    path.write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

"""Unified directory layout for all PilotCode files.

All user-level (global) data lives under ``~/.pilotcode/`` with three
sub-directories:

  ~/.pilotcode/
  ├── config/          # User-editable configuration
  │   ├── settings.json
  │   └── model_capability.json
  ├── data/            # Persistent application data
  │   ├── sessions/
  │   ├── agents/
  │   ├── knowhow/
  │   ├── forks.json
  │   └── input_history.json
  ├── cache/           # Safe-to-delete cached data
  │   ├── prompt_cache/
  │   ├── embeddings/
  │   ├── index/
  │   ├── plans/
  │   └── update_check.json
  └── themes/          # TUI theme files

Project-level data stays in ``{project}/.pilotcode/``:

  {project}/.pilotcode/
  ├── memory/          # facts.jsonl, bugs.jsonl, ...
  ├── snapshots/
  ├── project_memory.json
  └── backups/         # FileEdit backups (previously {file}.pilotcode.bak)
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------
def get_pilotcode_dir() -> Path:
    """Return the PilotCode root directory (``~/.pilotcode``)."""
    return Path.home() / ".pilotcode"


# ---------------------------------------------------------------------------
# Config (user-editable, should be backed up / version-controlled)
# ---------------------------------------------------------------------------
def get_config_dir() -> Path:
    d = get_pilotcode_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_path() -> Path:
    return get_config_dir() / "settings.json"


def get_model_capability_path() -> Path:
    return get_config_dir() / "model_capability.json"


# ---------------------------------------------------------------------------
# Data (persistent application state, should be backed up)
# ---------------------------------------------------------------------------
def get_data_dir() -> Path:
    d = get_pilotcode_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_sessions_dir() -> Path:
    d = get_data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_agents_dir() -> Path:
    d = get_data_dir() / "agents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_knowhow_dir() -> Path:
    d = get_data_dir() / "knowhow"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_forks_path() -> Path:
    return get_data_dir() / "forks.json"


def get_input_history_path() -> Path:
    return get_data_dir() / "input_history.json"


# ---------------------------------------------------------------------------
# Cache (safe to delete, will be rebuilt)
# ---------------------------------------------------------------------------
def get_cache_dir() -> Path:
    d = get_pilotcode_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_prompt_cache_dir() -> Path:
    d = get_cache_dir() / "prompt_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_embeddings_dir() -> Path:
    d = get_cache_dir() / "embeddings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_index_cache_dir() -> Path:
    d = get_cache_dir() / "index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_plans_cache_dir() -> Path:
    d = get_cache_dir() / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_update_check_path() -> Path:
    return get_cache_dir() / "update_check.json"


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
def get_themes_dir() -> Path:
    d = get_pilotcode_dir() / "themes"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Project-level helpers
# ---------------------------------------------------------------------------
def get_project_pilotcode_dir(project_path: str | Path) -> Path:
    """Return ``{project}/.pilotcode`` directory."""
    d = Path(project_path).resolve() / ".pilotcode"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_memory_dir(project_path: str | Path) -> Path:
    d = get_project_pilotcode_dir(project_path) / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_snapshots_dir(project_path: str | Path) -> Path:
    d = get_project_pilotcode_dir(project_path) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_backups_dir(project_path: str | Path) -> Path:
    d = get_project_pilotcode_dir(project_path) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_memory_path(project_path: str | Path) -> Path:
    return get_project_pilotcode_dir(project_path) / "project_memory.json"


def get_project_config_path(project_path: str | Path) -> Path:
    return Path(project_path).resolve() / ".pilotcode.json"

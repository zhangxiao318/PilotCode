"""Prompt building for QueryEngine.

Encapsulates system prompt construction, runtime context injection,
and persistent hint management.
"""

from __future__ import annotations

from typing import Any, Callable

from ..types.message import SystemMessage
from ..services import prompts as prompt_service
from ..services.knowhow_loader import KnowHowLoader


class PromptBuilder:
    """Builds the system message for LLM conversations."""

    def __init__(
        self,
        cwd: str,
        custom_system_prompt: str | None = None,
        get_app_state: Callable[[], Any] | None = None,
    ):
        self.cwd = cwd
        self.custom_system_prompt = custom_system_prompt
        self._get_app_state = get_app_state
        self._knowhow = KnowHowLoader(cwd)

    def build(self) -> SystemMessage:
        """Build system message with runtime context."""
        if self.custom_system_prompt:
            content = self.custom_system_prompt
        else:
            content = self._get_default_system_prompt()

        # Add runtime context (OS, cwd, etc.) AFTER static prompt
        # so prompt caching (e.g. Anthropic) can efficiently cache the static part.
        context = self._get_runtime_context()
        if context:
            content = content + "\n\n" + context

        # Inject archived session memory for continuity across compactions
        try:
            from ..services.context_archive import ContextArchive

            archive = ContextArchive()
            session_mem = archive.get_session_memory_prompt()
            if session_mem:
                content = session_mem + "\n\n" + content
        except Exception:
            pass

        # Load project-specific KnowHow instructions
        knowhow = self._knowhow.load(self.cwd)
        if knowhow:
            content = content + "\n\n## 项目规范（KnowHow）\n\n" + knowhow

        # Inject persistent memory directory index (MEMORY.md + behavioral instructions)
        try:
            from ..services.memory_dir import build_memory_prompt

            mem_prompt = build_memory_prompt(self.cwd)
            if mem_prompt:
                content = mem_prompt + "\n\n" + content
        except Exception:
            pass

        # Lightweight persistence: if this session has observed persistent
        # FileEdit weakness, inject a常驻 reminder into the system prompt.
        persistent_hint = self._get_persistent_fileedit_hint()
        if persistent_hint:
            content = content + "\n\n" + persistent_hint

        return SystemMessage(content=content)

    def _get_persistent_fileedit_hint(self) -> str | None:
        """Return a常驻 FileEdit hint if the model is known to be weak."""
        if self._get_app_state is None:
            return None
        try:
            app_state = self._get_app_state()
            stats = getattr(app_state, "fileedit_stats", None)
            if stats and stats.get("persistent_weak"):
                return (
                    "[PERSISTENT FRAMEWORK REMINDER] This session has observed repeated "
                    "FileEdit difficulties. For EVERY edit you make:\n"
                    "1. Re-read the file with FileRead BEFORE editing to get the EXACT text.\n"
                    "2. Copy the old_string EXACTLY — every space, tab, and newline matters.\n"
                    "3. Make exactly ONE atomic change per FileEdit call.\n"
                    "4. If FileEdit fails once, switch to SmartEditPlanner or use FileWrite for small files.\n"
                    "5. After any .py edit, run `python -m py_compile <filepath>` to check syntax."
                )
        except Exception:
            pass
        return None

    def _get_runtime_context(self) -> str:
        """Get runtime context (OS, cwd, etc.) for system prompt."""
        from ..services.environment_detector import get_environment_profile

        env = get_environment_profile(self.cwd)
        return env.to_prompt_section()

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for programming assistant."""
        return prompt_service.get_system_prompt(include_tools=True)

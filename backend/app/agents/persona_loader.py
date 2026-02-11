"""Persona file loader for Agent configuration.

Follows pattern from PromptTemplateEngine:
- Direct file system reads
- No caching
- Clear error handling for missing files
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.security import SecureFileGateway
from app.security.types import (
    UnsupportedFileTypeError,
)

_DEFAULT_AGENT_DIR: Final[Path] = Path("docs/agents")
_DEFAULT_PERSONA_EXT: Final[str] = ".md"


@dataclass(frozen=True, slots=True)
class PersonaLoadResult:
    """Result of persona file loading."""
    content: str
    file_path: Path
    relative_path: str


class PersonaLoader:
    """Loads agent persona files from project's docs/agents/ directory.

    Design decisions:
    - Pure file system: no database fallback
    - Explicit errors: FileNotFoundError for missing files
    - Secure: uses SecureFileGateway for all reads
    - Simple: no caching, read fresh each time
    """

    def __init__(
        self,
        *,
        gateway: SecureFileGateway,
        agent_dir: Path | None = None,
    ) -> None:
        """Initialize persona loader.

        Args:
            gateway: SecureFileGateway instance for safe file access
            agent_dir: Relative path to agents directory (default: docs/agents)
        """
        self._gateway = gateway
        self._agent_dir = agent_dir or _DEFAULT_AGENT_DIR

    def load_by_name(self, agent_name: str) -> PersonaLoadResult:
        """Load persona by agent name.

        Args:
            agent_name: Name of the agent (e.g., "Frontend Agent")

        Returns:
            PersonaLoadResult with content and metadata

        Raises:
            FileNotFoundError: If persona file doesn't exist
            UnsupportedFileTypeError: If file extension not .md
            PathOutsideRootError: If path escapes project root
            FileOperationTimeoutError: If read times out
        """
        filename = self._sanitize_name(agent_name)
        relative_path = self._agent_dir / f"{filename}{_DEFAULT_PERSONA_EXT}"

        try:
            content = self._gateway.read_text(
                relative_path,
                max_read_bytes=128 * 1024,  # 128KB limit
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Persona file not found for agent '{agent_name}'. "
                f"Expected location: {relative_path.as_posix()}"
            ) from exc

        full_path = self._gateway.root_path / relative_path

        return PersonaLoadResult(
            content=content,
            file_path=full_path,
            relative_path=relative_path.as_posix(),
        )

    def load_by_path(self, persona_path: str) -> PersonaLoadResult:
        """Load persona by relative path stored in database.

        Args:
            persona_path: Relative path from project root (e.g., "docs/agents/frontend.md")

        Returns:
            PersonaLoadResult with content and metadata

        Raises:
            FileNotFoundError: If persona file doesn't exist
            UnsupportedFileTypeError: If file extension not .md
            PathOutsideRootError: If path escapes project root
            FileOperationTimeoutError: If read times out
        """
        path = Path(persona_path)

        if path.suffix.lower() != _DEFAULT_PERSONA_EXT:
            raise UnsupportedFileTypeError(
                f"Persona file must have {_DEFAULT_PERSONA_EXT} extension: {persona_path}"
            )

        try:
            content = self._gateway.read_text(
                path,
                max_read_bytes=128 * 1024,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Persona file not found at: {persona_path}"
            ) from exc

        full_path = self._gateway.root_path / path

        return PersonaLoadResult(
            content=content,
            file_path=full_path,
            relative_path=path.as_posix(),
        )

    def exists(self, agent_name: str) -> bool:
        """Check if persona file exists for agent.

        Args:
            agent_name: Name of the agent

        Returns:
            True if persona file exists, False otherwise
        """
        filename = self._sanitize_name(agent_name)
        relative_path = self._agent_dir / f"{filename}{_DEFAULT_PERSONA_EXT}"
        full_path = self._gateway.root_path / relative_path
        return full_path.is_file()

    def resolve_path(self, agent_name: str) -> str:
        """Resolve persona file path for agent name.

        Args:
            agent_name: Name of the agent

        Returns:
            Relative path from project root (e.g., "docs/agents/frontend_agent.md")
        """
        filename = self._sanitize_name(agent_name)
        relative_path = self._agent_dir / f"{filename}{_DEFAULT_PERSONA_EXT}"
        return relative_path.as_posix()

    def _sanitize_name(self, agent_name: str) -> str:
        """Sanitize agent name for safe filename.

        Args:
            agent_name: Raw agent name

        Returns:
            Safe filename (lowercase, underscores instead of spaces)
        """
        return (
            agent_name.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

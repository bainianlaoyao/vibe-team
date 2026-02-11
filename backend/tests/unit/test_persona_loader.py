"""Unit tests for PersonaLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.persona_loader import PersonaLoader, PersonaLoadResult
from app.security import SecureFileGateway
from app.security.types import (
    PathOutsideRootError,
    UnsupportedFileTypeError,
)


def test_load_by_name_success(tmp_path: Path) -> None:
    """Test successful persona loading by agent name."""
    # Setup
    agents_dir = tmp_path / "docs" / "agents"
    agents_dir.mkdir(parents=True)
    persona_file = agents_dir / "frontend_agent.md"
    persona_file.write_text("# Frontend Agent\n\nTest persona", encoding="utf-8")

    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    # Execute
    result = loader.load_by_name("Frontend Agent")

    # Assert
    assert isinstance(result, PersonaLoadResult)
    # Normalize newlines for Windows compatibility
    content = result.content.replace("\r\n", "\n")
    assert content == "# Frontend Agent\n\nTest persona"
    assert result.file_path == persona_file
    assert result.relative_path == "docs/agents/frontend_agent.md"


def test_load_by_name_file_missing(tmp_path: Path) -> None:
    """Test FileNotFoundError when persona file doesn't exist."""
    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    with pytest.raises(FileNotFoundError, match="Persona file not found"):
        loader.load_by_name("Missing Agent")


def test_load_by_path_success(tmp_path: Path) -> None:
    """Test successful persona loading by path."""
    # Setup
    persona_file = tmp_path / "docs" / "agents" / "custom.md"
    persona_file.parent.mkdir(parents=True)
    persona_file.write_text("Custom persona content", encoding="utf-8")

    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    # Execute
    result = loader.load_by_path("docs/agents/custom.md")

    # Assert
    assert result.content == "Custom persona content"
    assert result.relative_path == "docs/agents/custom.md"


def test_load_by_path_invalid_extension(tmp_path: Path) -> None:
    """Test UnsupportedFileTypeError for non-.md files."""
    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    with pytest.raises(UnsupportedFileTypeError, match="must have .md extension"):
        loader.load_by_path("docs/agents/custom.txt")


def test_exists_true(tmp_path: Path) -> None:
    """Test exists() returns True for existing persona."""
    # Setup
    agents_dir = tmp_path / "docs" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "test.md").write_text("test", encoding="utf-8")

    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    # Assert
    assert loader.exists("Test") is True


def test_exists_false(tmp_path: Path) -> None:
    """Test exists() returns False for missing persona."""
    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    assert loader.exists("Missing Agent") is False


def test_sanitize_name() -> None:
    """Test name sanitization for filenames."""
    gateway = SecureFileGateway(root_path=Path("/tmp"))
    loader = PersonaLoader(gateway=gateway)

    assert loader._sanitize_name("Frontend Agent") == "frontend_agent"
    assert loader._sanitize_name("Backend-Dev") == "backend_dev"
    assert loader._sanitize_name("  Spaces  ") == "spaces"


def test_resolve_path() -> None:
    """Test path resolution for agent names."""
    gateway = SecureFileGateway(root_path=Path("/tmp"))
    loader = PersonaLoader(gateway=gateway)

    path = loader.resolve_path("Test Agent")
    assert path == "docs/agents/test_agent.md"


def test_load_by_path_escapes_root(tmp_path: Path) -> None:
    """Test PathOutsideRootError for paths escaping root."""
    gateway = SecureFileGateway(root_path=tmp_path)
    loader = PersonaLoader(gateway=gateway)

    with pytest.raises(PathOutsideRootError):
        # Must have .md extension to pass the first check
        loader.load_by_path("../../../outside_root.md")

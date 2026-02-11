from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, cast

from sqlmodel import Session, select

from app.agents.persona_loader import PersonaLoader
from app.db.models import Agent, Document, Project, Task, TaskDependency
from app.security import SecureFileGateway

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "prompt_templates"
_CHARS_PER_TOKEN = 4
_TRUNCATION_SUFFIX = "\n...[truncated]"
_MIN_SECTION_TOKENS = 16
_DEFAULT_TASK_TYPE = "default"
_DEFAULT_PHASE = "default"
_PRIORITY_TOKEN_BUDGET: dict[int, int] = {
    1: 3200,
    2: 2800,
    3: 2400,
    4: 1800,
    5: 1400,
}


@dataclass(frozen=True, slots=True)
class ContextBuildRequest:
    task_id: int
    phase: str = _DEFAULT_PHASE
    task_type: str = _DEFAULT_TASK_TYPE
    token_budget: int | None = None


@dataclass(frozen=True, slots=True)
class ContextBuildResult:
    prompt: str
    template_name: str
    token_budget: int
    estimated_tokens: int
    trimmed_sections: tuple[str, ...]


class PromptTemplateEngine:
    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or _DEFAULT_TEMPLATE_DIR

    @property
    def template_dir(self) -> Path:
        return self._template_dir

    def resolve_template_name(self, *, phase: str, task_type: str) -> str:
        normalized_phase = _normalize_template_key(phase)
        normalized_type = _normalize_template_key(task_type)
        candidates = (
            f"{normalized_phase}__{normalized_type}.tmpl",
            f"{normalized_phase}__default.tmpl",
            f"default__{normalized_type}.tmpl",
            "default__default.tmpl",
        )
        for candidate in candidates:
            if (self._template_dir / candidate).is_file():
                return candidate
        raise FileNotFoundError(
            f"No template found in {self._template_dir.as_posix()} for "
            f"phase='{phase}' task_type='{task_type}'."
        )

    def render(self, *, template_name: str, context: dict[str, str]) -> str:
        raw = (self._template_dir / template_name).read_text(encoding="utf-8")
        template = Template(raw)
        return template.safe_substitute(context)


class PromptContextBuilder:
    def __init__(
        self,
        *,
        session: Session,
        template_engine: PromptTemplateEngine | None = None,
    ) -> None:
        self._session = session
        self._template_engine = template_engine or PromptTemplateEngine()

    def build(self, request: ContextBuildRequest) -> ContextBuildResult:
        task = self._require_task(request.task_id)
        project = self._require_project(task.project_id)
        agent = self._require_agent(task.assignee_agent_id) if task.assignee_agent_id else None
        token_budget = _resolve_token_budget(task.priority, request.token_budget)
        gateway = SecureFileGateway(root_path=project.root_path)

        sections = {
            "phase": request.phase,
            "task_type": request.task_type,
            "task_summary": self._build_task_summary(task=task),
            "dependency_summary": self._build_dependency_summary(task=task),
            "agent_persona": (
                self._load_agent_persona(agent=agent, gateway=gateway)
                if agent
                else "(no agent assigned)"
            ),
            "global_rules": self._load_global_rules(gateway),
            "project_docs": self._load_project_documents(task=task, gateway=gateway),
            "tasks_md_snapshot": self._load_tasks_md_snapshot(gateway),
        }

        template_name = self._template_engine.resolve_template_name(
            phase=request.phase,
            task_type=request.task_type,
        )

        prompt = self._template_engine.render(template_name=template_name, context=sections)
        estimated_tokens = _estimate_tokens(prompt)
        if estimated_tokens <= token_budget:
            return ContextBuildResult(
                prompt=prompt,
                template_name=template_name,
                token_budget=token_budget,
                estimated_tokens=estimated_tokens,
                trimmed_sections=(),
            )

        trimmed_prompt, trimmed_sections = self._trim_prompt_to_budget(
            template_name=template_name,
            sections=sections,
            token_budget=token_budget,
        )
        return ContextBuildResult(
            prompt=trimmed_prompt,
            template_name=template_name,
            token_budget=token_budget,
            estimated_tokens=_estimate_tokens(trimmed_prompt),
            trimmed_sections=tuple(trimmed_sections),
        )

    def _trim_prompt_to_budget(
        self,
        *,
        template_name: str,
        sections: dict[str, str],
        token_budget: int,
    ) -> tuple[str, list[str]]:
        section_names = [
            "tasks_md_snapshot",
            "project_docs",
            "dependency_summary",
            "global_rules",
            "task_summary",
        ]
        trimmed_sections: list[str] = []
        mutable_sections = dict(sections)

        for name in section_names:
            prompt = self._template_engine.render(
                template_name=template_name,
                context=mutable_sections,
            )
            if _estimate_tokens(prompt) <= token_budget:
                return prompt, trimmed_sections

            current_tokens = _estimate_tokens(mutable_sections[name])
            next_tokens = max(_MIN_SECTION_TOKENS, current_tokens // 2)
            trimmed = _truncate_by_tokens(mutable_sections[name], max_tokens=next_tokens)
            if trimmed != mutable_sections[name]:
                mutable_sections[name] = trimmed
                trimmed_sections.append(name)

        prompt = self._template_engine.render(template_name=template_name, context=mutable_sections)
        if _estimate_tokens(prompt) > token_budget:
            # Final hard cap while preserving stable structure.
            prompt = _truncate_by_tokens(prompt, max_tokens=token_budget)
            if "full_prompt" not in trimmed_sections:
                trimmed_sections.append("full_prompt")
        return prompt, trimmed_sections

    def _require_task(self, task_id: int) -> Task:
        task = self._session.get(Task, task_id)
        if task is None:
            raise LookupError(f"Task {task_id} does not exist.")
        return task

    def _require_project(self, project_id: int) -> Project:
        project = self._session.get(Project, project_id)
        if project is None:
            raise LookupError(f"Project {project_id} does not exist.")
        return project

    def _require_agent(self, agent_id: int) -> Agent:
        agent = self._session.get(Agent, agent_id)
        if agent is None:
            raise LookupError(f"Agent {agent_id} does not exist.")
        return agent

    def _load_agent_persona(self, *, agent: Agent, gateway: SecureFileGateway) -> str:
        """Load agent persona from file system.

        Args:
            agent: Agent model with persona_path field
            gateway: SecureFileGateway for safe file access

        Returns:
            Persona content as string

        Raises:
            FileNotFoundError: If persona file doesn't exist (no fallback)
        """
        if not agent.persona_path:
            return "(no persona configured)"

        loader = PersonaLoader(gateway=gateway)

        try:
            result = loader.load_by_path(agent.persona_path)
            return f"# Agent Persona: {agent.name}\n\n{result.content}"
        except FileNotFoundError as exc:
            # No database fallback - strict requirement
            raise FileNotFoundError(
                f"Agent '{agent.name}' (ID: {agent.id}) references persona file "
                f"'{agent.persona_path}' which does not exist. "
                f"Please create the persona file or update the agent configuration."
            ) from exc

    def _build_task_summary(self, *, task: Task) -> str:
        lines = [
            f"- task_id: {task.id}",
            f"- title: {task.title}",
            f"- status: {task.status}",
            f"- priority: {task.priority}",
            f"- assignee_agent_id: {task.assignee_agent_id}",
            f"- due_at: {task.due_at}",
            "- description:",
            task.description or "(none)",
        ]
        return "\n".join(lines)

    def _build_dependency_summary(self, *, task: Task) -> str:
        entries: list[str] = []
        if task.parent_task_id is not None:
            parent = self._session.get(Task, task.parent_task_id)
            if parent is not None:
                entries.append(f"- parent: #{parent.id} {parent.title} ({parent.status})")

        statement = (
            select(TaskDependency, Task)
            .join(Task, cast(Any, Task.id) == TaskDependency.depends_on_task_id)
            .where(TaskDependency.task_id == task.id)
            .order_by(cast(Any, TaskDependency.depends_on_task_id))
        )
        for dependency, depended_task in self._session.exec(statement):
            entries.append(
                f"- depends_on: #{depended_task.id} {depended_task.title} "
                f"({depended_task.status}) [{dependency.dependency_type}]"
            )
        return "\n".join(entries) if entries else "(none)"

    def _load_global_rules(self, gateway: SecureFileGateway) -> str:
        docs_dir = gateway.root_path / "docs"
        if not docs_dir.is_dir():
            return "(no docs directory)"

        chunks: list[str] = []
        for file_path in sorted(docs_dir.glob("*.md"))[:4]:
            relative = file_path.relative_to(gateway.root_path)
            content = gateway.read_text(relative, max_read_bytes=24 * 1024)
            chunks.append(f"### {relative.as_posix()}\n{content.strip()}")
        return "\n\n".join(chunks) if chunks else "(no markdown rules found)"

    def _load_project_documents(self, *, task: Task, gateway: SecureFileGateway) -> str:
        statement = (
            select(Document)
            .where(Document.project_id == task.project_id)
            .order_by(
                cast(Any, Document.is_mandatory).desc(),
                cast(Any, Document.updated_at).desc(),
            )
            .limit(8)
        )
        rows = list(self._session.exec(statement).all())
        if not rows:
            return "(no indexed project documents)"

        chunks: list[str] = []
        for row in rows:
            try:
                content = gateway.read_text(row.path, max_read_bytes=24 * 1024)
            except FileNotFoundError:
                content = "(missing file on disk)"
            chunks.append(
                f"### {row.path} [doc_type={row.doc_type}, mandatory={row.is_mandatory}]\n"
                f"{content.strip()}"
            )
        return "\n\n".join(chunks)

    def _load_tasks_md_snapshot(self, gateway: SecureFileGateway) -> str:
        target = gateway.root_path / "tasks.md"
        if not target.is_file():
            return "(tasks.md not found)"
        return gateway.read_text("tasks.md", max_read_bytes=24 * 1024).strip()


def _normalize_template_key(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    return cleaned or "default"


def _resolve_token_budget(task_priority: int, override_budget: int | None) -> int:
    if override_budget is not None:
        if override_budget <= 0:
            raise ValueError("token_budget must be greater than 0")
        return override_budget
    return _PRIORITY_TOKEN_BUDGET.get(task_priority, _PRIORITY_TOKEN_BUDGET[3])


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _truncate_by_tokens(text: str, *, max_tokens: int) -> str:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")
    if _estimate_tokens(text) <= max_tokens:
        return text
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if max_chars <= len(_TRUNCATION_SUFFIX):
        return _TRUNCATION_SUFFIX[:max_chars]
    return f"{text[: max_chars - len(_TRUNCATION_SUFFIX)]}{_TRUNCATION_SUFFIX}"

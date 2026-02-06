from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import DocumentType
from app.db.models import Document, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate


@dataclass(frozen=True, slots=True)
class DocumentFilters:
    project_id: int | None = None
    doc_type: DocumentType | None = None
    is_mandatory: bool | None = None
    title_query: str | None = None


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, document: Document) -> Document:
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: DocumentFilters | None = None,
    ) -> Page[Document]:
        active_filters = filters or DocumentFilters()
        active_pagination = pagination or Pagination()

        statement = select(Document)
        if active_filters.project_id is not None:
            statement = statement.where(Document.project_id == active_filters.project_id)
        if active_filters.doc_type is not None:
            statement = statement.where(Document.doc_type == active_filters.doc_type.value)
        if active_filters.is_mandatory is not None:
            statement = statement.where(Document.is_mandatory == active_filters.is_mandatory)
        if active_filters.title_query:
            statement = statement.where(Document.title.ilike(f"%{active_filters.title_query}%"))

        statement = statement.order_by(Document.updated_at.desc(), Document.id.desc())
        return paginate(self.session, statement, pagination=active_pagination)

    def update_metadata(
        self,
        *,
        document_id: int,
        expected_version: int,
        title: str | None = None,
        doc_type: DocumentType | None = None,
        tags_json: list[str] | None = None,
        is_mandatory: bool | None = None,
    ) -> Document:
        values: dict[str, object] = {
            "updated_at": utc_now(),
            "version": expected_version + 1,
        }

        if title is not None:
            values["title"] = title
        if doc_type is not None:
            values["doc_type"] = doc_type.value
        if tags_json is not None:
            values["tags_json"] = tags_json
        if is_mandatory is not None:
            values["is_mandatory"] = is_mandatory

        statement = (
            update(Document)
            .where(Document.id == document_id)
            .where(Document.version == expected_version)
            .values(**values)
        )
        result = self.session.exec(statement)

        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"document {document_id} version mismatch, expected {expected_version}"
            )

        self.session.commit()
        updated = self.session.get(Document, document_id)
        if updated is None:
            raise OptimisticLockError(f"document {document_id} missing after optimistic update")
        return updated

# BeeBeeBrain - AI Engineering Management Platform

## Architecture & Tech Stack
- **Frontend**: Vue 3 + TypeScript, Vite, TailwindCSS, shadcn-vue, Pinia, Monaco Editor.
- **Backend**: Python 3.10+, FastAPI, SQLModel (SQLAlchemy), Celery (Tasks), Socket.IO (Python).
- **Engine**: Parallel execution using Git Worktree for isolation.
- **Core Concept**: Users manage "Agents" as parallel workers via a dashboard.

## Coding Standards
- **Frontend**:
  - Language: TypeScript (Strict Mode). Avoid `any`.
  - Style: Vue 3 Composition API (`<script setup>`).
  - Styling: TailwindCSS first.
- **Backend**:
  - Language: Python 3.10+ with Type Hints.
  - Framework: FastAPI + Pydantic models.
  - Style: PEP 8 compliant.
- **Commits**: Conventional Commits (e.g., `feat: add dashboard`, `fix: resolve conflict`).
- **Formatting**: ESLint + Prettier (Frontend), Black + isort (Backend).

## Project Structure
- `/shared`: Shared TypeScript types and constants.
- `/docs`: Detailed architecture and API documentation.

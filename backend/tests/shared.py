from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


@dataclass
class ApiTestContext:
    client: TestClient
    engine: Engine
    project_id: int
    project_root: Path
    other_project_id: int

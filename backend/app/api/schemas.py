from pydantic import BaseModel


class HealthzResponse(BaseModel):
    status: str
    service: str
    env: str


class ReadinessChecks(BaseModel):
    configuration: str


class ReadyzResponse(BaseModel):
    status: str
    checks: ReadinessChecks

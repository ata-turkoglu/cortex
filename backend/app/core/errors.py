from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    correlation_id: str
    details_available: bool = False
    details: dict[str, str] | None = None

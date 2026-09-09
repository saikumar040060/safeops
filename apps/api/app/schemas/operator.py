import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import OperatorRole


class OperatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: OperatorRole
    is_active: bool

from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_object_id(value: Any) -> Any:
    return str(value) if isinstance(value, ObjectId) else value


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]


class BaseDocument(BaseModel):
    """Base for every Mongo document: `_id` (ObjectId) is exposed as `id` (str)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: Optional[PyObjectId] = Field(default=None, validation_alias=AliasChoices("_id", "id"))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(exclude={"id"})
        if self.id:
            data["_id"] = ObjectId(self.id)
        return data


class PlatformSetting(BaseDocument):
    key: str
    value: Any = None
    description: str = ""
    is_public: bool = False


class AuditLog(BaseDocument):
    actor_id: Optional[PyObjectId] = None
    actor_role: str = "system"
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    request_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

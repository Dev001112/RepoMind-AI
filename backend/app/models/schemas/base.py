"""Shared Pydantic base for API schemas.

Emits/accepts camelCase JSON (the frontend's convention) while keeping
Pythonic snake_case field names internally, and reads straight off
SQLAlchemy ORM instances.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

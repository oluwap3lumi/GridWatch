"""Response schemas describe fields that Pydantic actually serializes, including defaults."""

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

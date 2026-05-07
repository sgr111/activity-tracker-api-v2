from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime


class AuditResponse(BaseModel):
    id:         int
    operation:  str
    changed_at: datetime
    changed_by: Optional[str]
    old_data:   Optional[dict[str, Any]]
    new_data:   Optional[dict[str, Any]]

    model_config = {"from_attributes": True}

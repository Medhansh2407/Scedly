"""
ScheduledBlock Pydantic model (non-table).

This is a derived view used internally by scheduling services.
It is not persisted separately but derived from Task fields.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from .models import EnergyLevel, Flexibility, Priority, TaskStatus


class ScheduledBlock(BaseModel):
    """
    Represents a scheduled time block for a task.
    
    This is a non-table model used internally by scheduling services.
    It is derived from Task fields and not persisted separately.
    """
    task_id: uuid.UUID
    start: datetime
    end: datetime
    priority: Priority
    energy_level: EnergyLevel
    flexibility: Flexibility
    status: TaskStatus

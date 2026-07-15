"""
One-shot migration: add `start_date` column to the existing `tasks` table.

SQLModel's metadata.create_all() only creates missing tables; it does NOT
alter existing ones. So new columns added to a model after the table exists
need an explicit DDL statement.

Idempotent: uses `ADD COLUMN IF NOT EXISTS`, safe to re-run.
"""

from sqlmodel import text
from app.db import engine

DDL = "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS start_date TIMESTAMP"

with engine.begin() as conn:  # begin() = auto-commit on success
    conn.execute(text(DDL))
    print("Migration applied: tasks.start_date column ensured.")

# Verify the column is there
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'tasks' AND column_name = 'start_date'"
    )).all()
    if rows:
        print(f"Verified -> {rows[0]}")
    else:
        print("ERROR: start_date column is missing after migration -- BUG")

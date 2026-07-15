"""Add all missing columns to the database."""
import os
os.chdir(r"C:\Users\Medhansh\Desktop\Startups\startup_calendar_app\backend")
from dotenv import load_dotenv
load_dotenv()
from app.db import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)

def add_col(table, column, col_type, default=None):
    cols = [c["name"] for c in inspector.get_columns(table)]
    if column not in cols:
        default_clause = f" DEFAULT {default}" if default else ""
        sql = f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type}{default_clause}'
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        print(f"  Added {table}.{column}")
    else:
        print(f"  OK {table}.{column}")

print("Users table:")
add_col("users", "plan", "VARCHAR", "'trial'")
add_col("users", "trial_ends_at", "TIMESTAMP", None)
add_col("users", "stripe_customer_id", "VARCHAR", None)
add_col("users", "stripe_subscription_id", "VARCHAR", None)
add_col("users", "subscription_status", "VARCHAR", None)
add_col("users", "current_period_end", "TIMESTAMP", None)

print("\nUser preferences table:")
add_col("user_preferences", "high_energy_window_start", "TIME", "'06:00'")
add_col("user_preferences", "high_energy_window_end", "TIME", "'14:00'")
add_col("user_preferences", "low_energy_window_start", "TIME", "'14:00'")
add_col("user_preferences", "low_energy_window_end", "TIME", "'22:00'")
add_col("user_preferences", "onboarding_completed", "BOOLEAN", "FALSE")
add_col("user_preferences", "outside_window_threshold_hours", "INTEGER", "48")
add_col("user_preferences", "timezone", "VARCHAR", "'UTC'")
add_col("user_preferences", "focus_hours_enabled", "BOOLEAN", "FALSE")
add_col("user_preferences", "focus_hours_start", "TIME", None)
add_col("user_preferences", "focus_hours_end", "TIME", None)

print("\nTasks table:")
add_col("tasks", "embedding", "vector(384)", None)
add_col("tasks", "scheduling_rationale", "TEXT", None)
add_col("tasks", "continued_from", "UUID", None)
add_col("tasks", "completion_order", "INTEGER", None)
add_col("tasks", "missed_at", "TIMESTAMP", None)
add_col("tasks", "start_date", "TIMESTAMP", None)
add_col("tasks", "category", "VARCHAR", None)

print("\nDone! Verifying users columns:")
inspector2 = inspect(engine)
cols = [c["name"] for c in inspector2.get_columns("users")]
print(f"  Users: {cols}")

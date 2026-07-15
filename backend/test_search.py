import os
os.chdir(r"C:\Users\Medhansh\Desktop\Startups\startup_calendar_app\backend")
from dotenv import load_dotenv; load_dotenv()
from app.db import get_session, engine
from app.crud.task_crud import search_by_title
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT user_id, title FROM tasks")).fetchall()
    print("Tasks:", [(r[0], r[1]) for r in rows])

if rows:
    uid = rows[0][0]
    db = get_session()
    r1 = search_by_title(db, uid, "coding")
    print("Search 'coding':", [t.title for t in r1])
    r2 = search_by_title(db, uid, "coding session")
    print("Search 'coding session':", [t.title for t in r2])
    db.close()

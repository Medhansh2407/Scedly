
import os, time, httpx, jwt as pyjwt
os.chdir(r"C:\Users\Medhansh\Desktop\Startups\startup_calendar_app\backend")
from dotenv import load_dotenv; load_dotenv()
from app.db import engine
from sqlalchemy import text

secret = os.environ["SUPABASE_JWT_SECRET"]
token = pyjwt.encode({"sub":"e8db9718-fad3-4237-b26c-2b691004840f","email":"medhanshnarang2407@gmail.com","aud":"authenticated","exp":int(time.time())+3600,"user_metadata":{},"app_metadata":{}}, secret, algorithm="HS256")

with engine.connect() as conn:
    r = conn.execute(text("SELECT id, title, status FROM tasks WHERE user_id = '1935f283-71b6-4349-b0de-c1bb6d4d8d44' LIMIT 1"))
    row = r.fetchone()
    if row:
        print(f"Task: {row[1]} status={row[2]} id={row[0]}")
        resp = httpx.post(f"http://localhost:8000/tasks/{row[0]}/complete", headers={"Authorization": "Bearer " + token}, timeout=10)
        print(f"Complete: {resp.status_code} {resp.text[:200]}")
    else:
        print("No tasks found")

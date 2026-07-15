"""
CLI client for the Autonomous Scheduler.

Usage:
    python cli.py

Set SCHEDULER_API_KEY in your .env or environment.
Optionally set SCHEDULER_BASE_URL (defaults to http://localhost:8000).
"""

import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SCHEDULER_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("SCHEDULER_API_KEY")
SESSION_ID = "cli-session"


def chat(message: str):
    """Send a message and stream the SSE response to terminal."""
    with httpx.stream(
        "POST",
        f"{BASE_URL}/chat",
        json={"message": message, "session_id": SESSION_ID},
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60,
    ) as resp:
        if resp.status_code != 200:
            print(f"\n[Error {resp.status_code}] {resp.read().decode()}")
            return

        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                if chunk.get("type") == "token":
                    print(chunk["content"], end="", flush=True)
            except json.JSONDecodeError:
                print(data, end="", flush=True)
        print()  # newline after response


def main():
    if not API_KEY:
        print("Error: SCHEDULER_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    print("Calendar Agent CLI (type 'quit' to exit)\n")
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not msg:
            continue
        if msg.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        print("Agent: ", end="")
        chat(msg)


if __name__ == "__main__":
    main()

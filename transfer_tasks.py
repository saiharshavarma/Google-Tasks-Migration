from __future__ import annotations

import json
import os
import time
import random
from typing import Dict, List, Set

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/tasks"]

# Throttle inserts to reduce chance of quota errors (seconds between inserts)
MIN_INSERT_INTERVAL_SEC = 0.35

# Retry/backoff settings
MAX_RETRIES = 12
BACKOFF_BASE_SEC = 1.5
BACKOFF_MAX_SEC = 90

CHECKPOINT_FILE = "checkpoint_copied_task_ids.json"


def get_service(token_file: str):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("tasks", "v1", credentials=creds)


def list_all_tasklists(service) -> List[dict]:
    items: List[dict] = []
    page_token = None
    while True:
        resp = service.tasklists().list(maxResults=100, pageToken=page_token).execute()
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def list_all_tasks(service, tasklist_id: str) -> List[dict]:
    items: List[dict] = []
    page_token = None
    while True:
        resp = (
            service.tasks()
            .list(
                tasklist=tasklist_id,
                maxResults=100,
                pageToken=page_token,
                showCompleted=True,  # include completed tasks
                showHidden=True,
                showDeleted=False,
            )
            .execute()
        )
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return [t for t in items if t.get("id") and not t.get("deleted")]


def create_tasklist(dest_service, title: str) -> str:
    created = dest_service.tasklists().insert(body={"title": title}).execute()
    return created["id"]


def build_task_body(src_task: dict) -> dict:
    body = {
        "title": src_task.get("title", ""),
        "notes": src_task.get("notes", ""),
        "status": "completed" if src_task.get("status") == "completed" else "needsAction",
    }

    # Due date (RFC3339). All-day tasks are commonly stored with a midnight timestamp.
    if src_task.get("due"):
        body["due"] = src_task["due"]

    # Completed timestamp if present
    if src_task.get("completed"):
        body["completed"] = src_task["completed"]

    return body


def load_checkpoint() -> Set[str]:
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("copied_source_task_ids", []))


def save_checkpoint(copied_ids: Set[str]) -> None:
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"copied_source_task_ids": sorted(copied_ids)}, f, indent=2)


def should_retry_http_error(e: HttpError) -> bool:
    # Retry on quota / rate limiting / transient server errors
    status = getattr(e.resp, "status", None)
    if status in (403, 429, 500, 503):
        return True
    return False


def execute_with_retry(callable_fn, action_desc: str):
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return callable_fn()
        except HttpError as e:
            last_err = e
            if not should_retry_http_error(e):
                raise

            # Exponential backoff with jitter
            sleep_for = min(BACKOFF_MAX_SEC, (BACKOFF_BASE_SEC ** attempt)) + random.uniform(0, 0.75)
            print(f"[Retry] {action_desc} failed with {e.resp.status}. Sleeping {sleep_for:.2f}s then retrying...")
            time.sleep(sleep_for)

    # Exhausted retries
    raise last_err


def transfer(prefix_lists: str = "[From Account 1] ") -> None:
    print("Sign in to SOURCE (Account 1) in the browser window that opens.")
    src = get_service("token_source.json")

    print("Sign in to DESTINATION (Account 2) in the browser window that opens.")
    dst = get_service("token_dest.json")

    copied_ids = load_checkpoint()

    src_lists = list_all_tasklists(src)
    print(f"Found {len(src_lists)} task lists in Account 1.")

    # Map source list id -> destination list id
    list_id_map: Dict[str, str] = {}

    # Create task lists in destination
    for tl in src_lists:
        title = tl.get("title", "Untitled")
        new_title = f"{prefix_lists}{title}"

        dest_list_id = execute_with_retry(
            lambda: create_tasklist(dst, new_title),
            f"create task list '{new_title}'"
        )
        list_id_map[tl["id"]] = dest_list_id
        print(f"Created list in Account 2: {new_title}")

    # Copy tasks
    for src_list_id, dest_list_id in list_id_map.items():
        tasks = list_all_tasks(src, src_list_id)
        total = len(tasks)
        print(f"Preparing to copy {total} tasks from one list...")

        inserted = 0
        skipped = 0
        last_insert_time = 0.0

        for t in tasks:
            src_task_id = t["id"]
            if src_task_id in copied_ids:
                skipped += 1
                continue

            # Throttle
            now = time.time()
            elapsed = now - last_insert_time
            if elapsed < MIN_INSERT_INTERVAL_SEC:
                time.sleep(MIN_INSERT_INTERVAL_SEC - elapsed)

            body = build_task_body(t)

            execute_with_retry(
                lambda: dst.tasks().insert(tasklist=dest_list_id, body=body).execute(),
                f"insert task '{body.get('title', '')[:40]}'"
            )

            last_insert_time = time.time()
            copied_ids.add(src_task_id)
            inserted += 1

            # Save checkpoint every 20 inserts
            if inserted % 20 == 0:
                save_checkpoint(copied_ids)
                print(f"Progress: inserted {inserted}, skipped {skipped} (checkpoint saved)")

        save_checkpoint(copied_ids)
        print(f"List done. Inserted {inserted}, skipped {skipped}.")

    print("Done. Verify in tasks.google.com (Account 2).")


if __name__ == "__main__":
    transfer(prefix_lists="[From Account 1] ")
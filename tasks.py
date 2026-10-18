"""A simple to-do list saved in a JSON file.

Each task looks like: {"id": 1, "title": "Buy milk", "done": false}
Every function takes a `path` so tests can use a temporary file.
"""

import json
from pathlib import Path

TASKS_FILE = Path("tasks.json")


def load_tasks(path=TASKS_FILE):
    """Read all tasks from the file. Return an empty list if it doesn't exist yet."""
    path = Path(path)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_tasks(tasks, path=TASKS_FILE):
    """Write all tasks to the file, nicely indented so it's easy to read."""
    Path(path).write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")


def list_tasks(path=TASKS_FILE):
    """Return every task."""
    return load_tasks(path)


def add_task(title, path=TASKS_FILE):
    """Add a new, not-done task and return it. Raises ValueError for an empty title."""
    title = title.strip()
    if not title:
        raise ValueError("Task title can't be empty.")

    tasks = load_tasks(path)
    # Next id = highest existing id + 1, so ids stay unique even after deletions.
    next_id = max((task["id"] for task in tasks), default=0) + 1
    task = {"id": next_id, "title": title, "done": False}
    tasks.append(task)
    save_tasks(tasks, path)
    return task


def complete_task(task_id, path=TASKS_FILE):
    """Mark a task as done and return it. Raises ValueError if the id doesn't exist."""
    tasks = load_tasks(path)
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            save_tasks(tasks, path)
            return task
    raise ValueError(f"No task with id {task_id}.")

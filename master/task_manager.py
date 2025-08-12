import uuid
import time
import threading
from typing import Dict, Optional

class TaskManager:
    """
    Manages task creation, storage, and status tracking
    for MasterAgent in the honeypot system.
    """

    def __init__(self):
        self.tasks = {}  # task_id -> task dict
        self.lock = threading.Lock()

    def create_task(self, command: dict, target_agent: str) -> dict:
        """
        Create a new task with unique ID and initial metadata.
        """
        task_id = str(uuid.uuid4())
        timestamp = time.time()

        task = {
            "task_id": task_id,
            "created_at": timestamp,
            "command": command,
            "target_agent": target_agent,
            "status": "pending",
        }

        with self.lock:
            self.tasks[task_id] = task

        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        """
        Retrieve a task by its ID.
        """
        with self.lock:
            return self.tasks.get(task_id)

    def update_task_status(self, task_id: str, status: str):
        """
        Update the status of a task.
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task["status"] = status
                task["updated_at"] = time.time()

    def get_all_tasks(self) -> Dict[str, dict]:
        """
        Return all stored tasks.
        """
        with self.lock:
            return dict(self.tasks)
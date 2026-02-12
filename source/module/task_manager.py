from datetime import datetime
from uuid import uuid4

__all__ = ["TaskManager"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _empty_statistics() -> dict[str, int]:
    return {
        "all": 0,
        "success": 0,
        "fail": 0,
        "skip": 0,
        "filtered": 0,
    }


class TaskManager:
    def __init__(self):
        self.tasks: dict[str, dict] = {}

    def create(self, mode: str) -> str:
        task_id = uuid4().hex
        self.tasks[task_id] = {
            "task_id": task_id,
            "mode": mode,
            "status": "pending",
            "started_at": _now(),
            "finished_at": None,
            "progress": _empty_statistics(),
            "summary": _empty_statistics(),
            "errors": [],
        }
        return task_id

    def get(self, task_id: str) -> dict | None:
        if task := self.tasks.get(task_id):
            # Avoid external mutation.
            return {
                **task,
                "progress": task["progress"].copy(),
                "summary": task["summary"].copy(),
                "errors": list(task["errors"]),
            }
        return None

    def mark_running(self, task_id: str, all_count: int = 0):
        if task := self.tasks.get(task_id):
            task["status"] = "running"
            task["progress"]["all"] = all_count

    def update_progress(
        self,
        task_id: str,
        *,
        all_count: int,
        success: int,
        fail: int,
        skip: int,
        filtered: int,
    ):
        if task := self.tasks.get(task_id):
            task["progress"] = {
                "all": all_count,
                "success": success,
                "fail": fail,
                "skip": skip,
                "filtered": filtered,
            }

    def add_error(self, task_id: str, message: str):
        if task := self.tasks.get(task_id):
            task["errors"].append(message)

    def complete(
        self,
        task_id: str,
        *,
        all_count: int,
        success: int,
        fail: int,
        skip: int,
        filtered: int,
    ):
        if task := self.tasks.get(task_id):
            summary = {
                "all": all_count,
                "success": success,
                "fail": fail,
                "skip": skip,
                "filtered": filtered,
            }
            task["status"] = "completed"
            task["finished_at"] = _now()
            task["progress"] = summary
            task["summary"] = summary

    def fail(
        self,
        task_id: str,
        reason: str,
        *,
        all_count: int = 0,
        success: int = 0,
        fail_count: int = 0,
        skip: int = 0,
        filtered: int = 0,
    ):
        if task := self.tasks.get(task_id):
            task["status"] = "failed"
            task["finished_at"] = _now()
            task["errors"].append(reason)
            summary = {
                "all": all_count,
                "success": success,
                "fail": fail_count,
                "skip": skip,
                "filtered": filtered,
            }
            task["progress"] = summary
            task["summary"] = summary

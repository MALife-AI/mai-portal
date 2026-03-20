"""백그라운드 태스크 매니저: 인제스션/변환 작업을 비동기 실행 + 취소 지원."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    total: int = 0
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    completed_at: str = ""
    _task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class TaskManager:
    """싱글턴 태스크 매니저."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}

    def submit(
        self,
        name: str,
        coro_factory: Callable[[TaskInfo], Coroutine],
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        info = TaskInfo(
            id=task_id,
            name=name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks[task_id] = info

        async def _run():
            info.status = TaskStatus.RUNNING
            try:
                await coro_factory(info)
                if info.status == TaskStatus.RUNNING:
                    info.status = TaskStatus.COMPLETED
            except asyncio.CancelledError:
                info.status = TaskStatus.CANCELLED
                info.message = "사용자에 의해 취소됨"
            except Exception as exc:
                info.status = TaskStatus.FAILED
                info.error = str(exc)
                logger.error("Task %s failed: %s", task_id, exc)
            finally:
                info.completed_at = datetime.now(timezone.utc).isoformat()

        info._task = asyncio.create_task(_run())
        return task_id

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )[:limit]
        return [t.to_dict() for t in tasks]

    def cancel(self, task_id: str) -> bool:
        info = self._tasks.get(task_id)
        if not info or not info._task:
            return False
        if info.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        info._task.cancel()
        return True

    def cleanup(self, max_age_hours: int = 24) -> int:
        """완료된 오래된 태스크 정리."""
        now = datetime.now(timezone.utc)
        to_remove = []
        for tid, info in self._tasks.items():
            if info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if info.completed_at:
                    completed = datetime.fromisoformat(info.completed_at)
                    if (now - completed).total_seconds() > max_age_hours * 3600:
                        to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)


# 싱글턴
task_manager = TaskManager()

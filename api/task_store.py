"""In-memory task store with progress tracking for async analysis."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event


# Node name → stage key mapping
_NODE_STAGE_MAP: dict[str, str] = {
    # Market analysis
    "Market Analyst": "market_analysis",
    "tools_market": "market_analysis",
    "Msg Clear Market": "market_analysis",
    # Social analysis
    "Social Analyst": "social_analysis",
    "tools_social": "social_analysis",
    "Msg Clear Social": "social_analysis",
    # News analysis
    "News Analyst": "news_analysis",
    "tools_news": "news_analysis",
    "Msg Clear News": "news_analysis",
    # Fundamentals analysis
    "Fundamentals Analyst": "fundamentals_analysis",
    "tools_fundamentals": "fundamentals_analysis",
    "Msg Clear Fundamentals": "fundamentals_analysis",
    # Investment debate
    "Bull Researcher": "investment_debate",
    "Bear Researcher": "investment_debate",
    "Research Manager": "investment_debate",
    "Trader": "investment_debate",
    # Risk assessment
    "Aggressive Analyst": "risk_assessment",
    "Conservative Analyst": "risk_assessment",
    "Neutral Analyst": "risk_assessment",
    "Risk Judge": "risk_assessment",
}

_STAGE_META: dict[str, tuple[str, int]] = {
    "market_analysis": ("📈 市场技术分析", 0),
    "social_analysis": ("💬 社交媒体情绪", 1),
    "news_analysis": ("📰 新闻分析", 2),
    "fundamentals_analysis": ("📋 基本面分析", 3),
    "investment_debate": ("⚖️ 投资辩论与交易计划", 4),
    "risk_assessment": ("🛡️ 风险评估与最终决策", 5),
}

# Analyst request name → stage key
_ANALYST_STAGES: dict[str, str] = {
    "market": "market_analysis",
    "social": "social_analysis",
    "news": "news_analysis",
    "fundamentals": "fundamentals_analysis",
}


@dataclass
class AnalysisTask:
    """Represents one async analysis task."""

    id: str
    ticker: str
    date: str
    analysts: list[str]
    status: str = "pending"  # pending | running | completed | failed | cancelling | cancelled
    current_stage: str = ""
    current_stage_label: str = ""
    progress: float = 0.0
    result: dict | None = None
    error: str | None = None
    created_at: str = ""
    completed_at: str | None = None
    cancel_event: Event = field(default_factory=Event)
    # Ordered list of active stage keys for this task (depends on selected analysts)
    _active_stages: list[str] = field(default_factory=list, repr=False)


class TaskStore:
    """Thread-safe in-memory task store.

    CPython's GIL guarantees dict read/write atomicity for simple operations,
    so no explicit lock is needed.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, AnalysisTask] = {}

    def create_task(self, ticker: str, date: str, analysts: list[str]) -> str:
        """Create a new analysis task and return its ID."""
        task_id = uuid.uuid4().hex

        # Build active stages list based on selected analysts
        active_stages: list[str] = []
        for analyst in analysts:
            stage = _ANALYST_STAGES.get(analyst)
            if stage:
                active_stages.append(stage)
        # Investment debate and risk assessment are always present
        active_stages.extend(["investment_debate", "risk_assessment"])

        task = AnalysisTask(
            id=task_id,
            ticker=ticker,
            date=date,
            analysts=analysts,
            created_at=datetime.now(timezone.utc).isoformat(),
            _active_stages=active_stages,
        )
        self._tasks[task_id] = task
        return task_id

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self._tasks.get(task_id)

    def update_progress(self, task_id: str, node_name: str) -> None:
        """Map a graph node name to a stage and update task progress."""
        task = self._tasks.get(task_id)
        if not task:
            return

        stage_key = _NODE_STAGE_MAP.get(node_name)
        if not stage_key:
            return

        meta = _STAGE_META.get(stage_key)
        if not meta:
            return

        label, _ = meta
        task.current_stage = stage_key
        task.current_stage_label = label
        task.status = "running"

        # Progress = position of current stage in active stages / total stages
        if stage_key in task._active_stages:
            idx = task._active_stages.index(stage_key)
            task.progress = round((idx + 1) / len(task._active_stages), 2)

    def complete_task(self, task_id: str, result: dict) -> None:
        """Mark task as completed with result data."""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = "completed"
        task.progress = 1.0
        task.result = result
        task.completed_at = datetime.now(timezone.utc).isoformat()

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed with error message."""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = "failed"
        task.error = error
        task.completed_at = datetime.now(timezone.utc).isoformat()

    def cancel_task(self, task_id: str) -> bool:
        """Signal a task to cancel. Returns False if task cannot be cancelled."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status not in ("pending", "running"):
            return False
        task.cancel_event.set()
        task.status = "cancelling"
        return True

    def list_tasks(self) -> list[AnalysisTask]:
        """Return all tasks ordered by creation time (newest first)."""
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)


# Module-level singleton
task_store = TaskStore()

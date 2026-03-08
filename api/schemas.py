"""Pydantic request/response models for TradingAgents API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Stock analysis request payload."""

    ticker: str = Field(..., description="Stock ticker symbol, e.g. 'NVDA'")
    date: str | None = Field(
        None,
        description="Analysis date in YYYY-MM-DD format. Defaults to the previous trading day.",
    )
    analysts: list[str] = Field(
        default=["market", "social", "news", "fundamentals"],
        description="Analyst modules to activate.",
    )
    max_debate_rounds: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Maximum investment debate rounds.",
    )


# ---------- Response models ----------


class ReportSection(BaseModel):
    market_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    fundamentals_report: str = ""


class DebateSection(BaseModel):
    bull_history: str = ""
    bear_history: str = ""
    judge_decision: str = ""


class RiskDebateSection(BaseModel):
    aggressive_history: str = ""
    conservative_history: str = ""
    neutral_history: str = ""
    judge_decision: str = ""


class AnalyzeResponse(BaseModel):
    success: bool = True
    ticker: str
    date: str
    decision: str = Field(description="BUY / SELL / HOLD")
    reports: ReportSection
    investment_debate: DebateSection
    trader_investment_plan: str = ""
    risk_debate: RiskDebateSection
    final_trade_decision: str = ""
    timestamp: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_type: str = "unknown"


# ---------- Async task models ----------


class TaskSubmitResponse(BaseModel):
    """Returned immediately when an analysis task is submitted."""

    task_id: str
    status: str = "pending"
    message: str


class TaskStatusResponse(BaseModel):
    """Full task status, including result when completed."""

    task_id: str
    ticker: str
    date: str
    status: str  # pending / running / completed / failed / cancelling / cancelled
    current_stage: str
    current_stage_label: str
    progress: float  # 0.0 - 1.0
    created_at: str
    completed_at: str | None = None
    result: AnalyzeResponse | None = None  # populated only when status == "completed"
    error: str | None = None  # populated only when status == "failed"


class TaskListResponse(BaseModel):
    """Paginated task list."""

    tasks: list[TaskStatusResponse]
    total: int

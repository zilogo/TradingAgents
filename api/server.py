"""FastAPI service for TradingAgents stock analysis (async task mode).

Start with:
    uvicorn api.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException

from api.auth import verify_token
from api.config import API_HOST, API_PORT, build_trading_config
from api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DebateSection,
    ErrorResponse,
    ReportSection,
    RiskDebateSection,
    TaskListResponse,
    TaskStatusResponse,
    TaskSubmitResponse,
)
from api.task_store import task_store

logger = logging.getLogger("tradingagents.api")

app = FastAPI(
    title="TradingAgents API",
    description="Multi-agent stock analysis service powered by TradingAgents framework.",
    version="0.2.0",
)


# ── Startup: pre-build default config ────────────────────────────
_trading_config: dict | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _trading_config
    _trading_config = build_trading_config()
    logger.info(
        "TradingAgents API ready  |  LLM=%s  backend=%s",
        _trading_config["deep_think_llm"],
        _trading_config["backend_url"],
    )


# ── Helpers ──────────────────────────────────────────────────────


def _default_trade_date() -> str:
    """Return the previous business day in YYYY-MM-DD format (UTC)."""
    today = datetime.now(timezone.utc).date()
    offset = 1
    if today.weekday() == 0:  # Monday -> Friday
        offset = 3
    elif today.weekday() == 6:  # Sunday -> Friday
        offset = 2
    return (today - timedelta(days=offset)).isoformat()


def _run_analysis_with_progress(task_id: str, max_debate_rounds: int) -> None:
    """Background thread: stream through graph nodes with progress tracking.

    Uses ``graph.graph.stream(stream_mode="updates")`` so each yielded chunk
    is ``{node_name: state_update}``, allowing us to map node names to stages.
    Cancellation is checked between nodes (cannot interrupt mid-LLM-call).
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    task = task_store.get_task(task_id)
    if not task:
        return

    try:
        task.status = "running"

        cfg = _trading_config.copy()
        cfg["max_debate_rounds"] = max_debate_rounds

        graph = TradingAgentsGraph(
            selected_analysts=task.analysts,
            debug=False,
            config=cfg,
        )

        # Reuse propagator for initial state and graph config
        init_state = graph.propagator.create_initial_state(task.ticker, task.date)
        args = graph.propagator.get_graph_args()
        args["stream_mode"] = "updates"  # override: need node names for progress

        # Stream through graph — each chunk is {node_name: state_update}
        final_state: dict = {}
        for chunk in graph.graph.stream(init_state, **args):
            # Check cancellation between nodes
            if task.cancel_event.is_set():
                task.status = "cancelled"
                task.completed_at = datetime.now(timezone.utc).isoformat()
                logger.info("Task %s cancelled", task_id)
                return

            for node_name, state_update in chunk.items():
                if node_name.startswith("__"):
                    continue
                task_store.update_progress(task_id, node_name)
                # Accumulate non-message fields (messages use add-reducer, skip them)
                if isinstance(state_update, dict):
                    for key, value in state_update.items():
                        if key != "messages":
                            final_state[key] = value

        # Extract BUY/SELL/HOLD via signal processor
        final_decision_text = final_state.get("final_trade_decision", "")
        decision = (
            graph.process_signal(final_decision_text)
            if final_decision_text
            else "N/A"
        )

        # Build structured result (same shape as original _run_analysis)
        invest_debate = final_state.get("investment_debate_state", {})
        risk_debate = final_state.get("risk_debate_state", {})

        result = {
            "ticker": task.ticker,
            "date": task.date,
            "decision": decision,
            "reports": {
                "market_report": final_state.get("market_report", ""),
                "sentiment_report": final_state.get("sentiment_report", ""),
                "news_report": final_state.get("news_report", ""),
                "fundamentals_report": final_state.get("fundamentals_report", ""),
            },
            "investment_debate": {
                "bull_history": invest_debate.get("bull_history", ""),
                "bear_history": invest_debate.get("bear_history", ""),
                "judge_decision": invest_debate.get("judge_decision", ""),
            },
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
            "risk_debate": {
                "aggressive_history": risk_debate.get("aggressive_history", ""),
                "conservative_history": risk_debate.get("conservative_history", ""),
                "neutral_history": risk_debate.get("neutral_history", ""),
                "judge_decision": risk_debate.get("judge_decision", ""),
            },
            "final_trade_decision": final_decision_text,
        }

        task_store.complete_task(task_id, result)
        logger.info("Task %s completed: %s → %s", task_id, task.ticker, decision)

    except Exception as exc:
        logger.error("Task %s failed: %s\n%s", task_id, exc, traceback.format_exc())
        task_store.fail_task(task_id, str(exc))


def _build_task_response(
    task, *, include_result: bool = True
) -> TaskStatusResponse:
    """Convert AnalysisTask dataclass to API response model."""
    result_model = None
    if include_result and task.status == "completed" and task.result:
        r = task.result
        result_model = AnalyzeResponse(
            success=True,
            ticker=r["ticker"],
            date=r["date"],
            decision=r["decision"],
            reports=ReportSection(**r["reports"]),
            investment_debate=DebateSection(**r["investment_debate"]),
            trader_investment_plan=r.get("trader_investment_plan", ""),
            risk_debate=RiskDebateSection(**r["risk_debate"]),
            final_trade_decision=r.get("final_trade_decision", ""),
            timestamp=task.completed_at or "",
        )

    return TaskStatusResponse(
        task_id=task.id,
        ticker=task.ticker,
        date=task.date,
        status=task.status,
        current_stage=task.current_stage,
        current_stage_label=task.current_stage_label,
        progress=task.progress,
        created_at=task.created_at,
        completed_at=task.completed_at,
        result=result_model,
        error=task.error,
    )


# ── Endpoints ────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health() -> dict:
    return {"status": "ok", "service": "TradingAgents API", "version": "0.2.0"}


@app.post(
    "/api/v1/analyze",
    response_model=TaskSubmitResponse,
    status_code=202,
    responses={401: {"model": ErrorResponse}},
)
async def analyze(
    req: AnalyzeRequest,
    _token: str = Depends(verify_token),
) -> TaskSubmitResponse:
    """Submit an async analysis task. Returns 202 with task_id immediately."""
    trade_date = req.date or _default_trade_date()
    ticker = req.ticker.upper()

    task_id = task_store.create_task(ticker, trade_date, req.analysts)
    logger.info(
        "Task %s submitted: ticker=%s date=%s analysts=%s",
        task_id,
        ticker,
        trade_date,
        req.analysts,
    )

    # Launch analysis in background thread via default executor
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None, _run_analysis_with_progress, task_id, req.max_debate_rounds
    )

    return TaskSubmitResponse(
        task_id=task_id,
        status="pending",
        message=f"Analysis task submitted for {ticker}. "
        f"Use GET /api/v1/tasks/{task_id} to check progress.",
    )


@app.get(
    "/api/v1/tasks/{task_id}",
    response_model=TaskStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_task(task_id: str) -> TaskStatusResponse:
    """Query task status and result. No authentication required — task_id is the credential."""
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return _build_task_response(task, include_result=True)


@app.get(
    "/api/v1/tasks",
    response_model=TaskListResponse,
)
async def list_tasks(
    _token: str = Depends(verify_token),
) -> TaskListResponse:
    """List all analysis tasks (summary without result body). Requires authentication."""
    tasks = task_store.list_tasks()
    return TaskListResponse(
        tasks=[_build_task_response(t, include_result=False) for t in tasks],
        total=len(tasks),
    )


@app.post(
    "/api/v1/tasks/{task_id}/cancel",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def cancel_task(task_id: str) -> dict:
    """Cancel a pending or running task. Takes effect between graph nodes."""
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    if not task_store.cancel_task(task_id):
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} cannot be cancelled (status: {task.status}).",
        )

    return {
        "task_id": task_id,
        "status": "cancelling",
        "message": "Cancel signal sent. Task will stop after current node completes.",
    }


# ── Entrypoint ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host=API_HOST, port=API_PORT, log_level="info")

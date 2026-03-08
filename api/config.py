"""Service configuration for TradingAgents API.

Loads settings from environment / .env and produces a ready-to-use
TradingAgents config dict.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# ── Server settings ──────────────────────────────────────────────
API_HOST: str = os.getenv("TRADING_API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("TRADING_API_PORT", "8080"))
ANALYZE_TIMEOUT: int = int(os.getenv("TRADING_ANALYZE_TIMEOUT", "600"))  # seconds

# ── TradingAgents config (mirrors main.py production settings) ───
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402


def build_trading_config() -> dict:
    """Build a TradingAgents config dict from environment variables."""
    cfg = DEFAULT_CONFIG.copy()

    cfg["llm_provider"] = os.getenv("TRADING_LLM_PROVIDER", "openai")
    cfg["backend_url"] = os.getenv(
        "TRADING_BACKEND_URL", "https://api.aitokencloud.com/v1"
    )
    cfg["deep_think_llm"] = os.getenv("TRADING_DEEP_LLM", "glm-5-fp8")
    cfg["quick_think_llm"] = os.getenv("TRADING_QUICK_LLM", "glm-5-fp8")
    cfg["max_debate_rounds"] = int(os.getenv("TRADING_MAX_DEBATE_ROUNDS", "1"))
    cfg["max_risk_discuss_rounds"] = int(
        os.getenv("TRADING_MAX_RISK_ROUNDS", "1")
    )

    cfg["data_vendors"] = {
        "core_stock_apis": os.getenv("TRADING_VENDOR_STOCK", "alpha_vantage"),
        "technical_indicators": os.getenv("TRADING_VENDOR_INDICATORS", "alpha_vantage"),
        "fundamental_data": os.getenv("TRADING_VENDOR_FUNDAMENTALS", "alpha_vantage"),
        "news_data": os.getenv("TRADING_VENDOR_NEWS", "alpha_vantage"),
    }

    return cfg

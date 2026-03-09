---
name: stock-analyst
description: >
  使用 TradingAgents 多智能体框架对股票进行深度分析，产出买入/卖出/持有决策。
  当用户提到股票分析、个股研判、买卖决策、技术面/基本面分析，
  或提及具体股票代码（如 NVDA、AAPL、TSLA）并希望获得投资建议时使用。
  即使用户只是问"XX 股票怎么样"或"该不该买 XX"也应触发。
---

# TradingAgents Stock Analyst

## Overview

This skill calls the **TradingAgents API** — a multi-agent stock analysis service running locally. The API uses an **async task model**: submit a task, poll for progress, and retrieve results when done.

The analysis pipeline involves:

1. **Market Analyst** — technical indicators, price action
2. **Social Analyst** — social media sentiment
3. **News Analyst** — news & insider transactions
4. **Fundamentals Analyst** — balance sheet, cash flow, income statement
5. **Investment Debate** — bull vs bear debate with judge
6. **Risk Assessment** — aggressive vs conservative vs neutral debate
7. **Final Decision** — BUY / SELL / HOLD with reasoning

> **Important**: A single analysis takes **3–10 minutes** due to multiple LLM agent calls. The async API lets you submit and poll rather than blocking.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/analyze` | Bearer Token | Submit analysis task → 202 + task_id |
| `GET` | `/api/v1/tasks/{task_id}` | None | Query task status & result |
| `GET` | `/api/v1/tasks` | Bearer Token | List all tasks |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | None | Cancel a running task |
| `GET` | `/api/v1/health` | None | Health check |

## Configuration

| Variable | Value | Description |
|----------|-------|-------------|
| `API_BASE` | `http://172.16.13.58:8080` | API service base URL |
| `TOKEN` | *(from user or env)* | Bearer token for authentication |

> All URLs below use `${API_BASE}` as prefix. If the server address changes, only update the table above.

## Authentication

Include a Bearer token in the `Authorization` header for endpoints that require it:

```
Authorization: Bearer <token>
```

The token is configured via the `TRADING_API_TOKEN` environment variable on the server. If you don't know the token, ask the user to provide it.

## Request Format

JSON body for `POST /api/v1/analyze`:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ticker` | string | Yes | — | Stock ticker symbol (e.g. `"NVDA"`, `"AAPL"`) |
| `date` | string | No | Previous trading day | Analysis date in `YYYY-MM-DD` format |
| `analysts` | string[] | No | `["market","social","news","fundamentals"]` | Analyst modules to use |
| `max_debate_rounds` | int | No | `1` | Number of debate rounds (1–5) |

## How to Execute

### Step 1: Pre-flight Check

```bash
curl -s ${API_BASE}/api/v1/health
```

Expected: `{"status":"ok","service":"TradingAgents API","version":"0.2.0"}`

If the health check fails, inform the user the API service is not running.

### Step 2: Submit Analysis Task

```bash
TASK_RESPONSE=$(curl -s -X POST ${API_BASE}/api/v1/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"<TICKER>","date":"<YYYY-MM-DD>"}')

TASK_ID=$(echo "$TASK_RESPONSE" | jq -r '.task_id')
echo "Task submitted: $TASK_ID"
```

Expected response (HTTP 202):
```json
{
  "task_id": "a1b2c3d4...",
  "status": "pending",
  "message": "Analysis task submitted for NVDA. Use GET /api/v1/tasks/a1b2c3d4... to check progress."
}
```

### Step 3: Poll for Progress

Poll every 15 seconds until `status` is `"completed"` or `"failed"`:

```bash
while true; do
  RESULT=$(curl -s "${API_BASE}/api/v1/tasks/$TASK_ID")
  STATUS=$(echo "$RESULT" | jq -r '.status')
  STAGE=$(echo "$RESULT" | jq -r '.current_stage_label')
  PROGRESS=$(echo "$RESULT" | jq -r '.progress')

  echo "[$STATUS] Progress: ${PROGRESS} — $STAGE"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    break
  fi
  sleep 15
done

echo "$RESULT" | jq '.'
```

### Step 4 (Optional): Cancel a Task

```bash
curl -s -X POST "${API_BASE}/api/v1/tasks/$TASK_ID/cancel"
```

> Note: Cancellation takes effect between graph nodes. The currently executing LLM call will finish before the task stops.

## Progress Stages

During polling, the `current_stage_label` field shows which phase is active:

| Progress | Stage Label |
|----------|-------------|
| 1/6 | 📈 市场技术分析 |
| 2/6 | 💬 社交媒体情绪 |
| 3/6 | 📰 新闻分析 |
| 4/6 | 📋 基本面分析 |
| 5/6 | ⚖️ 投资辩论与交易计划 |
| 6/6 | 🛡️ 风险评估与最终决策 |

The denominator adjusts dynamically based on selected analysts.

## Response Parsing

When `status` is `"completed"`, the `result` field contains the full analysis:

```json
{
  "task_id": "...",
  "status": "completed",
  "progress": 1.0,
  "result": {
    "success": true,
    "ticker": "NVDA",
    "date": "2024-05-10",
    "decision": "BUY",
    "reports": {
      "market_report": "...",
      "sentiment_report": "...",
      "news_report": "...",
      "fundamentals_report": "..."
    },
    "investment_debate": {
      "bull_history": "...",
      "bear_history": "...",
      "judge_decision": "..."
    },
    "trader_investment_plan": "...",
    "risk_debate": {
      "aggressive_history": "...",
      "conservative_history": "...",
      "neutral_history": "...",
      "judge_decision": "..."
    },
    "final_trade_decision": "...",
    "timestamp": "2024-05-10T12:00:00+00:00"
  }
}
```

## Report Formatting

After receiving a completed response, format the output as a Markdown report for the user using this template:

```markdown
# 📊 {ticker} 股票分析报告

**分析日期**: {date}
**最终决策**: **{decision}** 🟢/🔴/🟡

---

## 📈 市场技术分析
{reports.market_report}

## 💬 社交媒体情绪
{reports.sentiment_report}

## 📰 新闻与内部交易
{reports.news_report}

## 📋 基本面分析
{reports.fundamentals_report}

---

## ⚖️ 投资辩论

### 🐂 看多观点
{investment_debate.bull_history}

### 🐻 看空观点
{investment_debate.bear_history}

### 🏛️ 裁判决定
{investment_debate.judge_decision}

---

## 📝 交易员投资计划
{trader_investment_plan}

---

## 🛡️ 风险评估辩论

### 🔥 激进派
{risk_debate.aggressive_history}

### 🛡️ 保守派
{risk_debate.conservative_history}

### ⚖️ 中立派
{risk_debate.neutral_history}

### 裁判决定
{risk_debate.judge_decision}

---

## 🎯 最终交易决策
{final_trade_decision}

---

> ⚠️ **免责声明**: 本分析由 AI 多智能体系统生成，仅供参考，不构成投资建议。投资有风险，决策需谨慎。
```

## Error Handling

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 202 | Task accepted | Extract task_id and start polling |
| 200 | Task status returned | Check status field |
| 401 | Unauthorized | Token invalid — ask user for correct token |
| 404 | Task not found | Invalid task_id |
| 409 | Conflict | Task cannot be cancelled (already completed/failed) |
| 422 | Validation Error | Check request parameters |

If `status` is `"failed"` in the task response, display the `error` field.

## Usage Examples

User says: "帮我分析一下英伟达"
→ Submit with `{"ticker": "NVDA"}`, poll until complete

User says: "AAPL 该买吗？用 2024-01-15 的数据"
→ Submit with `{"ticker": "AAPL", "date": "2024-01-15"}`, poll until complete

User says: "只看技术面分析 TSLA"
→ Submit with `{"ticker": "TSLA", "analysts": ["market"]}`, poll until complete

## Disclaimer

All analysis results are generated by an AI multi-agent system and are for **reference only**. They do not constitute investment advice. Users should conduct their own research and exercise independent judgment before making any investment decisions.

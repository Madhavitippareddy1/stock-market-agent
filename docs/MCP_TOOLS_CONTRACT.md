# Shared MCP Tools Contract

This project connects to a common MCP server used by multiple projects. The MCP
server should expose the tools below for this stock market application.

AWS shared MCP server endpoint:

```text
http://internal-dstrmaysam-shared-mcp-alb-748190876.eu-west-2.elb.amazonaws.com/sse
```

## Stock tools

### `get_stock_quote`

Gets one company/ticker price.

### `get_company_profile`

Gets company name, sector, industry, and market cap.

### `compare_stocks`

Compares two or more requested stocks.

### `suggest_best_stock_of_month`

Ranks a configured stock universe by one-month price performance and returns
top candidates with risks and disclaimer.

Input:

```json
{
  "question": "suggest me the best stock of this month"
}
```

### `stock_research`

Input:

```json
{
  "question": "compare Apple and Meta"
}
```

Output:

```json
{
  "answer": "Apple and Meta comparison...",
  "sources": ["Yahoo Finance"],
  "tickers": ["AAPL", "META"]
}
```

Expected behavior:

- Resolve company names to tickers.
- Return only requested stocks.
- Do not default to all top stocks unless the user asks for a dashboard or top list.

## RAG tools

### `search_financial_reports`

Searches stored financial reports for one ticker/company.

### `summarize_financial_report`

Summarizes a stored annual, quarterly, or half-yearly report.

### `financial_report_research`

Input:

```json
{
  "question": "analyse this annual report",
  "uploaded_filename": "AAPL-annual-report.pdf"
}
```

Output:

```json
{
  "answer": "Financial report summary...",
  "sources": ["s3://bucket/financial-reports/AAPL/annual/2025/report.pdf"]
}
```

Expected behavior:

- If an uploaded document is provided, analyze that document first.
- Use S3/OpenSearch only when no upload is provided or when the user asks for stored reports.
- Keep ticker filters strict.

## User tools

### `get_user_profile`

Gets user risk profile and investment goal.

### `get_user_watchlist`

Gets the user's saved stock watchlist.

### `user_context`

Input:

```json
{
  "user_id": "demo-user",
  "question": "show my watchlist"
}
```

Output:

```json
{
  "answer": "Your watchlist contains AAPL, MSFT, and NVDA.",
  "risk_profile": "balanced",
  "watchlist": ["AAPL", "MSFT", "NVDA"]
}
```

## Portfolio tools

### `get_portfolio_holdings`

Gets raw holdings for a user.

### `calculate_portfolio_risk`

Calculates concentration risk alerts.

### `portfolio_analysis`

Input:

```json
{
  "user_id": "demo-user",
  "question": "analyze my portfolio"
}
```

Output:

```json
{
  "answer": "Your portfolio is concentrated in technology...",
  "total_value": 25000,
  "risk_alerts": ["AAPL is 42% of the portfolio."]
}
```

Expected behavior:

- Calculate portfolio value.
- Calculate gain/loss.
- Generate concentration risk alerts.
- Use current prices from the stock tool.

## Future investment tool

### `investment_research`

Input:

```json
{
  "user_id": "demo-user",
  "question": "should I buy PepsiCo?"
}
```

Output:

```json
{
  "answer": "PepsiCo may suit a defensive portfolio, but valuation and growth should be reviewed...",
  "disclaimer": "This is educational research, not financial advice."
}
```

This should be added after User Agent and Portfolio Agent are stable.

## Agent-to-tool mapping

| Agent | MCP tools |
| --- | --- |
| Stock Agent | `get_stock_quote`, `get_company_profile`, `compare_stocks`, `suggest_best_stock_of_month`, `stock_research` |
| RAG Agent | `search_financial_reports`, `summarize_financial_report`, `financial_report_research` |
| User Agent | `get_user_profile`, `get_user_watchlist`, `user_context` |
| Portfolio Agent | `get_portfolio_holdings`, `calculate_portfolio_risk`, `portfolio_analysis` |
| Investment Agent | `investment_research`, plus stock/user/portfolio tools |

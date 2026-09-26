# Stock Screeners — 5 proven strategies

Five research screens in one app, built from the academic literature. **No API keys needed.**

- **Prices:** Yahoo Finance public chart API
- **Fundamentals:** SEC EDGAR companyfacts (TTM revenue, gross profit, earnings, cash flow, assets, liabilities)

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## The strategies

| # | Strategy | Idea | Paper |
|---|----------|------|-------|
| 🌱 | Undiscovered Growth | Strong growers (rev +10%+, profitable) still 10–45% below highs; small caps score higher | — |
| 📉 | Fallen Quality | Quality stocks down ≥25% with fundamentals intact | — |
| 💰 | Gross Profitability | Top ~100 by gross profit ÷ total assets, annual rebalance | Novy-Marx (2013) |
| 🚀 | Momentum | Top ~100 by 12-month return skipping the last month, monthly rebalance | Jegadeesh & Titman (1993) |
| ⚖️ | Profitable Value | 30 cheapest (B/M, E/P, FCF yield) among profitable ex-financials, annual rebalance | Greenblatt (2005) / Fama-French (2015) |

Pick a strategy at the top. Each has:

- **Watchlist tab** — the latest run with 🟢/🟡 news verdicts and one-line notes (newer strategies ship unreviewed).
- **Run fresh screen tab** — re-run the whole S&P 500 yourself with adjustable filters, export to CSV.
- **Backtest tab** — point-in-time monthly backtest vs SPY on bundled 2017→2026 history: fundamentals as actually filed by each rebalance date, equal weight, long only, no costs. Current S&P 500 constituents only (survivorship bias flatters results).
- **Near misses** — names excluded and why.
- **How it works** — the methodology plus the paper.

First run takes ~10 minutes (SEC EDGAR is polite-rate-limited); fundamentals are cached on disk so re-runs are fast.

## Notes

- Value and profitability are negatively correlated — the strategies diversify each other.
- Momentum crashes occasionally (2009); size it accordingly.
- Fresh runs show unreviewed names — do your own news check before taking any of them seriously.

Research screens, not investment advice.

# Stock Screeners — 6 proven strategies

Six research screens in one app, built from the academic literature. **No API keys needed.**

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
| 🎯 | Composite | 30 stocks ranking best on value + quality + momentum + growth combined, ex-financials | — |

Pick a strategy at the top. Each has:

- **Watchlist tab** — the latest run with 🟢/🟡 news verdicts and one-line notes (newer strategies ship unreviewed).
- **Run fresh screen tab** — re-run the whole universe yourself with adjustable filters, export to CSV.
- **Backtest tab** — point-in-time monthly backtest vs SPY on bundled 2017→2026 history: fundamentals as actually filed by each rebalance date, equal weight, long only, no costs. Current-constituent survivorship bias flatters results.
- **Universe selector** — S&P 500 (503 stocks) or S&P 1500 (S&P 500 + 400 midcap + 600 smallcap, 1,506 stocks) — built by `build_universe_1500.py` from Wikipedia + SEC EDGAR CIKs. Saved watchlists ship for the S&P 500; on the S&P 1500 the Run-fresh-screen tab covers all six strategies.
- **Near misses** — names excluded and why.
- **How it works** — the methodology plus the paper.

First run takes ~10 minutes (SEC EDGAR is polite-rate-limited); fundamentals are cached on disk so re-runs are fast.

## Notes

- Value and profitability are negatively correlated — the strategies diversify each other.
- Momentum crashes occasionally (2009); size it accordingly.
- Fresh runs show unreviewed names — do your own news check before taking any of them seriously.

Research screens, not investment advice.

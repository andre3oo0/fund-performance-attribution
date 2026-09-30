# Fund Performance Measurement and Attribution

**Did the fund's manager add value over simply buying the index, after fees and allowing for risk, and
which decisions produced the result?**

This is the question a performance analyst answers for every fund, every month. A fund's quarterly report
may say it beat the market, but that claim depends on how returns were measured, which benchmark was used,
and whether the benchmark's own data can be trusted. This project rebuilds a fund's performance from its
transactions, checks the benchmark, and splits the result into the decisions that produced it.

The fund is **fictional**: the Hadeda Equity Fund, a South African equity fund launched with R50 million on
3 January 2022, with synthetic investors and a set of investment rules fixed before any result was computed
([config/fund.yaml](config/fund.yaml)). Everything it is measured with is real: JSE share prices and
dividends, the FTSE/JSE Top 40 through the Satrix 40 fund, and the South African Reserve Bank's Treasury
bill rate.

## Status

Work in progress, started 30 September 2026. There are no findings yet. The plan, with the checks already
made and the reasoning behind each decision, is in [docs/plan.md](docs/plan.md).

Already found while planning: Yahoo's adjusted close for the Satrix 40 fund leaves out its distributions,
and until October 2024 Yahoo lists most distributions two or three times. A benchmark taken from Yahoo at
face value would be wrong in both directions, so here it is rebuilt and checked against Satrix's own
notices.

## Skills

| Area | What it involves here |
|---|---|
| Performance measurement | Time-weighted and money-weighted returns, NAV per unit, gross and net of fees |
| Attribution | Brinson-Fachler allocation and selection effects by sector, contribution by holding |
| Risk | Volatility, tracking error, information ratio, Sharpe ratio, drawdown |
| Fund accounting | Unit pricing, investor subscriptions and redemptions, dividends, fee accrual |
| Data quality | Benchmark reconstruction, reconciliation against source documents, flagging bad data |
| Reporting | Monthly Excel tracker and a quarterly client report pack |

## Related projects

1. [jse-share-price-reconciliation](https://github.com/andre3oo0/jse-share-price-reconciliation): the daily
   price checks behind the fund's valuation
2. This project: the fund's performance and what drove it
3. Mandate compliance monitoring: checking the fund against its investment limits (not started)

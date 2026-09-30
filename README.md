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

Work in progress, started 30 September 2026. The fund's performance has not been measured yet. The plan,
with the reasoning behind each decision, is in [docs/plan.md](docs/plan.md).

The benchmark, the Top 40 index and the Treasury bill rate are now collected and checked
([docs/data.md](docs/data.md)). Before any performance figure, the checks found three problems a
benchmark taken at face value would carry:

- **Distributions counted up to three times.** Until October 2024, Yahoo lists each quarterly Satrix 40
  distribution two or three times. The amounts match Satrix's own figures, but summing them as listed
  would count two to three times the real income. Yahoo's adjusted close ignores them altogether.
- **A price 100 times too small.** Satrix 40 closed at R0.84 on 25 April 2025, against R84.12 the day
  before.
- **A zero interest rate.** The Reserve Bank's Treasury bill series reads 0.00% for five days in February
  2022, which would understate the risk-free return used to judge the fund's risk-adjusted performance.

Every fact the fund's rules rely on is checked against a primary source in [docs/sources.md](docs/sources.md).

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

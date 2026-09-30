# Plan: fund performance measurement and attribution

Agreed 30 September 2026. The fund is fictional; the prices, dividends, index and interest rates it is
measured with are real. This is the second of three projects built around the same fund; the first,
[jse-share-price-reconciliation](https://github.com/andre3oo0/jse-share-price-reconciliation), checks the
prices it is valued with.

## 1. The problem, framed as the job

A performance analyst at a fund administrator or asset manager answers one question every month and every
quarter: **did the manager add value over simply buying the index, after fees and after allowing for risk,
and which decisions produced the result?** Then they send the client a report pack that says so plainly.

The README reports what the rebuilt returns, the checked benchmark and the attribution show. Findings come
from the data once the fund's book is built; none are assumed here.

## 2. The fund (fictional, shared by all three projects)

| | |
|---|---|
| Name | **Hadeda Equity Fund (fictional)**; no manager, scheme, portfolio or FSP of that name on the FSCA register, 30 Sep 2026 (section 4) |
| Type | South African general equity fund, rand-denominated, long only, no borrowing, no derivatives |
| Inception | Monday 3 January 2022 (to confirm as a trading day in the JSE calendar), seed R50 million |
| Units | Priced daily at NAV per unit, launched at R10.00 (NAV lets investors' flows buy and sell units, which is what makes the return time-weighted) |
| Benchmark | FTSE/JSE Top 40, measured through Satrix 40's total return (see section 4) |
| Universe | Shares in the Top 40 on the decision date (point-in-time, so no survivorship bias) |
| Fees | 1.00% a year management fee, accrued daily, paid monthly; brokerage and costs 0.35% of trade value (illustrative, as in project 1) |
| Cash | Target 3%, band 1% to 5%; earns the 91-day T-bill rate (an assumption, stated) |
| Investor flows | Synthetic monthly subscriptions and redemptions from a fixed seed, including one large redemption, so the gap between time-weighted and money-weighted return is visible |
| Dividends | Real, from Yahoo's dividend column, recognised on the ex-date, cash received five trading days later (assumption, stated); dividend withholding tax treatment for a unit trust to be verified before use |

### Investment rules, fixed before any result is computed

1. Rebalance quarterly, on the first trading day after each quarterly Top 40 review takes effect.
2. Rank the point-in-time Top 40 by 12-month price return excluding the latest month (momentum), using only
   closes available on the decision date.
3. Hold the top 20, equal-weighted (4.85% each at a 3% cash target).
4. Between rebalances, invest net subscriptions pro rata to current weights; fund redemptions by selling pro
   rata; bring cash back into its band at month-end only.
5. Mandate limit: no share above 10% of the fund. Drift above the limit is trimmed at the next rebalance and
   logged, which gives project 3 real breaches to find.

The rules are committed to `config/fund.yaml` **before** any return code exists; the commit date in git
history is the evidence that results did not shape the rules. Equal weighting against a cap-weighted
benchmark creates large, explainable sector bets (for example underweight Naspers and Prosus), which gives
the attribution something real to find.

## 3. Questions the output answers (`python -m src.answers`)

1. Did the fund beat the Top 40 after fees: since inception, and over one and three years?
2. Was the extra return worth the extra risk (information ratio, Sharpe ratio against the benchmark's)?
3. Which decisions produced the result: sector allocation or stock selection?
4. Which holdings added most and cost most?
5. What did fees and trading costs cost the investor, in percentage points and rand?
6. Why did the average investor's return differ from the fund's (money-weighted against time-weighted)?
7. What was the worst fall from a peak, and how long did recovery take, for the fund and the benchmark?
8. How much would the answers change if the benchmark data had been taken at face value (duplicated
   distributions, bad prices)?

Each answer gives its evidence: figures, period and the query or tab it came from.

## 4. Checks made before building (30 September 2026)

| Question | Finding | Evidence |
|---|---|---|
| Top 40 benchmark on Yahoo | `STX40.JO` (Satrix 40) has daily closes and distributions from before inception; `^J200.JO` has the Top 40 **price** index level (no dividends) | yfinance probe, 1 Dec 2021 to 28 Sep 2026, 1,203 sessions each |
| Does Yahoo's adjusted close include distributions? | **No.** Adj Close over Close moved only from 0.9973 to 1.0 over nearly five years, while Satrix paid roughly quarterly distributions | Same probe |
| Are Yahoo's distributions clean? | **No.** Until October 2024 most distributions appear two or three times (for example 20.71c on 31 Dec 2021, 19 Jan and 24 Jan 2022); from 2025 once each. Summing them as received would overstate the benchmark | 33 dividend rows for about 19 quarters |
| Satrix 40 against the price index | Price return 59.1% for STX40 against 56.4% for `^J200.JO`, 1 Dec 2021 to 28 Sep 2026; unexplained, to investigate | Same probe |
| Risk-free rate | SARB publishes the 91-day T-bill tender rate (series `MMRD203A`) through a public web API, history from 3 Jan 2022, latest 6.93% on 28 Sep 2026 | `custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations/MMRD203A/{from}/{to}` |
| Benchmark constituents and weights | Satrix publishes the full Top 40 constituent list with weights at each quarterly rebalance as a JSE SENS notice (for example 26 Sep 2024) | SENS PDFs return 403 to scripts from this laptop; retrieve by browser or from the runner (phase 0) |
| Fund name against the FSCA register | No match for "Hadeda" among CIS managers or schemes (local and foreign), in the full list of managers and portfolios (9,931 lines; control: "Satrix 40 Portfolio" found; 230 lines contain "Equity Fund"), or among FSPs (control: "Satrix" returns 2) | www2.fsca.co.za CIS search (`PRGNAME=Search_Mancos`), its "download all Manco's and Portfolios" list read in the browser, and the FSP search (`Search_FSP.htm`), via fsca.co.za Regulated Entities |
| Project 1's landed Yahoo data | The 5-year backfill snapshot (29 Sep 2026) includes the `dividends` column for all 107 shares | Project 1's private snapshot of 29 Sep 2026 |

Consequence: **the benchmark is built, not downloaded.** Total return = STX40 close with each distribution
reinvested on its ex-date, after de-duplicating Yahoo's rows and checking each distribution against Satrix's
own notices. The duplicates are flagged, never silently dropped, and question 8 reports what they would have
done to the comparison.

## 5. Methods

| Measure | Method |
|---|---|
| Fund return | Time-weighted, daily, from NAV per unit (valuation before flows), chain-linked to months, quarters and years; annualised only for periods over one year |
| Gross and net | Net from NAV per unit; gross adds back the daily fee accrual |
| Investor return | Money-weighted (IRR) on the fund's net flows, for question 6 |
| Benchmark | Satrix 40 total return (section 4); `^J200.JO` plus reconstructed dividends as a cross-check |
| Contribution | Each holding's weight at the start of the day times its return, linked over the period |
| Attribution | Brinson-Fachler by sector (allocation, selection, interaction), monthly, with cash as its own sector; linked across months with Carino's method so the effects add up exactly to the period's active return |
| Benchmark sectors | Point-in-time constituents and weights from Satrix's quarterly SENS notices, drifted daily with prices; the rebuilt benchmark return is reconciled against STX40's actual return and the gap is reported |
| Risk | Annualised volatility, tracking error, information ratio, Sharpe and Sortino (91-day T-bill), beta, up and down capture, maximum drawdown and recovery time; 36-month rolling figures from December 2024 |
| Presentation | Laid out in the spirit of GIPS (periods, gross and net, benchmark beside every figure); explicitly not a GIPS compliance claim |

Sector classification: project 1's sectors are approximate. Attribution depends on them, so phase 0b checks
each Top 40 member's ICB industry against a public primary source (JSE company pages or the company's own
filings) and records the source; anything unverifiable is labelled.

## 6. Data and repositories

```
private data repository (project 1's)             landed Yahoo snapshots, never public
        |
        | read-only token, a secret of this repository
        v
project 2, public repository                       code, fund rules, synthetic ledger, derived figures
        lands its own small inputs: STX40 and ^J200 (Yahoo), T-bill (SARB), Top 40 notices (SENS)
```

- Yahoo only; no EODHD, so project 1's quota is untouched.
- Land everything exactly as received, fingerprinted; flag problems, never repair them; everything
  downstream rebuilds with one command (same pattern as project 1).
- Published: returns, weights, attribution, risk figures, the synthetic ledger (trades at real closes, as
  project 1 already publishes). Not published: raw vendor price files or index levels in bulk.
- Top 40 members missing from project 1's 107-share universe are added there first (Yahoo only), so price
  checks cover every share the fund and benchmark hold.

## 7. Outputs

| Output | Form |
|---|---|
| Answers | `python -m src.answers`, eight questions with evidence, also in each run summary |
| Monthly tracker | Excel: summary, monthly returns, benchmark, attribution, contribution, risk, flows, fees, assumptions, definitions. Arial, figures as formulas over the detail tabs, percentages as fractions, recalculated in LibreOffice in CI with zero errors, headline figures cross-checked against the database |
| Quarterly report pack | Word document built in Python, converted to PDF by LibreOffice on the runner: commentary, performance table, attribution, top contributors and detractors, risk, fees; styled like a client pack |
| Dashboard | A static page on GitHub Pages, derived figures only, refreshed monthly |

## 8. Tests that matter

Planted errors the code must catch or get right:
- Textbook time-weighted return cases with flows (worked answers checked by hand in the test file).
- A large subscription on a flat day: return must be zero, not a jump.
- An ex-dividend price drop with the dividend booked: return must not show a loss.
- A distribution entered twice, a 100x price, a missing close, a fee accrued twice: each flagged.
- Attribution identity: allocation plus selection plus interaction equals active return every month, and the
  Carino-linked effects equal the period's active return.
- Look-ahead guard: a decision-date ranking must fail if it touches a later close.
- Traps that must not raise an alarm: a real price halving on a share split, a genuine zero-return day, a
  month with no flows.

## 9. Phases

| Phase | Work | Done when |
|---|---|---|
| 0a. Project 1 first | Move project 1's price snapshots, run logs and reports to a private repository, since the vendors' terms restrict republishing | Done 30 September 2026 |
| 0b. Verify and decide | FSCA register check on the fund name; repository name; fetch Satrix SENS notices from Dec 2021 to Sep 2026; verify ICB sectors; check Satrix distributions against Yahoo; dividend tax treatment; confirm the inception date in the calendar | Each answer recorded with its source in `docs/sources.md`; plan finalised as `docs/plan.md` |
| 1. Fund definition | Create this repository; commit `config/fund.yaml` (mandate and rules) and README skeleton | Rules committed before any return code |
| 2. Data | Land STX40, `^J200.JO`, T-bill, constituent notices; staging; data quality flags (duplicate distributions, unit anomalies, gaps) | Flags visible in a data quality view; tests pass |
| 3. Fund book | Simulate decisions, trades, flows, dividends, fees and cash day by day; daily NAV and unit price; ledger | NAV reconciles to cash plus holdings every day |
| 4. Returns and risk | TWR, MWR, benchmark total return, risk measures | Planted-error suite passes |
| 5. Attribution | Contribution by holding; Brinson-Fachler by sector with Carino linking; benchmark rebuild reconciled to STX40 | Identity tests pass; rebuild gap reported |
| 6. Answers and tracker | `src.answers`; Excel tracker with CI recalculation and cross-check | Zero formula errors; figures match the database |
| 7. Report pack and dashboard | Quarterly pack (Word and PDF), GitHub Pages dashboard | Q3 2026 pack produced |
| 8. Schedule | Monthly workflow on the third trading day; manual dry run first | Dry run green, then first scheduled run |
| 9. Write-up | README findings with numbers, `docs/findings.md`; regenerate project 1's holdings fixture from the fund's book, keeping the planted breaks | README reads problem, findings, meaning, method |

## 10. Decisions made

1. **Fund name:** Hadeda Equity Fund (fictional), clear on the FSCA register on 30 September 2026. A real
   fund's name is ruled out: it would attribute invented performance to a real, regulated product.
2. **Repository name:** `fund-performance-attribution`, the industry's own words for the work.
3. **Strategy:** equal-weighted momentum, simple to explain, and it takes real sector and stock bets for the
   attribution to explain. A value or quality screen was the alternative.

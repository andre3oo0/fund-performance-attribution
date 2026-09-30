# Sources and verified facts

Every fact the fund's rules or the measurement depend on, with where it was checked. Checked on
30 September 2026 unless stated. Anything not confirmed from a primary source says so.

## Market data

| Data | Source | Notes |
|---|---|---|
| Benchmark: Satrix 40 (STX40) closes and distributions | Yahoo Finance, `STX40.JO`, landed daily from 1 Dec 2020 | Prices in cents (Yahoo reports `ZAc`). Adjusted close does **not** include distributions, so it is not used |
| FTSE/JSE Top 40 price index | Yahoo Finance, `^J200.JO` | Index points, no dividends; a cross-check only |
| Stand-ins for missing JSE history | Yahoo Finance: `CFR.SW` (Richemont, SIX, francs), `BHP.L` (BHP, LSE, pence), `CHFZAR=X`, `GBPZAR=X` | Returns only, until each JSE series begins; checked against Satrix's year-end prices ([data](data.md)) |
| Risk-free rate: 91-day Treasury bill tender rate | SARB web API, series `MMRD203A`: `custom.resbank.co.za/SarbWebApi/WebIndicators/Shared/GetTimeseriesObservations/MMRD203A/{from}/{to}` | Published for each trading day; the tender itself is weekly |
| Satrix 40 costs | Satrix minimum disclosure document, 31 Aug 2026: https://satrix.co.za/fund/mdd/STX40 | TER 0.10% (one and three years); management fee 0.09%, transaction costs 0.03% |

## Satrix 40 distributions, checked against Satrix's own figures

Satrix's annual financial statements (note 6) and distribution announcements give the same amounts as Yahoo
for every quarter from Q4 2021 to Q4 2025; Q1 and Q2 2026 (96.62c, 98.31c) are confirmed by the minimum
disclosure document only.

- Annual financial statements: 2023 https://satrix.co.za/media/88188, 2024 https://satrix.co.za/media/90845,
  2025 https://satrix.co.za/media/92341
- Announcements read on Sharenet's SENS display: Q4 2021 (released 13 Jan 2022), Q3 2024 (10 Oct 2024),
  Q1 2025 (9 Apr 2025)

Which of Yahoo's repeated rows is the ex-date: where Satrix states the ex-date, it matches Yahoo's
mid-month row, not the quarter-end row.

| Quarter | Amount | Satrix: ex / record / paid | Yahoo rows |
|---|---|---|---|
| Q4 2021 | 20.71c | 19 Jan / 21 Jan / 26 Jan 2022 | 31 Dec 2021, **19 Jan 2022**, 24 Jan 2022 |
| Q3 2024 | 69.79c | 16 Oct / 18 Oct / 21 Oct 2024 | 30 Sep 2024, **16 Oct 2024** |
| Q1 2025 | 32.72c | 15 Apr / 17 Apr / 22 Apr 2025 | **15 Apr 2025** only |

Yahoo's quarter-end rows match the quarter Satrix names each distribution by ("declared 31 March" in the
financial statements is that label, not a declaration date). Yahoo's third rows (for example 24 Jan 2022)
match neither the record date nor the payment date: unexplained.

## Benchmark constituents and weights

- Satrix announces each quarterly rebalance on JSE SENS with the full list of constituents and weights.
  The JSE's own SENS PDF site sits behind a bot-detection challenge, which this project does not work
  around. One notice has been read in full, through Sharenet's SENS display (March 2025: changes applied
  after the close on Thursday 20 March, effective Monday 24 March 2025; 42 code rows, 40 companies, weights
  before and after, no sector column).
- Satrix's annual financial statements (note 3) list every holding at 31 December, with shares, price,
  fair value in rand and percentage of the portfolio, for that year and the one before. Four statements
  cover every year-end from 2020 to 2025: 2021 https://satrix.co.za/media/63515 (2021 and 2020), and the
  2023, 2024 and 2025 statements above. They are landed as received and parsed on every rebuild
  (`src/sources/satrix.py`); each year's holdings add up to the stated total to within R2 of rounding.
- 47 names appear across the six year-ends, 41 holdings in each, mapped to 47 JSE codes in
  `config/securities.yaml`. Two names change meaning over time: Satrix prints "BHP Group plc" both before
  BHP unified its listings in January 2022 and after (mapped to two codes by year, the date unverified),
  and its 2025 statement calls Valterra Platinum "Valterra Partners LLC".
- Unresolved: the quarterly changes between year-ends, from Satrix's rebalance notices.

## Sector classification (ICB)

- No free, public, per-company list of ICB classifications was found. The JSE's sector pages are behind
  the same bot-detection challenge; Sharenet's sector lookup is paid.
- FTSE Russell's free Top 40 factsheet gives the ICB supersector breakdown (count and weight of the index)
  and the ICB sector of the ten largest members:
  https://research.ftserussell.com/Analytics/FactSheets/Home/DownloadSingleIssue?openfile=open&issueName=J200
- Satrix's financial statements give the fund's holdings by ICB industry, in rand, for each year-end.
- **Each company's ICB industry is proven by matching those totals.** With the industries in
  `config/securities.yaml`, the holdings add up to Satrix's printed total for every industry at every
  year-end from 2021 to 2025, to within R2 of rounding (the check `dq_statement_industry` re-proves this on
  every rebuild). First guesses that failed and were corrected by the totals: Remgro is Financials, not
  Industrials; Exxaro is Energy, not Basic Materials; MultiChoice is Telecommunications, not Consumer
  Discretionary.
- Satrix's 2020 figures use the ICB structure before its 2021 revision (Consumer Goods and Consumer
  Services), so they are not compared; the fund starts in 2022 and does not need them.
- Limit: matching totals proves the industries add up, not that no two companies of equal value are
  swapped. Across five year-ends and 11 industries that is very unlikely, but it is not a published list.

## Fund rules

| Rule | Source |
|---|---|
| Inception, Monday 3 January 2022, is a trading day | Public Holidays Act 36 of 1994, s2(1), moves a holiday only from a Sunday; 1 January 2022 was a Saturday: https://www.gov.za/sites/default/files/gcis_document/201409/act36of1994.pdf. The project's JSE calendar agrees |
| Single-share limit | Board Notice 90 of 2014 (CISCA), para 3(1)(a): 5% of the portfolio for a share with market capitalisation under R2 billion, 10% at R2 billion or more, or up to 120% of the share's index weight capped at 20% against the overall market index; para 3(1)(b) allows a passive breach but no further buying: https://www.gov.za/sites/default/files/gcis_document/201409/37895bn90.pdf. Later amendments (an FSCA notice of 2024 was referenced) are **unverified** |
| Dividends tax on the fund's dividend income | Not withheld from the fund: a collective investment scheme is a regulated intermediary (Income Tax Act s64G(2)(c)); dividends passed to investors within 12 months accrue to them (s25BA) and tax is withheld then, unless the investor is exempt. SARS Comprehensive Guide to Dividends Tax, issue 5, sections 4.1.11 and 5.4: https://www.sars.gov.za/wp-content/uploads/Ops/Guides/LAPD-IT-G19-Comprehensive-Guide-to-Dividends-Tax.pdf. The former exemption in s64F(1)(k) was deleted by the Taxation Laws Amendment Act 23 of 2018 |
| Fund name | No manager, scheme, portfolio or financial services provider named "Hadeda" on the FSCA register (CIS search, full list of managers and portfolios, FSP search) |

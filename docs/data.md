# Data: what is collected, how it is kept, and what the checks found

## How it runs

The `land` workflow in this repository is called from a private data repository (`jse-price-data`, shared
with [jse-share-price-reconciliation](https://github.com/andre3oo0/jse-share-price-reconciliation)),
because the vendors' terms restrict republishing their data. The run, its logs and the landed files stay
private; this repository publishes code and derived figures only. The workflow refuses to run from a
public repository.

Each run:

1. Runs the tests, then re-checks every file already landed against its fingerprint.
2. Collects each source (`python -m src.ingest`) and lands it exactly as received: gzipped, with a manifest
   holding the fetch time, row counts, per-symbol outcome and a SHA-256 fingerprint. A day already landed
   is never replaced except by an explicit `--refetch`.
3. Keeps only completed sessions: before 17:30 SAST on the snapshot date, that day's bar is left out.
4. Rebuilds the warehouse (`python -m src.rebuild`) and prints the data quality checks (`python -m src.dq`).

Locally, with access to the private repository:

```bash
pip install -r requirements.txt
git clone https://github.com/andre3oo0/jse-price-data.git data/landing
python -m src.rebuild
python -m src.dq
```

## What is collected

| Source | Series | From | Landed 30 Sep 2026 |
|---|---|---|---|
| Yahoo Finance | Satrix 40 (`STX40.JO`), cents | 1 Dec 2020 | 1,452 daily bars to 28 Sep 2026 |
| Yahoo Finance | FTSE/JSE Top 40 price index (`^J200.JO`), points | 1 Dec 2020 | 1,443 daily bars to 29 Sep 2026 |
| SARB | 91-day T-bill tender rate (`MMRD203A`), percent | 1 Dec 2020 | 1,468 daily values to 28 Sep 2026 |
| Satrix | Satrix 40 annual financial statements, PDF | Year-ends 2020 to 2025 | Four statements, landed once each under their year-end |

Satrix's statements are landed once each under their year-end (`satrix/2025-12-31/`), since a published
statement does not change. The Top 40 member shares follow (44 of the 47 codes have Yahoo prices).

## The checks

Each check is a view in [sql/dq.sql](../sql/dq.sql). Problems are flagged, never repaired; the step that
uses the data decides what to do with each, and says so.

| Check | Rule |
|---|---|
| Repeated distribution | The same amount for the same instrument within 45 days; every row of the cluster is flagged |
| Unit error | A close 20 times or more away from both neighbours (one day), or from the previous close without returning (a step change) |
| Unknown unit | A unit other than cents or rands, which cannot be converted |
| Closed-day price | A bar dated on a weekend or JSE holiday, from the calendar built from the Public Holidays Act |
| Missing session | A trading day inside a series' own date range with no bar |
| Frozen price | Five or more sessions at exactly the same close |
| Rate problem | More than ten days between published rates, or a rate at or below zero, or 30% and above |
| Unmapped holding | A name in Satrix's statement with no JSE code for that year |
| Statement total | A statement's holdings that do not add up to its stated total (R5 allowed for rounding) |
| Industry total | Holdings grouped by each company's ICB industry that differ from Satrix's industry table (2021 onwards) |
| Restated holding | The same year-end printed with different shares or value in two statements |
| Year-end price | Satrix's year-end price against Yahoo's close on the last trading day of the year (0.1% allowed), or no Yahoo price at all |

The tests plant each error and check it is found, and plant traps that must not raise an alarm: a quarterly
distribution of a repeated amount, a share split, a public holiday, four frozen sessions, a weekend in the
rate series, a year-end on a Saturday, a name that maps to different codes in different years, and 2020's
old industry structure.

## What the checks found on the first landing (30 September 2026)

**Satrix 40's distributions are listed up to three times.** 36 of Yahoo's 43 distribution rows belong to
16 repeated clusters, every quarter from Q4 2020 to Q3 2024; from Q4 2024 each appears once. The amounts
all match Satrix's own figures, and where Satrix states an ex-date it is Yahoo's mid-month row
([sources](sources.md)). Summing the rows as received would count two to three times the benchmark's real income
for those quarters.

**One Satrix 40 close is 100 times too small.** 25 April 2025: R0.84 against R84.12 the day before and
R85.05 the next trading day, while the Top 40 index moved normally. The same day appears in the price
errors found by jse-share-price-reconciliation.

**SARB's T-bill series reads 0.00% for five trading days,** 18 to 24 February 2022, between 3.89% and 4.15%.
A zero rate is missing data, not a real rate.

**Gaps.** The Top 40 index has no bar for 12 trading days, 11 of them in 2021 before the fund starts and one
on 19 February 2024. Satrix 40 has none for 18 and 20 January 2022, either side of its 19 January ex-date.
Satrix 40's latest bar is 28 September while the index has 29 September; the check covers each series' own
range, so a missing latest day is not yet flagged.

Adjusted close is not used: Yahoo's adjusted close for Satrix 40 moves only from 0.9973 to 1.0 of the close
over nearly five years, so it does not reflect the distributions.

## What the Satrix statements showed (30 September 2026)

**The year-end constituents are complete.** Every year-end from 2020 to 2025 lists 41 holdings (40
companies, with Investec's two lines), all mapped to a JSE code; each year's holdings add up to Satrix's
stated total, no year-end printed in two statements differs, and the weights sum to 100%.

**Yahoo's closes are back-adjusted, so they cannot be multiplied by Satrix's share counts.** A preview
against the Yahoo history already collected by jse-share-price-reconciliation (from 29 Sep 2021) matched
180 of 205 year-end prices from 2021 to 2025 to within 0.1%. Most of the rest differ by one constant
factor per share across every year-end before a later corporate action: Naspers -80% (a later share split),
Prosus -54% to 2022, Mondi +10% to 2023, Anglo American -1.7% to 2024, and Investec (about -6.5%) and
Remgro (-2%) at 2021. The reasons behind the factors are not yet verified. Returns from Yahoo stay
consistent, but values do not, so benchmark weights are taken from Satrix's rand values and moved with
returns, never from share counts times Yahoo prices.

**Four benchmark members have no Yahoo prices for part of the period:** Richemont before 19 April 2023
(16.2% of Satrix 40 at the end of 2021), BHP Group plc before 31 January 2022 (13.2%), MultiChoice
throughout (1.0%, delisted December 2025) and Northam Platinum Ltd in 2020 (replaced by Northam Platinum
Holdings in 2021).

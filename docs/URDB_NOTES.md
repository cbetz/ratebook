# URDB Exploration Notes

Working notes from profiling the URDB bulk corpus (Sprint 0, task 2: "download `usurdb.csv.gz`, load into DuckDB, explore"). Six profiling passes were run against the raw table and every headline number was re-derived by an adversarial checker pass; where the checker disagreed, the corrected number or the uncertainty is stated inline.

## Provenance

- **Snapshot file:** `data/raw/usurdb-2026-06-13.csv.gz` (URDB bulk download, fetched from `apps.openei.org` — note the bulk file still serves from openei.org even after the API's May 2026 migration to developer.nlr.gov)
- **Downloaded:** 2026-06-12 21:02 EDT; server `Last-Modified: Fri, 12 Jun 2026 08:43:36 GMT` — corpus state is as-of June 12, 2026 UTC
- **Loaded to:** `raw.urdb` in `data/ratebook.duckdb` — 58,866 rows × 737 columns, **all VARCHAR** (every number below that involves dates/numerics went through `TRY_CAST`)
- **Integrity:** sha256 (`f0e23406…`), exact source URL, and fetch headers are in `data/raw/usurdb-2026-06-13.csv.gz.meta.json` and the `raw.ingests` table; row count in `raw.ingests` matches the table (58,866)

All percentages are rate-record-weighted unless stated otherwise. "Active" throughout means `enddate` NULL/empty — a URDB curation convention, not ground truth (see §1 and §6).

---

## 1. Corpus snapshot & freshness

**Shape.** 58,866 rows. `label` is a clean unique key (0 duplicates, 0 nulls). `eiaid` is populated on 100% of rows: 2,843 distinct eiaids vs 2,938 distinct utility name strings — 87 eiaids carry multiple name spellings, 17 names span multiple eiaids. **eiaid, not name, is the join key** (but see §4 for eiaid's own problems).

| Sector | Rows |
|---|---|
| Commercial | 27,952 |
| Residential | 13,807 |
| Industrial | 10,752 |
| Lighting | 6,344 |
| (missing) | 11 |

Active vs ended: 30,848 / 28,018 overall; Residential 6,353 active / 7,454 ended. `supersedes` lineage is populated on 26,276 rows (44.6%) — the only machine-readable version chain in the corpus. `startdate` is missing on 3,408 rows (5.8%), 0 unparseable; recent vintages: 2,142 rows with 2024 startdates, 2,233 with 2025, 1,266 with 2026.

**`latest_update` distribution by year** (all rows; checker note: the original profile omitted an 8-row 2014 bucket — full distribution below sums to 58,866):

| Year | Rows |
|---|---|
| 2014 | 8 |
| 2015 | 33,533 (57.0%) |
| 2016 | 2,809 |
| 2017 | 3,961 |
| 2018 | 3,337 |
| 2019 | 2,972 |
| 2020 | 497 |
| 2021 | 378 |
| 2022 | 1,581 |
| 2023 | 1,349 |
| 2024 | 2,610 |
| 2025 | 3,017 |
| 2026 | 2,814 |

**The "~150 utilities/year" claim is empirically dead-on.** Distinct eiaids with any record touched in calendar 2025: **151**. Trailing 12 months (since 2025-06-13): 138 utilities across 3,985 rows. 2026 YTD: 75 utilities / 2,814 rows. Against the ~3,000-utility EIA universe, URDB actively maintains ~5% of utilities per year.

**Stronger than "decaying" — possibly frozen.** The newest `latest_update` anywhere in the corpus is **2026-04-27 16:17:26**. Zero records were touched in May or June 2026, despite the snapshot being generated June 12 — ~6.5 weeks of total silence, lining up with the May 29 API migration and the NLR layoffs. Cadence had been a few hundred to ~950 rows/month through April 2026, then stopped. **Status: unknown whether this is permanent — single snapshot, ~2 weeks after the migration; could be a temporary pipeline pause. Re-verify on the next monthly snapshot before using in any public claim.**

**"Active" does not mean "current."** Of 6,353 active residential rates, only 838 (13.2%) have `latest_update` ≥ 2024-06-13; 4,711 (74%) still carry pre-2016 timestamps — loaded in the 2015 bulk era and never revisited, but with no enddate, so they read as live tariffs. Only 177 of the 2,594 eiaids with any active residential rate have one touched in the last 2 years. (Caveat: the 2015 spike is almost certainly a bulk-migration timestamp, so "untouched since 2015" means "never revisited since initial load," not "verified in 2015.") This is the quantitative case for Ratebook's own `last_verified` field and per-utility scorecard.

**Metadata Ratebook needs most is mostly empty:**

- `servicetype`: missing 42,171 (71.6%); Bundled 9,982; Delivery with Standard Offer 3,412; Delivery 3,252; Energy 49
- `is_default`: missing 44,852 (76.2%); false 13,292; true 722. Active residential: 5,158 missing / 1,007 false / **188 true** — far too few to drive ZIP→default-plan resolution
- `dgrules`: missing 42,613 (72.4%); Net Metering 15,276; Buy All Sell All 518; Net Billing 459
- There is **no `approved` column** anywhere in the 737 (checked all column names); the bulk file is presumably the approved-only view, so approval status can't be tracked from it

---

## 2. Column families: what URDB v8 actually carries

The 737 columns decompose into 11 families with zero leftovers. 664 columns (90%) are four flattened period/tier grids; 73 are flat columns:

| Family | Columns | Notes |
|---|---|---|
| energyratestructure | 340 | period0–34 × tier0–10 × {rate, adj, max, sell, unit} (sparse — CSV only emits columns some row uses) |
| demandratestructure (TOU demand) | 192 | {rate, adj, max, unit} per tier |
| flatdemandstructure | 120 | {rate, adj, max, unit} per tier |
| coincidentratestructure | 12 | only rate + adj ever hold data |
| identity/provenance | 15 | label, utility, eiaid, source, dates, supersedes… |
| voltage/capacity applicability | 10 | peakkwcapacity*, peakkwhusage*, voltage*, phasewiring |
| fixed charges | 6 | fixedchargefirstmeter/eaaddl/units, mincharge(+units), fixedattrs |
| energy + demand schedules | 2+2 | weekday/weekend 12×24 matrices (see §3) |
| flatDemandMonth_* | 12 | month → flat-demand period mapping |
| demand lookback/ratchet | 14 | lookbackpercent/range/month0–11 |
| structure-adjacent units/attrs/comments + dgrules | 11 | |

**Dead weight:** 243 columns (33%) are 100% empty in all 58,866 rows — 85 energy, 93 demand, 56 flat-demand, 8 coincident grid columns, plus the scalar `energyrateunit` (0 non-empty values corpus-wide). Coincident `*max`/`*unit` tier columns are empty everywhere.

**Population among active residential (n=6,353):**

| Family | Population |
|---|---|
| identity/provenance | 100% |
| energy rate structure (any rate cell) | 99.1% (6,295) |
| energy weekday/weekend schedules | 99.3% (6,310) |
| fixed charges (family) | 94.3% (fixedchargefirstmeter alone 90.7%) |
| voltage/capacity applicability | 34.6% |
| dgrules | 20.0% (1,271) |
| energy sell rates | 5.2% (332) |
| mincharge | 4.1% (263) |
| flat demand structure | 3.3% (207) |
| TOU demand structure (and its schedules) | 1.5% (94) |
| coincident demand / lookback-ratchet | ~0.1% each (5 / 7 rows) |

**Trap: unit columns are default-filled and must never be used as presence signals.** `demandrateunit` is populated ("kW") on 93.1% of active residential rows while real demand rate cells exist on 1.5%; `flatdemandunit` 57.3% vs 3.3% real structure. A naive any-non-empty-column family metric reports 94.2% and 57.4% — both artifacts. Presence tests must key on rate cells.

**Max populated indices.** Corpus-wide energy reaches period 34 / tier 10, but periods ≥24 carry only sell+unit cells (10 rows, sell-only feed-in structures), periods 15–23 are nearly all sell-only (34 rows), and only 2 rows have buy rates beyond period 14. Active residential never exceeds energy period 9 / tier 7; 99.7% fit within 6 periods. Demand: corpus p≤8/t≤15, active residential p≤3; flat demand corpus p≤7/t≤16, residential p≤2; coincident p≤2/t0 only.

Corpus-wide (commercial-dominated) the demand families are far more populated — TOU demand 13.1%, flat demand 36.4% — so demand support matters for any non-residential expansion even though it's nearly dead weight for the residential focus.

---

## 3. Residential rate-structure prevalence (what the Sprint-0 engine must support)

**How schedules are encoded.** `energyweekdayschedule` / `energyweekendschedule` are JSON-serialized **12×24 integer matrices** — 12 rows (Jan–Dec) × 24 columns (hours 0–23) — where each cell is a period index into `energyratestructure`. Every one of the 6,310 active residential schedules parses to exactly 288 entries; no other shape exists. Seasonality is implicit (month-rows differ); TOU is implicit (>1 distinct period within a row, or weekday ≠ weekend). One profiling pass found referenced period indices exactly match *defined* periods for all 6,295 rates with structure; a second pass using a stricter test (period must have a non-empty rate) found **at least 15** active-residential weekday schedules referencing a period with no rate defined — a floor, since weekend schedules and schedules referencing periods >5 weren't checked. Both checks belong in the grader (§6). There is **no holiday dimension** — real tariffs often bill holidays as weekend; URDB cannot express that.

**Structure classification of the 6,353 active residential rates** (classification script preserved at `/tmp/urdb_res_profile.py`; rules in the table notes):

| Class | Count | Share |
|---|---|---|
| Flat (1 period, 1 tier, no time variation) | 2,453 | 38.6% |
| Tiered non-TOU (1 effective period, >1 tier) | 1,363 | 21.5% |
| Seasonal-only flat | 438 | 6.9% |
| Seasonal-only tiered | 1,027 | 16.2% |
| TOU single-tier | 854 | 13.4% |
| TOU + tiered | 160 | 2.5% |
| No energy rate structure at all | 58 | 0.9% |

Roll-ups: 60% need only flat/tiered math; 2,075 (32.7%) have seasonal variation; 1,014 (16.0%) are TOU — and **610 of the 1,014 TOU rates are also seasonal**, so seasonal TOU is the dominant TOU form, not an edge case. The Sprint-0 engine target (tiered + TOU + seasonal + fixed charges) covers **99.1%** of active residential rates structurally.

**TOU decomposition:** 989 rates have true intra-day variation (797 of those also differ weekday vs weekend); only 26 differ weekday/weekend with uniform days. The engine needs both the hour dimension and the weekday/weekend daytype dimension from day one.

**Complexity ceilings:** up to 10 periods (16 rates use 9, 2 use 10) and up to 8 tiers (2 rates); 91% use ≤2 periods, 81% ≤2 tiers. Tier-count distribution: 1: 3,745 / 2: 1,401 / 3: 814 / 4: 191 / 5: 106 / 6: 31 / 7: 5 / 8: 2 — 2,550 multi-tier (checker: **40.1%** of the 6,353 denominator; the originally reported 40.5% divided by 6,295).

**Fixed charges are near-universal and not all $/month.** 90.7% (5,760) carry `fixedchargefirstmeter`; units $/month 5,697, **$/day 141** (median $0.626/day, max $8.34), missing 515. $/month percentiles (n=5,619): p5 $3.50, p25 $7.70, p50 $12.50, p75 $20.00, p95 $36.00; min −$6.00 (water-heater credits — negative fixed charges exist on 3 rates), max $1,500 (sector-mislabeled commercial, see §6). A $/day fixed charge makes the bill depend on billing-period length — **bill-match needs billing-period days as an input**.

**Demand charges touch residential:** 286 rates (4.5%) — 204 flat/monthly demand, 94 TOU demand (with their own 12×24 schedules), 12 both. Units include kW, kVA, "kVA daily", hp. Defensible to flag-and-refuse in Sprint 0, but 1-in-22 residential rates is uncomputable until it lands.

**Net metering signal is thin:** active residential `dgrules` = Net Metering 1,162 / Net Billing 68 / Buy All Sell All 41 / missing 5,082 (80.0%); 332 rates carry nonzero sell rates, 65 of those with no dgrules at all. Minimum charges: 263 rates in $/month (211), $/day (43), $/year (4).

**Big caveat:** these shares are rate-record-weighted across 2,686 utility names (2,594 eiaids) — a long tail of small munis/co-ops skews toward flat/tiered. Among big IOUs (CA, AZ, much of the top-25 list) TOU/seasonal-TOU shares are far higher. Re-run this profile restricted to the top-25 EIA-861 utilities before locking Sprint-0 engine scope.

---

## 4. Top-25 utility coverage (and the PECO bill-match target)

**Verdict: every named top-25 IOU/muni is present except Texas REPs.** Three buckets by `latest_update`:

**Fresh (touched in 2026, within ~5 months of snapshot):** PG&E ("Pacific Gas & Electric Co", 14328, 75 active res, 2026-04-14, 75/75 with source), LADWP (11208, 4, 2026-04-24), PECO (14940, 5, 2026-04-20), FPL (6452, 3, 2026-03-05), Duke Energy Progress NC/SC (as legacy "Progress Energy Carolinas Inc", eiaid 5416, 10+8, 2026-04-01/03-20), Duke Energy Carolinas NC/SC (5416, 7+6, 2026-02-20), Duke Florida ("Progress Energy Florida Inc", 6455, 5, 2026-04-17), Duke Indiana (15470, 2, 2026-03-23), Dominion ("Virginia Electric & Power Co", 19876, 8 VA 2026-02-19 + 4 NC 2025-09), APS (803, 14, 2026-03-03), SRP (16572, 38, 2026-02-27), Xcel-PSCo (15466, 5, 2026-03-20), PSE&G (15477, 10, 2026-04-17), DTE (5109, 29, 2026-04-21), Ameren IL (56697, 7, 2026-03-31), Ameren MO ("Union Electric Co", 19436, 6, 2026-01-05), Entergy LA (11241, 4, 2026-03-05) + Entergy New Orleans (13478, 2, 2026-04-27), Alabama Power (195, 14, 2026-04-14), Puget Sound Energy (15500, 13, 2026-04-27), Portland General (15248, 9, 2026-01-27 — only 6/9 have source URLs), BGE (1167, 10, 2026-03-09).

**Recent (6–22 months):** SDG&E (16609, 25, 2025-05-21), SCE (17609, 34, 2024-08-29 — oldest non-stale at ~21 months), ComEd (4110, 16, 2025-02-03), Con Edison (4226, 26, 2025-02-18), Georgia Power (7140, 4, 2025-01-06), Xcel NSP-MN (13781, 9, 2025-02-05) and NSP-WI (13780, 4, 2025-04-02), National Grid NY ("Niagara Mohawk", 13573, 32, 2025-02-24), National Grid MA ("Massachusetts Electric Co", 11804, 12, 2025-03-11), Narragansett RI (13214, 4, 2025-08-18), Consumers Energy Co (4254, 8, 2025-06-25), Entergy MS (12685, 4, 2025-08-05), Entergy TX (55937, 2, 2025-03-13), Pepco (15270, 13, 2025-08-30).

**Stale or effectively missing:** Duke Energy Ohio (3542) has 54 residential rates and **zero active** — every one enddated (max 2024-02-29; last update 2024-06-10). Entergy Arkansas (814) likewise: 32 res rates, 0 active, 2024-06-06. Both utilities operate today, so zero-active means URDB maintenance lapsed, not that rates don't exist. NSP state-splits (SD/ND) frozen since 2017; Duke Kentucky (19446) 0 active since 2018; "Potomac Electric Power Co (Maryland)" split entity frozen since 2019.

**Texas reality check.** URDB contains **zero REP plans** — no TXU Energy, no Reliant, nothing that sets actual ERCOT retail residential prices. What it has: 2019-vintage delivery-only rates for the four TDUs (Oncor 44372 and CenterPoint 8901 each have 1 active residential rate, both last updated 2019-05-01; AEP TX ×2 and TNMP similar), plus genuinely fresh non-choice utilities: Austin Energy (1015, 5, 2025-09-09), CPS Energy (16604, 2, 2026-04-23), El Paso Electric (5701, 4, 2026-02-23), Entergy TX. Complete TX residential answers require composing TDU delivery + REP EFL pricing from a non-URDB source (Power to Choose).

**PECO (first bill-match target) is in excellent shape.** 5 active residential rates, eiaid 14940, all `latest_update` 2026-04-20, all with live source PDFs, all `startdate` 2026-01-01:

- `69e650226746522c70079989` — Residential Service (R), is_default=false
- `69e65026bc32447e430e25a9` — Residential Service (R), **is_default=true — the canonical one** (source: azure-na-assets.contentstack.com, "Pages 52 Rate R … Supp. no. 21 eff. Jan 1 2026")
- `69e65a18805b2131910774d9` — Residential Service (R) - TOU
- `69e652f1d52ff0b5930ddcd9` / `69e652f42a6d14bfa3011d29` — Residential Heating Service (RH) ×2 (source: peco.com, electric tariff eff. April 1, 2026)

Cautions: both R and RH exist as active duplicate pairs (the two RH rows were created **3 seconds apart** on 2026-04-20 per ObjectId timestamps — checker-corrected from "1 second"); only one R row carries is_default=true. And PECO's residential history has a hole — ended rates exist for 2015–2018 and 2025–26, nothing updated 2019–2024 — so historical bill reproduction beyond the current book can't lean on URDB.

**Identity hazards found while matching:** `eiaid` is VARCHAR with 163 float-artifact values ("14328.0"); state-jurisdiction splits share the parent's eiaid via name suffixes ("Duke Energy Carolinas, LLC (South Carolina)" = 5416); and there are outright wrong assignments — "Progress Energy Carolinas Inc" (Duke Energy Progress) carries 5416, Duke Carolinas' ID, while Duke Progress's actual EIA ID is believed to be 3046 (**domain knowledge, not yet verified against Form 861 — open question**). Name matching has collision traps: `%oncor%` also matches Concord/Concordia entities (the checker confirmed the headline Oncor numbers but flagged that the pattern as written returns 5 utility groups); Green Mountain Power (VT) ≠ Green Mountain Energy (TX REP); Salt River Electric Coop (16587) ≠ Salt River Project (16572); "Consumers Energy" (11788) ≠ "Consumers Energy Co" (4254). Sector labels also lie: FPL's 3 "active residential" rates include "GS-1 (General Service Non Demand and Non Metered)" — a commercial tariff tagged Residential; real FPL residential actives are RS-1 and RTR-1.

---

## 5. Golden-set feasibility

**Verdict: 20 golden pairs across major utilities is comfortably feasible** — a few hours of curation, not a research project.

**Pool math.** Of 6,353 active residential rates: 6,268 (98.7%) have a non-empty `source`; 4,518 (71.1%) are true `http(s)://` URLs. Of the 1,750 remainder, the checker found 156 are scheme-less URLs (`www.*`/bare domain), leaving ~1,594 genuinely free-text archival citations ("ISU Documentation", "Rates Binder A" — Illinois State University did the original long-tail data entry from paper binders). Among URL sources, roughly half are direct PDFs: 2,329–2,354 depending on classifier definition (51.5–52.1%, ~770–774 utilities) — the spread comes from `.pdf#fragment` URLs, `.cfm`/`.jsp` endpoints, and **~39 source fields that hold multiple `\r\n`-separated URLs** (a schema implication in its own right). Dynamic/HTML endpoints: ~1,350–1,388 (and the .pdf pool is understated — psc.wi.gov `viewfile.aspx` endpoints, 314 sources, likely serve PDFs). The prime stratum: **active residential + `.pdf` source + `latest_update` ≥ 2025-01-01 = 601 records across 126 utilities**, covering nearly every top-25 IOU/muni.

**Link-rot estimate** (14-URL `curl -sIL` spot check, biased toward big/recent utilities): 10/14 URLs fetchable as `application/pdf` — 9 with plain curl (PG&E, ComEd, PECO, Duke NC, Alabama, LADWP, Dominion VA, Eversource CT, APS), plus DTE/michigan.gov which 403s bare curl but serves with a browser User-Agent. URL-level failures: ConEd (200 but redirects to an HTML rates page), SCE (edisonintl.sharepoint.com 403/auth-wall), Georgia Power (hard 404, year-folder rotated), SDG&E (tariff.sdge.com connection failure even with browser UA). Checker nuance: Georgia Power's 2025-folder URLs elsewhere in the corpus return 200 PDF, and SDG&E's www.sdge.com URL also works — so at the **utility** level 12/14 have at least one working PDF source. Do not extrapolate ~70% to the long tail: 74% of active residential rates were last touched in 2015 and will have far worse rot. Also: a 200 PDF can still be a drifted revision — `dtee1cur.pdf`/`Utah_Price_Summary.pdf` are "current version" alias URLs whose content changes under a stable URL.

**Known gaps needing workarounds:** SCE (pair manually from public sce.com schedules), ConEd (manual PSC tariff PDF), and **FPL and Consumers Energy have zero active residential pdf-sourced records** — two top-10 utilities missing from the easy pool. SDG&E: retry from GCP or via Playwright.

**Candidate pairs** (`[v]` = HEAD-verified 200 `application/pdf` during profiling; full source URLs retrievable from `raw.urdb` by label):

| # | Label | Utility | Rate | Source / status |
|---|---|---|---|---|
| 1 | `69d92c23ac3477692606714c` | PG&E | E-1 Baseline Region P (default) | pge.com ELEC_SCHEDS_E-1.pdf [v] |
| 2 | `69de73e26d1ebb0263094f0c` | PG&E | E-TOU-C Region Z | pge.com ELEC_SCHEDS_E-TOU-C.pdf (same verified domain) |
| 3 | `69e65026bc32447e430e25a9` | PECO | Residential Service (R), default — **the bill-match target** | contentstack CDN, Rate R supp. 21 eff. 2026-01-01 [v] |
| 4 | `69e65a18805b2131910774d9` | PECO | Residential (R) - TOU | same PDF as #3 [v] — verify it covers TOU before locking |
| 5 | `679c05efaddfd4b96500e1d4` | ComEd | BES Residential Single Family w/o Space Heat (default) | comed.com CDN [v] — source is a billed-charges *guide*, not the tariff; verify sufficiency |
| 6 | `69e681d00b9e1bb34f0912d9` | DTE Electric | Rate D1 Full Service (default) | michigan.gov rate book (browser-UA only) |
| 7 | `6998c205a746c90e550cb23f` | Duke Energy Carolinas | RS Residential | duke-energy.com ncschedulers.pdf [v] |
| 8 | `69c1a32d79e080761e08539c` | Duke Energy Indiana | RS Residential (default) | duke-energy.com IURC-16 rate-rs |
| 9 | `69deb3d8e547dde41109ee02` | Alabama Power | Family Dwelling Service (default) | alabamapower.com FD.pdf [v] |
| 10 | `69a706ab7da20ea6b00d0238` | APS | R-TOU-E 4–7pm (default) | aps.com [v] |
| 11 | `69a1b8bf40140c3bb007f1bd` | SRP | E-23 Tier 1 Basic (default) | srpnet.com FY26 ratebook |
| 12 | `6997c46543b6aa9b2a015f78` | Dominion (VEPCO) | Schedule 1 (default) | dominionenergy azureedge CDN [v] |
| 13 | `69eb933dd52ff0b5930ddce2` | LADWP | R1A Zone 1 (default) | ladwp.com full rate book [v] |
| 14 | `6973ea390a32312ef00ae241` | LIPA | 180/183/186 Residential (default) | lipower.org Jan-2026 tariff book |
| 15 | `6969340fd06d027d0c0c65bc` | Eversource CT (CL&P) | Rate 1 (default) | eversource.com rate-1-ct.pdf [v] |
| 16 | `68b399e19d10ce4ee705c572` | Pepco | Schedule R (default) | pepco.com CDN (same Exelon contentstack as verified #3/#5) |
| 17 | `69ea606ff253a30c3f0075ee` | NV Energy (Nevada Power) | ORS-TOU | nvenergy.com |
| 18 | `685c51a57ab730a74905690c` | PacifiCorp UT (Rocky Mountain Power) | Schedule 1 (default) | rockymountainpower.net Utah_Price_Summary.pdf (alias URL — content drifts) |
| 19 | `6859a625ee417fe3fa0cb0df` | We Energies | Rg 1 (default) | we-energies.com elecrateswi.pdf (tariff book, #pagemode fragment) |
| 20 | `69dd1b5381bf8b311c0576a8` | AEP Ohio | RS Bundled | aepohio.com full tariff book |

Alternates if any fail on full GET: `69394fd9e1b9b205080a1589` (Tucson Electric TRRES, docs.tep.com), `69efcb2f99dfb306b503f3ab` (Puget Sound 7A, pse.com — domain verified), `69794f3fadcfa9a14a06546a` (Portland General Rate 7, assets.ctfassets.net).

Deliberate shape mix: ~15 single-schedule PDFs + ~5 whole tariff books (AEP Ohio, LIPA, LADWP, We Energies, ConEd-style). The books stress-test extraction differently — finding the schedule inside a 100–500 page document — and the golden set should cover both.

---

## 6. Data-quality hazards (feed these to the eval harness)

1. **Silent date corruption in exactly the rows we care about.** 124 enddates use two-digit years (`24-12-30 23:59:56`) that `TRY_CAST` happily parses as year 24 AD — concentrated in post-2023 records of top-25 utilities: NYSEG (26), BG&E (18), Duke Indiana (18), Niagara Mohawk (17), Xcel-MN (14), ComEd (12), PPL (7), SRP (5), LADWP (3), ConEd (2), PSCo (2). Zero such startdates. A pipeline without a 4-digit-year floor sorts these as the "oldest" revision.
2. **More date sentinels:** 57 epoch-zero startdates (1969-12-30/31 = unix 0 with TZ offsets, meaning "unknown"); 1,067 startdate>enddate rows, 852 of them within 2 days (timezone-shifted midnight artifacts — pervasive 01:00:00/06:00:00/23:59:56 times); 3,408 rows with no startdate. Zero parseable enddates are in the future (max 2026-04-09): **enddate is a retroactive retirement stamp, never a scheduled expiry.**
3. **Numerics are syntactically clean, semantically wild.** 0 `TRY_CAST` failures across fixedchargefirstmeter (53,660 non-empty), tier0rate (52,031), tier0max (14,947). But: tier0rate spans −0.3027 to 10,984 $/kWh (221 negative, 1,713 zero, 30 above $5); fixedchargefirstmeter max $2,532,584.53, 13 negative. Validation must be semantic range guards, not parsing.
4. **Tier-partition violations exist but are rare:** 4 residential period0 rows where tier maxes don't increase (a 3000→200 inversion; an exact 150=150 tie) + 3 multi-tier rows missing tier0max. Perfect negative examples for the grader's tiers-partition check — but ~7 hits in 58,866 rows means the check is necessary, nowhere near sufficient; synthetic negatives are also needed.
5. **Schedule integrity:** all 6,310 active-residential weekday schedules have exactly 288 slots, but ≥15 reference a period with no rate defined (floor — see §3). Grader needs "every referenced period has a rate" alongside the 8,760-hour-coverage check.
6. **Duplicate-active chaos:** 778 active (utility, name) pairs covering 1,573 rows are simultaneously "active" (Portland General Rate 7 ×4; PECO's RH pair created 3 seconds apart). Using active rows as ground truth without dedup + freshness filtering will poison the golden set.
7. **Lineage holes:** `supersedes` populated on 26,276 rows but 1,169 (4.4%) point to labels absent from the snapshot.
8. **Riders live in prose.** 3,819 of 6,353 active residential rates (60%) have a description; 1,039 of those (27%) mention rider/adjustment/fuel/surcharge (rider 282, adjustment 802, fuel 192, surcharge 70 — LIKE matches, some false positives). URDB's structured columns omit these — this is precisely the "your app lied about my bill" failure mode; bill-match within 2% will often be impossible from URDB numbers alone.
9. **One published tariff ≠ one URDB record:** LADWP publishes each tier/zone as a separate record; 103 active residential names contain "tier"/"zone". 10 records self-flag "[URDB cannot correctly model this rate]". 262 rows have no charging structure at all (191 "active"); 58 active residential rows have no energy rate; 11 rows have NULL sector; 533 have no source.
10. **Unit zoo:** fixedchargeunits $/month 53,254 / $/day 1,302; tier max units kWh 41,606 / kWh/kW 2,230 / "kWh daily" 852 / kWh/kVA 126 / kWh/hp 118 / "kWh/kW daily" 2; demand units include kVA (678), hp (363), "kW daily" (47); mincharge includes $/year (67).

**Grader checklist derived from observed failures:** (a) tier maxes strictly increase, final tier open; (b) every period referenced in weekday+weekend schedules has ≥1 rate; (c) schedules are exactly 288 slots; (d) value-range guards (residential rate in [−1, 5] $/kWh, fixed charge in [0, 500] $/month; flag negatives); (e) 4-digit-year and range checks on dates; (f) units within the closed enums.

---

## 7. Implications for extended schema v0

Consolidated from all six passes:

- **Don't flatten.** Store rate structures as variable-length nested lists (periods → tiers). The 664 flattened columns are 90% of URDB's width and a third of all columns are 100% empty. Energy tiers carry 5 fields (rate, adj, max, sell, unit); demand/flat-demand tiers 4 (no sell); coincident needs only rate/adj. Drop `energyrateunit` entirely.
- **Units are closed enums with normalization rules:** fixed charge {$/month, $/day}, min charge {$/month, $/day, $/year}, tier max {kWh, kWh/kW, kWh daily, kWh/kVA, kWh/hp}, demand {kW, kVA, hp, daily variants}. The engine implements demand-normalized tiers and daily proration **or returns a first-class `unsupported_structure` — never silently computes**. Signed values (negative fixed charges exist). Never use unit fields as presence evidence (default-filled); when importing a populated structure with missing unit, inherit URDB defaults (kWh/kW) explicitly.
- **Schedules:** adopt the 12×24 weekday/weekend integer-matrix form as canonical interchange (covers 99.3% of active residential, maps directly to the 8,760-hour grader check), parsed from JSON. Add an explicit **holiday-treatment field** that URDB imports leave as `unknown`.
- **Three independent date/verification fields:** effective range (`start`/`end`, validity constraint start ≤ end, tolerating open/missing bounds), Ratebook-owned `last_verified` + confidence, and `urdb_latest_update` as provenance. Distinguish `superseded_at` (URDB enddate semantics) from `scheduled_end` (which URDB never carries), and "no end date because current" from "end date unknown." Ingest enforces 4-digit years, nulls pre-1990 sentinels, normalizes TZ-shifted timestamps to dates.
- **Utility identity:** dimension table keyed on normalized EIA ID **plus jurisdiction** (PacifiCorp ×4 states, Duke ×4+ jurisdictions share one eiaid via name suffixes), with a name-alias table; strip `.0` float artifacts; reconcile against Form 861.
- **Record identity:** keep `label` as the source-record id, but canonical identity is (utility_id, plan_code/name, effective_range) with explicit revision chains; carry `supersedes` (4.4% dangling) and dedup near-identical rows created seconds apart. Add a variant-grouping mechanism (zone/tier/voltage/region variants of one tariff) and an `unmodelable`/`modeling_limitations` flag.
- **Ratebook-owned `is_default_plan`** per utility+sector, curated for the top 150 — URDB is_default is tri-state (true/false/NULL; don't coerce NULL to false), covers ~7% of utilities, and 8 utilities have multiple active "defaults."
- **Provenance:** `source_documents` as an **array** ({url, role, …} — multi-URL source fields exist), `source_type` enum (pdf_url | html_url | dynamic_endpoint | archival_citation | unknown), **archive-at-ingest** (sha256 of fetched copy, fetch timestamp, http_status, content_type, fetch_method plain|browser_ua|playwright — the URL alone is not durable), preserve `?rev=`/`?sfvrsn=`/`?hash=` CDN params as a `revision_token` (free change-detection signal), and a sub-URL locator (page_range/anchor/schedule_id) for tariff-book sources. Record snapshot provenance per record (raw.ingests already has file/sha256/Last-Modified) and publish upstream staleness (max latest_update vs snapshot date) as a metric.
- **NEM:** first-class structured block (mechanism, export rate, true-up, vintage/grandfathering), `unknown`-first, populated by PDF/PUC extraction; preserve URDB `dgrules` + sell rates as provenance-tagged hints only.
- **Riders are load-bearing, not optional:** first-class line items; preserve raw description/comments text as extraction provenance.
- **servicetype** as a required, Ratebook-curated enum modeling delivery and supply components separately (71.6% missing in URDB; essential for restructured states, PECO included). **Texas carve-out:** tariff_type = bundled | delivery-only (TDU) | supply-only (REP); the engine and bill-match must support composing the two.
- **Sector:** closed enum + unknown; re-derive/validate during extraction (URDB sector is a hint — FPL GS-1 case), with plausibility checks (residential fixed-charge range, max demand) feeding the HITL queue.
- **Ingest guards fail soft:** quarantine zero-energy-structure records (58 active residential would otherwise serve $0/kWh); missing source/sector goes to HITL, not hard failure.
- **Golden-set sampling:** stratify on the freshness bimodality — prefer the trailing-12-month stratum (~3,985 rows / 138 utilities) and 2024–2026 startdate vintages; treat pre-2016-touched records as historical/unverified with probable link rot. Applicability fields (34.6% populated) are nullable; absence means "applies unless stated," not data to fabricate.

---

## 8. Open questions

- [ ] **Is URDB frozen or paused?** Zero updates since 2026-04-27 across the whole corpus. Re-check on the July snapshot before this goes anywhere near marketing copy. ("Decaying, not dead" remains the defensible claim; "frozen" is one more snapshot away from provable.)
- [ ] **Duke Energy Progress eiaid:** URDB assigns 5416 (Duke Carolinas' ID); actual EIA ID believed 3046 — verify against EIA Form 861 when the utility dimension loads.
- [ ] **`adj` (adjustment) columns were not profiled** — they're URDB's thin gesture at riders; profile their usage before finalizing the rider schema.
- [ ] **Re-run the structure-prevalence profile restricted to top-25 EIA-861 utilities** (customer-weighted) before locking Sprint-0 engine scope — the corpus-wide shares understate TOU.
- [ ] **psc.wi.gov `viewfile.aspx` endpoints** (314 sources): confirm they serve PDFs — would grow the golden-pair pool.
- [ ] **SDG&E fetchability:** tariff.sdge.com refused this network; retry from GCP / Playwright (www.sdge.com URLs work).
- [ ] **Candidates #4 and #5 source sufficiency:** PECO TOU shares the Rate-R PDF; ComEd's source is a billing guide, not the tariff. Verify content before locking the golden set.
- [ ] **Weekend-schedule and high-period dangling-reference check:** the 15-row count is a floor; finish the sweep when building the grader.
- [ ] **FPL + Consumers Energy golden pairs:** zero active residential pdf-sourced records; source PDFs manually from utility sites.
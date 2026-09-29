# ShotSense · Shot Data Probe 2014–15

An **offline, single-file, interactive data explorer** for the 2014–15 NBA shot dataset.
The whole dashboard — all **102,992 shots × 58 model parameters** — lives inside one 9.6 MB
`index.html`. No server, no backend, no sampling: the browser decompresses the embedded
dataset, infers each column's type, handles missing values and computes every statistic live.

**▶ Open [`index.html`](index.html)** — double-click it, or serve it with any static host.

> 中文摘要：這是一個**離線單檔**的互動式資料探索網頁，把 2014–15 賽季全部 102,992 筆出手 ×
> 58 個模型參數內嵌在一個 HTML 裡。瀏覽器端即時解壓、自動判定欄位型別、處理缺失值並計算所有
> 統計量（沒有抽樣、沒有後端）。支援中／英雙語切換（頁面底部），並以可折疊卡片疊放呈現，
> 不會一次把所有圖表塞給使用者。

---

## What the dashboard gives you

Ten collapsible cards. Only the first two open by default, so you can scan before you dive in.

| # | Card | What it does |
|---|---|---|
| 00 | **Parameter Select** | Pick α (primary) and β (secondary) from the 58 parameters, filter by group, quick-pick chips. Shows dtype, group, SHAP rank, valid N, missing rate for each. |
| 01 | **Statistical Profile** | mean · median · std · skewness (G1) · excess kurtosis (G2) · missing rate · normality verdict · min/max · IQR · coefficient of variation · zero rate. Categorical columns get class count, largest class, imbalance ratio and entropy instead. |
| 02 | **Distribution** | Histogram with Freedman–Diaconis binning and a Silverman-bandwidth Gaussian KDE overlay, log-scale toggle, wheel zoom + drag pan. Categorical α renders a ranked bar chart. |
| 03 | **Normality / Q-Q** | Q-Q plot against a `μ + σz` reference line, with Jarque–Bera statistic and p-value. The S-shape / tail behaviour tells you *how* it deviates, not just *that* it does. |
| 04 | **Outliers** | Box plot with a 1.5 × IQR fence, whisker caps and jittered outlier points. The axis always spans the full data range (so nothing is clipped) but opens zoomed to the whiskers (so the box stays readable). |
| 05 | **Bivariate** | α × β scatter. Numeric × numeric → scatter + binned-median trend line. Categorical × numeric → jittered bands with per-class medians. Categorical × categorical → contingency heat map. **Click any point to inspect the full 58-value record and the player behind it.** |
| 06 | **Association** | Which measure is appropriate and why — Spearman ρ (continuous × continuous), correlation ratio η (categorical × continuous), bias-corrected Cramér's V (categorical × categorical) — plus strength meter, direction and a full readout. |
| 07 | **Correlation Matrix** | The full 58 × 58 association matrix on a single consistent metric, computed exactly in Python on all 102,992 rows. Click any cell to set that pair as α / β. A "strongest pairs" table below surfaces column redundancy. |
| 08 | **Missingness** | Missing-value rate per parameter, severity-coloured, plus totals. |
| 09 | **Parameter Ledger** | The full 58-row register — sortable, searchable, group-filterable. Click a row to set α, Shift-click to set β. |

**Interaction:** hover for values, click a scatter point for the full shot record, switch
parameters and every dependent card re-renders instantly, wheel-zoom and drag-pan on every
chart, responsive down to 430 px, and a language switcher (`中文 / ENGLISH`) pinned to the bottom.

---

## Repository layout

```
ShotSense/
├── index.html                                   # the dashboard — 9.6 MB, self-contained
├── data/
│   ├── shotsense_2014_15_58params.csv           # 43 MB · 102,992 × 58, the page's data source
│   └── shots_master_2014_15_v4_matchup.parquet  # 9 MB · upstream table (91 cols) used to build it
├── outputs/
│   └── shap_ranking_full.csv                    # the 58-parameter list + SHAP importance + groups
└── src/probe/
    ├── build_probe_dashboard.py                 # builds index.html + the CSV
    ├── template.html                            # the frontend source (design system, charts, i18n)
    ├── fetch_fonts.py                           # downloads + base64-embeds the Google Fonts subsets
    ├── fonts.css                                # 404 KB · 8 embedded woff2 faces
    ├── verify.js                                # headless verification harness (52 checks)
    ├── echarts.min.js                           # vendored Apache ECharts 5
    └── fflate.min.js                            # vendored fflate (gzip in the browser)
```

---

## The dataset

**102,992 shots × 58 parameters**, one row per field-goal attempt in the 2014–15 NBA regular
season, covering **281 players** from **2014-10-28 to 2015-03-04**.

- Heaves (end-of-period desperation attempts) are excluded, as are shots without tracking data.
- 41 parameters are continuous, 17 are categorical.
- 20 parameters have missing values; the worst is `age_at_season` at 28.66 %. Gaps concentrate in
  rolling features that need a historical window — early-season games simply have not accumulated
  enough history yet. Those NaNs are handled natively by XGBoost at modelling time.

### Data dictionary

`mean|SHAP|` is the mean absolute SHAP value from the v4 matchup XGBoost model — a measure of how
much each parameter actually moves the model's output. "New in v4" marks the seven
opponent-body / matchup features added in the fourth feature-engineering iteration.

| # | Parameter | Group | Type | mean\|SHAP\| | New in v4 |
|---|---|---|---|---|---|
| 1 | `action_type` | 出手型態 | categorical | 0.3860 |  |
| 2 | `score_margin_at_shot` | 賽況/時間 | continuous | 0.2465 |  |
| 3 | `close_def_dist` | 防守壓力 | continuous | 0.1922 |  |
| 4 | `shot_dist_calc` | 空間/幾何 | continuous | 0.1565 |  |
| 5 | `touch_time` | 出手型態 | continuous | 0.1187 |  |
| 6 | `is_home` | 賽程/環境 | categorical | 0.0899 |  |
| 7 | `action_type_target_enc` | 出手型態 | continuous | 0.0787 |  |
| 8 | `team_rolling_fg_last_10` | 球員/球隊狀態 | continuous | 0.0650 |  |
| 9 | `shot_distance_log` | 空間/幾何 | continuous | 0.0499 |  |
| 10 | `dribbles` | 出手型態 | continuous | 0.0440 |  |
| 11 | `position` | 球員/球隊狀態 | categorical | 0.0422 |  |
| 12 | `period` | 賽況/時間 | categorical | 0.0384 |  |
| 13 | `shot_clock` | 賽況/時間 | continuous | 0.0380 |  |
| 14 | `season_game_no` | 賽程/環境 | continuous | 0.0369 |  |
| 15 | `dist_to_sideline` | 空間/幾何 | continuous | 0.0308 |  |
| 16 | `height_adv_over_dist` | 防守壓力 | continuous | 0.0300 | yes |
| 17 | `dist_x_angle` | 空間/幾何 | continuous | 0.0288 |  |
| 18 | `age_at_season` | 球員/球隊狀態 | continuous | 0.0254 |  |
| 19 | `loc_y` | 空間/幾何 | continuous | 0.0247 |  |
| 20 | `player_rolling_fg_last_5` | 球員/球隊狀態 | continuous | 0.0240 |  |
| 21 | `shot_distance` | 空間/幾何 | continuous | 0.0232 |  |
| 22 | `player_prior_attempts` | 球員/球隊狀態 | continuous | 0.0225 |  |
| 23 | `weight_lb` | 球員/球隊狀態 | continuous | 0.0212 |  |
| 24 | `seconds_remaining` | 賽況/時間 | continuous | 0.0196 |  |
| 25 | `defender_height_in` | 防守壓力 | continuous | 0.0186 | yes |
| 26 | `defender_weight_lb` | 防守壓力 | continuous | 0.0160 | yes |
| 27 | `is_catch_and_shoot` | 出手型態 | categorical | 0.0151 |  |
| 28 | `weight_diff` | 防守壓力 | continuous | 0.0140 | yes |
| 29 | `player_id_target_enc` | 球員/球隊狀態 | continuous | 0.0139 |  |
| 30 | `draft_year` | 球員/球隊狀態 | continuous | 0.0138 |  |
| 31 | `height_in` | 球員/球隊狀態 | continuous | 0.0123 |  |
| 32 | `shot_angle_rad` | 空間/幾何 | continuous | 0.0118 |  |
| 33 | `shot_dist_error` | 空間/幾何 | continuous | 0.0115 |  |
| 34 | `shot_clock_filled` | 賽況/時間 | continuous | 0.0110 |  |
| 35 | `offensive_time_consumed` | 賽況/時間 | continuous | 0.0089 |  |
| 36 | `shot_zone_range` | 分區標籤 | categorical | 0.0085 |  |
| 37 | `dist_to_baseline` | 空間/幾何 | continuous | 0.0073 |  |
| 38 | `height_diff` | 防守壓力 | continuous | 0.0072 | yes |
| 39 | `shot_number` | 賽況/時間 | continuous | 0.0072 |  |
| 40 | `shot_zone_basic` | 分區標籤 | categorical | 0.0072 |  |
| 41 | `loc_x` | 空間/幾何 | continuous | 0.0071 |  |
| 42 | `rest_days` | 賽程/環境 | continuous | 0.0056 |  |
| 43 | `shot_angle_abs_deg` | 空間/幾何 | continuous | 0.0051 |  |
| 44 | `player_rolling_made_last_3` | 球員/球隊狀態 | categorical | 0.0039 |  |
| 45 | `years_in_league` | 球員/球隊狀態 | continuous | 0.0038 |  |
| 46 | `n_officials` | 賽程/環境 | continuous | 0.0031 |  |
| 47 | `is_back_to_back` | 賽程/環境 | categorical | 0.0029 |  |
| 48 | `shot_angle_deg` | 空間/幾何 | continuous | 0.0021 |  |
| 49 | `shot_angle_sym_deg` | 空間/幾何 | continuous | 0.0020 |  |
| 50 | `shot_zone_area` | 分區標籤 | categorical | 0.0019 |  |
| 51 | `is_height_advantage` | 防守壓力 | categorical | 0.0003 | yes |
| 52 | `offensive_time_consumed_filled` | 賽況/時間 | continuous | 0.0001 |  |
| 53 | `shot_type` | 出手型態 | categorical | 0.0000 |  |
| 54 | `PTS_TYPE` | 分區標籤 | categorical | 0.0000 |  |
| 55 | `is_corner_3` | 空間/幾何 | categorical | 0.0000 |  |
| 56 | `is_shot_clock_zero` | 賽況/時間 | categorical | 0.0000 |  |
| 57 | `is_shot_clock_missing` | 賽況/時間 | categorical | 0.0000 |  |
| 58 | `is_defender_height_missing` | 防守壓力 | categorical | 0.0000 | yes |

Columns marked *continuous* that are actually small-range integers (`period`, `dribbles`) are
kept continuous on purpose — the auto-detection rule is dtype-aware, not "few unique values ⇒
categorical", because that heuristic would misclassify rolling percentages such as
`player_rolling_fg_last_5` (only 11 distinct values) as categorical.

---

## Rebuilding

Requirements: Python 3.10+ with `pandas`, `numpy`, `scipy`.

```bash
python src/probe/build_probe_dashboard.py
```

This reads `data/shots_master_2014_15_v4_matchup.parquet` and `outputs/shap_ranking_full.csv`,
and writes `index.html` (~9.6 MB) plus `data/shotsense_2014_15_58params.csv` (~43 MB).
Takes roughly 30–80 s. The build fails loudly if any template placeholder is left unreplaced.

The embedded web fonts are already committed in `src/probe/fonts.css`. To regenerate them:

```bash
python src/probe/fetch_fonts.py
```

## Verification

`src/probe/verify.js` drives a real headless Chrome (via `puppeteer-core`) against `index.html`
and runs **52 assertions** — statistics cross-checked against pandas, real mouse hover and click
on chart data points, parameter switching, heat-map cell clicks, bilingual switching, accordion
expand/collapse, responsive layout at 430 px, and a hard check that no console error or page
error is emitted.

```bash
npm install puppeteer-core
NODE_PATH=./node_modules node src/probe/verify.js
```

Latest run: **52 / 52 passed · 0 console errors · 0 warnings**, boot in ~0.7 s.

---

## Technical notes

A few decisions worth knowing if you plan to reuse this approach.

**Embedding 43 MB of data in one HTML file.** The 58 columns are serialised column-oriented as
plain text (one column per line, comma-separated, empty field = missing), then `gzip -9`, then
base64: 23.2 MB of text → 5.93 MB gzipped → 7.91 MB base64. The browser inflates it with fflate's
`gunzipSync` (chosen over `DecompressionStream` for Safari < 16.4 compatibility) and parses it
with a character-code scanner into `Float64Array`s — no `split(',')`, which would allocate
6.3 million short-lived strings. Full parse plus statistics for all 58 columns takes under a second.

**Statistics that match pandas exactly.** Central moments are accumulated in a single pass using
Pébay's (2008) online update, with the M4 → M3 → M2 ordering and pre-update values — get this
order wrong and heavy-tailed kurtosis is badly underestimated (21.87 came out as 2.92 before the
fix). Skewness and kurtosis use the same bias corrections as pandas `.skew()` / `.kurt()`.
Verified against pandas to within 1e-4 on every tested column.

**One consistent association metric.** The correlation matrix would be meaningless if continuous
pairs used Pearson while categorical pairs used something else. Instead: continuous × continuous →
|Spearman ρ|, categorical × continuous → correlation ratio η, categorical × categorical →
bias-corrected Cramér's V. All 3,364 cells are computed in Python on the full dataset and embedded,
because pairwise-complete computation in the browser would be ~346 million operations.

**The 90s Retro Card & Editorial design system.** Cream newsprint canvas (`#F4F1DE`), paper panels
(`#FFFCEB`), deep navy ink (`#1D3557`), crimson / mustard / teal / burnt-orange accents. Cards use
a 2 px ink border with a hard `4px 4px 0` offset shadow; buttons physically translate on hover and
press. Playfair Display for headings, JetBrains Mono for all figures, Inter for body text — all
eight font faces are embedded as base64 woff2, so the page has no network dependencies at all.
Deliberately no gradients anywhere: the paper grain is an SVG `feTurbulence` texture and the
heat-map legend uses a piecewise scale.

---

## Data & attribution

- **Shot data** — the 2014–15 NBA shot log (SportVU player-tracking derived), 128,069 raw attempts,
  reduced to 102,992 after removing heaves and untracked attempts.
- **Player body metrics** (height, weight, position, draft year) — the Wyatt Walsh NBA SQLite
  database, merged in to build the v4 matchup features.

This repository is academic work for a final-year project. No license has been chosen yet — add one
before reusing the code.

## Enabling GitHub Pages

To view the dashboard as a live page instead of downloading it:

**Settings → Pages → Source: `Deploy from a branch` → Branch: `main` / `root` → Save**

The page will then be served at `https://jaszw13.github.io/ShotSense/`. Because `index.html` is
fully self-contained, it works as-is — no build step, no Jekyll config needed.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShotSense :: Data Probe builder
================================
把 2014-15 賽季 58 個 model parameter 打包成單一自帶資料的互動式網頁。

產出：
  1. index.html —— 單檔、離線可用、含全部 102,992 筆
     ＋ 10/11/12 號卡片（EBM vs XGBoost、EBM 形狀篩選、EBM 報告）
  2. data/shotsense_2014_15_58params.csv —— 58 欄位的乾淨 CSV（網頁的資料來源）

設計：
  - 58 個 parameter 直接取自 outputs/shap_ranking_full.csv 的特徵清單（v4 matchup model）
  - 原始 102,992 × 58 以「每欄一行、逗號分隔」的緊湊格式序列化，gzip + base64 後內嵌
  - 瀏覽器端自行解壓、解析、判定型別、處理缺失、計算統計量 —— 全部即時運算
  - 相關係數矩陣（Spearman ρ / 混合型別關聯強度）在 Python 端以全量資料精確計算後內嵌
  - EBM 的模型對照／形狀篩選／報告由 src/probe/build_ebm_bundle.py 先收斂成 ebm_bundle.json
"""

from __future__ import annotations

import base64
import csv
import gzip
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "data" / "shots_master_2014_15_v4_matchup.parquet"
SHAP_CSV = ROOT / "outputs" / "shap_ranking_full.csv"
TEMPLATE = Path(__file__).resolve().parent / "template.html"
ECHARTS = Path(__file__).resolve().parent / "echarts.min.js"
FFLATE = Path(__file__).resolve().parent / "fflate.min.js"
FONTS = Path(__file__).resolve().parent / "fonts.css"
EBM_BUNDLE = Path(__file__).resolve().parent / "ebm_bundle.json"
OUT_HTML = ROOT / "index.html"
OUT_CSV = ROOT / "data" / "shotsense_2014_15_58params.csv"

PLAYER_COL = "PLAYER_NAME_LOG"
LABEL_COL = "shot_made"
DATE_COL = "game_date"

# 判定為類別型的門檻：
#   - dtype 為 object / category 者一律視為類別型
#   - 數值欄位若「離散取值數 <= CAT_MAX_UNIQUE」且「取值密度 <= CAT_MAX_DENSITY」，
#     代表它是二元旗標或小範圍離散標籤（如 period、PTS_TYPE、is_home），也歸為類別型
CAT_MAX_UNIQUE = 15
CAT_MAX_DENSITY = 0.005


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 1. 讀取參數清單（含 SHAP 重要性與分組）
# ---------------------------------------------------------------------------
def load_params() -> list[dict]:
    with open(SHAP_CSV, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    params = []
    for r in rows:
        params.append(
            {
                "name": r["feature"].strip(),
                "group": (r["group"] or "").strip() or "未分組",
                "shap": float(r["mean_abs_shap_B"] or 0.0),
                "rank": int(float(r["rank_B"])),
                "matchup": r["is_matchup"].strip().lower() == "true",
            }
        )
    log(f"參數清單：{len(params)} 個")
    return params


# ---------------------------------------------------------------------------
# 2. 型別自動判定
# ---------------------------------------------------------------------------
def dtype_class(series: pd.Series) -> str:
    if series.dtype == object or isinstance(series.dtype, pd.CategoricalDtype):
        return "obj"
    if pd.api.types.is_integer_dtype(series) or pd.api.types.is_bool_dtype(series):
        return "int"
    return "float"


def detect_kind(series: pd.Series) -> tuple[str, list]:
    """回傳 (kind, categories)；kind ∈ {'cat', 'num'}

    規則（依序）：
      1. object / category dtype                        → 類別型
      2. 只有一個取值（常數）                            → 數值型（UI 會標記為常數）
      3. 整數 / 布林 dtype 且離散取值 <= CAT_MAX_UNIQUE  → 類別型（二元旗標、period、PTS_TYPE …）
      4. 浮點 dtype 且離散取值 <= 2                      → 類別型（浮點編碼的 0/1 旗標）
      5. 其餘                                            → 連續型
    """
    s = series.dropna()
    n_unique = int(s.nunique())
    cls = dtype_class(series)
    if cls == "obj":
        return "cat", sorted(s.unique().tolist())
    if n_unique <= 1:
        return "num", []
    if cls == "int" and n_unique <= CAT_MAX_UNIQUE:
        return "cat", sorted(s.unique().tolist())
    if cls == "float" and n_unique <= 2:
        return "cat", sorted(s.unique().tolist())
    return "num", []


# ---------------------------------------------------------------------------
# 3. 相關係數矩陣（全量精確計算）
# ---------------------------------------------------------------------------
def rank_matrix(M: np.ndarray) -> np.ndarray:
    """逐欄做 average-rank 轉換，NaN 保持 NaN。M: (n, k)"""
    n, k = M.shape
    R = np.full((n, k), np.nan, dtype=np.float64)
    for j in range(k):
        col = M[:, j]
        m = ~np.isnan(col)
        v = col[m]
        if v.size == 0:
            continue
        order = np.argsort(v, kind="mergesort")
        sv = v[order]
        ranks = np.empty(v.size, dtype=np.float64)
        i = 0
        while i < v.size:
            j2 = i
            while j2 + 1 < v.size and sv[j2 + 1] == sv[i]:
                j2 += 1
            ranks[order[i : j2 + 1]] = 0.5 * (i + j2) + 1.0
            i = j2 + 1
        R[m, j] = ranks
    return R


def spearman_pairwise(R: np.ndarray) -> np.ndarray:
    n, k = R.shape
    C = np.full((k, k), np.nan, dtype=np.float64)
    valid = ~np.isnan(R)
    for i in range(k):
        C[i, i] = 1.0
        ai_all = R[:, i]
        for j in range(i + 1, k):
            m = valid[:, i] & valid[:, j]
            if m.sum() < 30:
                C[i, j] = C[j, i] = np.nan
                continue
            a = ai_all[m]
            b = R[m, j]
            a = a - a.mean()
            b = b - b.mean()
            den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
            r = float((a * b).sum()) / den if den > 0 else np.nan
            C[i, j] = C[j, i] = r
    return C


def eta_squared_corr(cat_codes: np.ndarray, rank_vals: np.ndarray) -> float:
    """名目 × 數值 的關聯強度：correlation ratio η = sqrt(SSB/SST)，值域 0..1"""
    m = ~np.isnan(cat_codes) & ~np.isnan(rank_vals)
    c = cat_codes[m].astype(np.int64)
    y = rank_vals[m]
    if y.size < 30:
        return float("nan")
    ybar = y.mean()
    sst = float(((y - ybar) ** 2).sum())
    if sst <= 0:
        return float("nan")
    ssb = 0.0
    for g in np.unique(c):
        yg = y[c == g]
        ssb += yg.size * (yg.mean() - ybar) ** 2
    return math.sqrt(max(ssb / sst, 0.0))


def cramers_v(cat_a: np.ndarray, cat_b: np.ndarray) -> float:
    """名目 × 名目：bias-corrected Cramér's V"""
    m = ~np.isnan(cat_a) & ~np.isnan(cat_b)
    a = cat_a[m].astype(np.int64)
    b = cat_b[m].astype(np.int64)
    if a.size < 30:
        return float("nan")
    ct = pd.crosstab(pd.Series(a), pd.Series(b)).values.astype(np.float64)
    chi2 = float(stats.chi2_contingency(ct, correction=False)[0])
    n = ct.sum()
    r, k = ct.shape
    if n <= 1:
        return float("nan")
    phi2 = chi2 / n
    phi2corr = max(0.0, phi2 - (k - 1) * (r - 1) / (n - 1))
    rcorr = r - (r - 1) ** 2 / (n - 1)
    kcorr = k - (k - 1) ** 2 / (n - 1)
    den = min(kcorr - 1, rcorr - 1)
    return math.sqrt(phi2corr / den) if den > 0 else float("nan")


def build_corr_matrices(df: pd.DataFrame, params: list[dict], kinds: dict) -> dict:
    names = [p["name"] for p in params]
    k = len(names)
    n = len(df)

    # 逐欄建矩陣：類別欄位先轉成整數碼，其餘轉 float
    raw = np.full((n, k), np.nan, dtype=np.float64)
    cat_codes = np.full((n, k), np.nan, dtype=np.float64)
    is_cat = np.zeros(k, dtype=bool)
    for j, nm in enumerate(names):
        kind, cats = kinds[nm]
        if kind == "cat":
            is_cat[j] = True
            cmap = {v: i for i, v in enumerate(cats)}
            codes = df[nm].map(cmap).astype(np.float64).to_numpy()
            raw[:, j] = codes
            cat_codes[:, j] = codes
        else:
            raw[:, j] = pd.to_numeric(df[nm], errors="coerce").to_numpy(dtype=np.float64)

    log("rank 轉換 …")
    R = rank_matrix(raw)

    log("Spearman ρ 逐對計算 …")
    C = spearman_pairwise(R)

    log("混合型別關聯強度矩陣 …")
    A = np.full((k, k), np.nan, dtype=np.float64)
    for i in range(k):
        A[i, i] = 1.0
        for j in range(i + 1, k):
            if is_cat[i] and is_cat[j]:
                v = cramers_v(cat_codes[:, i], cat_codes[:, j])
            elif is_cat[i] and not is_cat[j]:
                v = eta_squared_corr(cat_codes[:, i], R[:, j])
            elif not is_cat[i] and is_cat[j]:
                v = eta_squared_corr(cat_codes[:, j], R[:, i])
            else:
                v = abs(C[i, j]) if not np.isnan(C[i, j]) else np.nan
            A[i, j] = A[j, i] = v

    def clean(M):
        return [None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), 4)
                for v in M.reshape(-1)]

    return {"spearman": clean(C), "assoc": clean(A)}


# ---------------------------------------------------------------------------
# 4. 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    params = load_params()
    names = [p["name"] for p in params]

    log(f"讀取 {PARQUET.name} …")
    df = pd.read_parquet(PARQUET, columns=sorted(set(names + [PLAYER_COL, LABEL_COL, DATE_COL])))
    n = len(df)
    log(f"資料維度：{n:,} 筆 × {len(names)} 個 parameter")

    # --- 型別判定 ---
    kinds, catmaps_out, colinfo = {}, {}, []
    for p in params:
        nm = p["name"]
        kind, cats = detect_kind(df[nm])
        kinds[nm] = (kind, cats)
        colinfo.append(
            {
                "name": nm,
                "group": p["group"],
                "shap": p["shap"],
                "rank": p["rank"],
                "matchup": p["matchup"],
                "kind": kind,
                "dtype": dtype_class(df[nm]),
                "cats": cats,
            }
        )
    n_cat = sum(1 for c in colinfo if c["kind"] == "cat")
    log(f"型別判定：{len(colinfo) - n_cat} 連續型 / {n_cat} 類別型")

    # --- 相關矩陣 ---
    corr = build_corr_matrices(df, params, kinds)

    # --- 序列化資料本體 ---
    log("序列化資料本體 …")
    lines: list[str] = []
    for p in params:
        nm = p["name"]
        kind, cats = kinds[nm]
        if kind == "cat":
            cmap = {v: i for i, v in enumerate(cats)}
            v = df[nm].map(cmap)
            lines.append(",".join("" if pd.isna(x) else str(int(x)) for x in v))
        else:
            v = pd.to_numeric(df[nm], errors="coerce")
            lines.append(",".join("" if pd.isna(x) else ("%g" % round(float(x), 4)) for x in v))

    # 輔助欄位：球員索引 / 是否命中 / 比賽日（距開季天數）
    players = sorted(df[PLAYER_COL].dropna().unique().tolist())
    pidx = {v: i for i, v in enumerate(players)}
    lines.append(",".join(str(pidx[v]) for v in df[PLAYER_COL].fillna(players[0])))
    lines.append(",".join(str(int(v)) for v in df[LABEL_COL].fillna(0)))
    d0 = df[DATE_COL].min()
    lines.append(",".join(str(int(v)) for v in (df[DATE_COL] - d0).dt.days))

    raw_txt = "\n".join(lines)
    log(f"原始序列：{len(raw_txt)/1e6:.2f} MB")
    # mtime=0 keeps the gzip header timestamp-free, so the build is byte-reproducible
    gz = gzip.compress(raw_txt.encode("utf-8"), 9, mtime=0)
    b64 = base64.b64encode(gz).decode("ascii")
    log(f"gzip：{len(gz)/1e6:.2f} MB → base64：{len(b64)/1e6:.2f} MB")

    # --- 缺失去除統計（Python 端算，用來交叉驗證；前端亦會自行計算）---
    for c in colinfo:
        c["missing"] = int(df[c["name"]].isna().sum())

    meta = {
        "season": "2014-15",
        "n": int(n),
        "nPlayers": len(players),
        "dateStart": str(d0.date()),
        "dateEnd": str((df[DATE_COL].max()).date()),
        "shotMade": float(df[LABEL_COL].mean()),
        "params": colinfo,
        "players": players,
        "corr": corr,
        "payloadBytes": len(gz),
    }

    # --- 產出 CSV ---
    log(f"寫出 {OUT_CSV.name} …")
    out_csv = df[names].copy()
    for c in colinfo:
        if c["kind"] == "cat":
            out_csv[c["name"]] = out_csv[c["name"]].astype(str).replace({"nan": ""})
    out_csv.to_csv(OUT_CSV, index=False, encoding="utf-8")
    log(f"CSV：{OUT_CSV.stat().st_size/1e6:.1f} MB")

    # --- 組裝 HTML ---
    log("組裝 HTML …")
    tpl = TEMPLATE.read_text(encoding="utf-8")
    fonts_css = FONTS.read_text(encoding="utf-8") if FONTS.exists() else ""
    if fonts_css:
        log(f"內嵌字型：{FONTS.name}（{len(fonts_css)/1024:.1f} KB）")
    if not EBM_BUNDLE.exists():
        raise RuntimeError(
            f"缺少 {EBM_BUNDLE.name}；請先執行 src/probe/build_ebm_bundle.py"
        )
    ebm_js = EBM_BUNDLE.read_text(encoding="utf-8").replace("<", "\\u003c")
    log(f"內嵌 EBM bundle：{EBM_BUNDLE.name}（{len(ebm_js)/1024:.1f} KB）")
    html = tpl.replace("/*__FONTS__*/", fonts_css)
    html = html.replace("/*__ECHARTS__*/", ECHARTS.read_text(encoding="utf-8"))
    html = html.replace("/*__FFLATE__*/", FFLATE.read_text(encoding="utf-8"))
    meta_js = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = html.replace("/*__PROBE_META__*/", meta_js)
    html = html.replace("/*__EBM_BUNDLE__*/", ebm_js)
    html = html.replace("__PROBE_PAYLOAD__", b64)
    for token in ("/*__FONTS__*/", "/*__ECHARTS__*/", "/*__FFLATE__*/",
                  "/*__PROBE_META__*/", "/*__EBM_BUNDLE__*/", "__PROBE_PAYLOAD__"):
        if token in html:
            raise RuntimeError(f"模板佔位符未被替換：{token}")
    OUT_HTML.write_text(html, encoding="utf-8")
    log(f"HTML：{OUT_HTML}（{OUT_HTML.stat().st_size/1e6:.1f} MB）")

    # --- 摘要 ---
    print()
    print("=" * 78)
    print(f"  完成：{n:,} 筆 × {len(names)} 個 parameter / {len(players)} 名球員")
    print(f"  類別型：{n_cat} 個 → {[c['name'] for c in colinfo if c['kind']=='cat']}")
    miss = [(c['name'], c['missing']) for c in colinfo if c['missing'] > 0]
    print(f"  有缺失：{len(miss)} 個欄位，最高 {max(miss, key=lambda x: x[1])[0]} "
          f"({max(x[1] for x in miss)/n*100:.2f}%)")
    print(f"  耗時：{time.time()-t0:.1f}s")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())

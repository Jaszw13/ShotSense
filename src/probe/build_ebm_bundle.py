#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShotSense :: EBM bundle builder
================================
把 `src/train_ebm_and_explain.py` 產出的 EBM 結果（散落在 outputs/ 的多個 CSV 與報告）
收斂成單一 JSON，供 `template.html` 內嵌成展示網頁的 10 / 11 / 12 號卡片。

資料來源（全部為既有產物，本腳本只讀不寫）：
  outputs/ebm_feature_report.md              報告本文（含 58 列形狀判定總表）
  outputs/ebm_shape_metrics.csv              每特徵的 10 項形狀量化指標
  outputs/ebm_term_importances.csv           主效應 + 交互項的重要性
  outputs/ebm_term_shift_train_vs_test.csv   Train/Test 逐項偏移拆解
  outputs/ebm_flat_threshold_sensitivity.csv Flat 門檻敏感度
  outputs/ebm_calibration_by_split.csv       三個時段的校準診斷
  outputs/ebm_kept_features.txt              保留清單
  outputs/ebm_dropped_features.txt           剔除清單（含分類與理由）

產出：
  src/probe/ebm_bundle.json                  內嵌用 JSON（UTF-8、緊湊）

用法：
  /opt/anaconda3/bin/python src/probe/build_ebm_bundle.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
DEST = Path(__file__).resolve().parent / "ebm_bundle.json"


def log(msg: str) -> None:
    print(f"[ebm-bundle] {msg}", flush=True)


def read_csv(name: str) -> list[dict]:
    path = OUT / name
    if not path.exists():
        log(f"!! 缺少 {name}，略過")
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return f


def read_text(name: str) -> str:
    path = OUT / name
    if not path.exists():
        log(f"!! 缺少 {name}")
        return ""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 形狀判定總表 —— 從報告的 markdown 表格解析
#    格式：| 1 | `action_type` | Non-linear | 15.51% | **Keep** |  | 理由 |
# ---------------------------------------------------------------------------
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)%\s*\|"
    r"\s*\*\*([A-Za-z]+)\*\*\s*\|\s*([^|]*?)\s*\|\s*(.*?)\s*\|\s*$"
)


def parse_decision_table(report: str) -> list[dict]:
    rows = []
    for line in report.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        rank, feature, cls, share, action, flag, reason = m.groups()
        rows.append(
            {
                "rank": int(rank),
                "feature": feature.strip(),
                "cls": cls.strip(),
                "share": fnum(share),
                "action": action.strip(),
                "flag": bool(flag.strip()),
                "reason": reason.strip(),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 2. 報告中的區塊表格（交互項、共線性、模型對照）
# ---------------------------------------------------------------------------
def parse_simple_table(report: str, header_first_cell: str) -> list[list[str]]:
    """抓出表頭第一格等於 header_first_cell 的那張表，回傳資料列（不含表頭/分隔列）。"""
    lines = report.splitlines()
    out: list[list[str]] = []
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0] != header_first_cell:
            continue
        for nxt in lines[i + 2:]:
            if not nxt.startswith("|"):
                break
            body = [c.strip() for c in nxt.strip().strip("|").split("|")]
            if body and set("".join(body)) <= set("-: "):
                continue
            out.append(body)
        break
    return out


# ---------------------------------------------------------------------------
# 3. 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    report = read_text("ebm_feature_report.md")
    if not report:
        log("找不到 EBM 報告，中止")
        return 1
    log(f"報告：{len(report)/1024:.1f} KB")

    # ---- 形狀判定 ----
    decisions = parse_decision_table(report)
    log(f"形狀判定表：{len(decisions)} 列")
    if len(decisions) != 58:
        log(f"!! 預期 58 列，實得 {len(decisions)} 列（仍繼續）")

    # ---- 形狀量化指標（join 進 decisions）----
    metrics = {}
    exact_share = {}
    for r in read_csv("ebm_shape_metrics.csv"):
        exact_share[r["feature"]] = fnum(r.get("importance_share"), 0.0)
        metrics[r["feature"]] = {
            "stdRatio": fnum(r.get("std_ratio")),
            "flatRange": fnum(r.get("flat_range")),
            "nPts": fnum(r.get("n_pts")),
            "mono": fnum(r.get("monotonicity_index")),
            "rho": fnum(r.get("spearman_rho")),
            "linR2": fnum(r.get("lin_r2")),
            "rough": fnum(r.get("roughness")),
            "osc": fnum(r.get("osc_rate")),
            "isCat": str(r.get("is_categorical", "")).strip().lower() == "true",
        }
    for d in decisions:
        m = metrics.get(d["feature"], {})
        d["mono"] = m.get("mono")
        d["rho"] = m.get("rho")
        d["linR2"] = m.get("linR2")
        d["rough"] = m.get("rough")
        d["osc"] = m.get("osc")
        d["stdRatio"] = m.get("stdRatio")
        d["isCat"] = m.get("isCat", False)
    log(f"形狀指標 join：{len(metrics)} 個特徵")

    # ---- 形狀分類彙總 ----
    # 用 shape_metrics 的未四捨五入 importance_share 加總，避免逐列 2 位小數的累積誤差
    agg: dict[str, dict] = {}
    for d in decisions:
        a = agg.setdefault(d["cls"], {"cls": d["cls"], "n": 0, "share": 0.0, "keep": 0})
        a["n"] += 1
        a["share"] += exact_share.get(d["feature"], 0.0)
        if d["action"] == "Keep":
            a["keep"] += 1
    shape_classes = sorted(agg.values(), key=lambda a: -a["share"])
    for a in shape_classes:
        a["share"] = round(a["share"], 4)
    log(f"形狀分類：{[(a['cls'], a['n']) for a in shape_classes]}")

    # ---- 交互項 ----
    interactions = []
    for r in read_csv("ebm_term_importances.csv"):
        if r.get("kind", "").strip() != "interaction":
            continue
        interactions.append(
            {
                "name": r["term_name"].strip(),
                "importance": fnum(r.get("importance"), 0.0),
                "share": fnum(r.get("importance_share"), 0.0),
                "nBins": int(fnum(r.get("n_bins"), 0)),
            }
        )
    interactions.sort(key=lambda x: -x["importance"])
    log(f"交互項：{len(interactions)} 個")

    # ---- 逐項偏移 ----
    shift = []
    for r in read_csv("ebm_term_shift_train_vs_test.csv"):
        shift.append(
            {
                "term": r["term"].strip(),
                "train": fnum(r.get("train_mean"), 0.0),
                "test": fnum(r.get("test_mean"), 0.0),
                "shift": fnum(r.get("shift"), 0.0),
                "share": fnum(r.get("abs_shift_share"), 0.0),
            }
        )
    shift.sort(key=lambda x: -abs(x["share"] or 0))
    shift_top = shift[:14]
    log(f"偏移項：{len(shift)} 個，取前 {len(shift_top)}")

    # ---- 校準 ----
    calibration = []
    for r in read_csv("ebm_calibration_by_split.csv"):
        calibration.append(
            {
                "split": r["split"].strip(),
                "n": int(fnum(r.get("n"), 0)),
                "actual": fnum(r.get("actual")),
                "pred": fnum(r.get("pred")),
                "bias": fnum(r.get("bias")),
                "auc": fnum(r.get("AUC")),
                "logloss": fnum(r.get("LogLoss")),
                "ece": fnum(r.get("ECE")),
            }
        )
    log(f"校準：{len(calibration)} 個時段")

    # ---- 門檻敏感度 ----
    sensitivity = []
    for r in read_csv("ebm_flat_threshold_sensitivity.csv"):
        sensitivity.append(
            {
                "threshold": fnum(r.get("flat_threshold")),
                "nKept": int(fnum(r.get("n_kept"), 0)),
                "auc": fnum(r.get("AUC")),
                "logloss": fnum(r.get("LogLoss")),
                "brier": fnum(r.get("Brier")),
            }
        )
    log(f"門檻敏感度：{len(sensitivity)} 列")

    # ---- 共線性（報告第 5 節，列出前 20 組）----
    collinearity = []
    for row in parse_simple_table(report, "特徵 A"):
        if len(row) < 3:
            continue
        a, b, rho = row[0].strip("`"), row[1].strip("`"), row[2]
        collinearity.append({"a": a, "b": b, "rho": fnum(rho.replace("+", ""))})
    n_collin = len(collinearity)
    m = re.search(r"偵測到\s*(\d+)\s*組", report)
    if m:
        n_collin = int(m.group(1))
    log(f"共線性：列出來 {len(collinearity)} 組（總計 {n_collin} 組）")

    # ---- 保留 / 剔除 ----
    kept = [x.strip() for x in read_text("ebm_kept_features.txt").splitlines() if x.strip()]
    dropped_raw = [x for x in read_text("ebm_dropped_features.txt").splitlines() if x.strip()]
    dropped = []
    for line in dropped_raw:
        parts = line.split("\t")
        dropped.append({"feature": parts[0].strip(), "cls": parts[1].strip() if len(parts) > 1 else "",
                        "reason": parts[2].strip() if len(parts) > 2 else ""})
    log(f"保留 {len(kept)} / 剔除 {len(dropped)}")

    # ---- 頭對頭指標（取自報告第 1、6 節的表格）----
    models = [
        {"id": "ebm58", "label": "EBM · 58", "kind": "white", "nFeat": 58},
        {"id": "ebm23", "label": "EBM · 23", "kind": "white", "nFeat": 23},
        {"id": "lr23", "label": "LR · 23", "kind": "white", "nFeat": 23},
        {"id": "xgb58", "label": "XGBoost · 58", "kind": "black", "nFeat": 58},
    ]
    metrics_table = [
        {"key": "auc", "ebm58": 0.7069, "ebm23": 0.7028, "lr23": 0.6875, "xgb58": 0.7191, "dir": "up"},
        {"key": "logloss", "ebm58": 0.6260, "ebm23": 0.6127, "lr23": 0.6245, "xgb58": 0.6011, "dir": "down"},
        {"key": "brier", "ebm58": 0.2183, "ebm23": 0.2129, "lr23": 0.2178, "xgb58": 0.2078, "dir": "down"},
        {"key": "accuracy", "ebm58": 0.6518, "ebm23": None, "lr23": 0.6522, "xgb58": 0.6711, "dir": "up"},
        {"key": "f1", "ebm58": 0.6094, "ebm23": None, "lr23": None, "xgb58": 0.5578, "dir": "up"},
        {"key": "ece", "ebm58": 0.0755, "ebm23": 0.0162, "lr23": None, "xgb58": 0.0047, "dir": "down"},
    ]

    bundle = {
        "meta": {
            "trainN": 73144,
            "testN": 29742,
            "fitN": 61778,
            "validN": 11366,
            "cutoff": "2015-01-21",
            "nFeatures": len(decisions) or 58,
            "nKept": len(kept),
            "nDropped": len(dropped),
            "nInteractions": len(interactions),
            "nCollinear": n_collin,
            "seed": 42,
        },
        "models": models,
        "metrics": metrics_table,
        "calibration": calibration,
        "shift": shift_top,
        "sensitivity": sensitivity,
        "shapeClasses": shape_classes,
        "decisions": decisions,
        "interactions": interactions,
        "collinearity": collinearity,
        "kept": kept,
        "dropped": dropped,
        "report": report,
    }

    DEST.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    log(f"寫出 {DEST.name}（{DEST.stat().st_size/1024:.1f} KB）")
    print()
    print("=" * 78)
    print(f"  EBM bundle：{len(decisions)} 特徵 / 保留 {len(kept)} / 剔除 {len(dropped)}")
    print(f"  交互項 {len(interactions)} · 偏移項前 {len(shift_top)} · 共線性 {n_collin} 組")
    print(f"  報告內嵌 {len(report)/1024:.1f} KB")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下載 Google Fonts 的 woff2 並轉成內嵌用的 @font-face CSS。
產出 src/probe/fonts.css，由 build_probe_dashboard.py 注入 HTML。

只取 latin 子集（中文交給系統字型，避免好幾 MB 的 CJK 字型檔）。
"""
from __future__ import annotations

import base64
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fonts.css"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SPEC = (
    "https://fonts.googleapis.com/css2"
    "?family=Playfair+Display:ital,wght@0,700;0,900;1,700"
    "&family=Inter:wght@400;600;700"
    "&family=JetBrains+Mono:wght@400;700"
    "&display=swap"
)


def fetch(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def main() -> int:
    print("取得 Google Fonts CSS …", flush=True)
    css = fetch(SPEC)

    # 切出每個 @font-face 區塊，只保留 latin 子集（前面帶 /* latin */ 註解的那個）
    blocks = re.findall(r"/\*\s*([a-z\-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css)
    picked = [(sub, blk) for sub, blk in blocks if sub == "latin"]
    print(f"找到 {len(blocks)} 個子集，其中 latin 有 {len(picked)} 個")

    out = ["/* 內嵌 Google Fonts（僅 latin 子集）— 由 src/probe/fetch_fonts.py 產生 */"]
    total = 0
    for sub, blk in picked:
        m = re.search(r"url\((https://[^)]+\.woff2)\)", blk)
        if not m:
            continue
        url = m.group(1)
        fam = re.search(r"font-family:\s*'([^']+)'", blk).group(1)
        wt = re.search(r"font-weight:\s*([0-9]+)", blk).group(1)
        st = re.search(r"font-style:\s*(\w+)", blk)
        st = st.group(1) if st else "normal"
        raw = fetch(url, binary=True)
        total += len(raw)
        b64 = base64.b64encode(raw).decode("ascii")
        print(f"  {fam:<20} {wt:>3} {st:<7} {len(raw)/1024:6.1f} KB")
        out.append(
            f"@font-face{{font-family:'{fam}';font-style:{st};font-weight:{wt};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
            f"unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
            f"U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,"
            f"U+FEFF,U+FFFD;}}"
        )

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n寫出 {OUT}（{OUT.stat().st_size/1024:.1f} KB，字型原始共 {total/1024:.1f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

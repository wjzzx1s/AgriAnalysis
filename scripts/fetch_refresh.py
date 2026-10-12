#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把公司画像数据刷新到报告数据时点（2026-10-12），并补齐「总市值口径」所需的字段。

东财行情接口（push2.eastmoney.com）在本机被拒（403 / RemoteDisconnected），
因此统一走可用通道：

  px        新浪前复权日行情 stock_zh_a_daily(symbol="sh600598")
            → 最新收盘价、总股本（由 share_chg 提供）、近一年涨跌幅
  share_chg 巨潮股本结构 stock_share_change_cninfo(symbol=code)
            → 总股本、控股股东与实际控制人、变动原因
  holders   新浪主要股东 stock_main_stock_holder(stock=code)
            → 最新报告期前十大股东及持股比例（股权结构）
  basic     由 px 计算（收盘价 × 流通股本）→ 流通市值，作对照口径

落盘位置与既有管线一致：data/raw/company/<code>_<kind>.csv。
汇总快照另存 data/raw/company_spot.csv（每家公司一行，总市值口径）。
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW, save  # noqa: E402

SUB = "company"
WORKERS = 3
PX_START = "2021-01-01"


def market_prefix(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    if code.startswith(("43", "83", "87", "92")):
        return "bj"
    return "sh"


def codes() -> list[tuple[str, str]]:
    uni = pd.read_csv(os.path.join(os.path.dirname(RAW), "clean", "sw_stock_industry.csv"),
                      encoding="utf-8-sig", dtype=str)
    l1 = uni[uni["行业层级"] == "一级"][["股票代码", "证券名称"]].drop_duplicates("股票代码")
    return [(str(r["股票代码"]).zfill(6), str(r["证券名称"])) for _, r in l1.iterrows()]


def refresh_one(code: str, name: str) -> dict:
    pref = market_prefix(code)
    out = {"代码": code, "名称": name}
    ok = fail = 0

    # --- 日行情（前复权）→ 最新收盘价 + 近一年涨跌幅 + 流通市值（对照）
    try:
        px = ak.stock_zh_a_daily(symbol=f"{pref}{code}")
        px["date"] = pd.to_datetime(px["date"], errors="coerce")
        px = px.dropna(subset=["date", "close"])
        px = px[px["date"] >= pd.Timestamp(PX_START)]
        save(px, f"{code}_px", f"新浪财经 stock_zh_a_daily({pref}{code})",
             note=name, subdir=SUB, force=True)
        last = px.iloc[-1]
        out["最新收盘"] = float(last["close"])
        out["行情日期"] = str(last["date"])[:10]
        out["流通股本"] = float(last.get("outstanding_share", float("nan")))
        out["流通市值亿元"] = out["最新收盘"] * out["流通股本"] / 1e8
        past = px[px["date"] <= last["date"] - pd.Timedelta(days=365)]
        if len(past):
            out["近一年涨跌%"] = round((out["最新收盘"] / float(past.iloc[-1]["close"]) - 1) * 100, 2)
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"    [FAIL] {code} {name} px: {type(exc).__name__} {str(exc)[:90]}")
        fail += 1

    # --- 股本结构（总股本 + 控股股东/实际控制人）
    try:
        sc = ak.stock_share_change_cninfo(symbol=code)
        save(sc, f"{code}_share_chg", f"巨潮资讯网 stock_share_change_cninfo({code})",
             note=name, subdir=SUB, force=True)
        if "变动日期" in sc.columns:
            s = sc.copy()
            s["变动日期"] = pd.to_datetime(s["变动日期"], errors="coerce")
            s = s.dropna(subset=["变动日期"]).sort_values("变动日期")
            if len(s):
                last = s.iloc[-1]
                out["总股本亿股"] = float(pd.to_numeric(last.get("总股本"), errors="coerce")) / 1e4
                out["股本变动日"] = str(last["变动日期"])[:10]
                if "控股股东、实际控制人" in s.columns:
                    v = s["控股股东、实际控制人"].dropna().astype(str)
                    v = v[v.str.strip() != ""]
                    if len(v):
                        out["控股股东或实控人"] = v.iloc[-1].strip()
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"    [FAIL] {code} {name} share_chg: {type(exc).__name__} {str(exc)[:90]}")
        fail += 1

    # --- 主要股东（股权结构：最新报告期前十大股东）
    try:
        hd = ak.stock_main_stock_holder(stock=code)
        save(hd, f"{code}_holders", f"新浪财经 stock_main_stock_holder({code})",
             note=name, subdir=SUB, force=True)
        if len(hd) and "截至日期" in hd.columns:
            h = hd.copy()
            h["截至日期"] = pd.to_datetime(h["截至日期"], errors="coerce")
            h = h.dropna(subset=["截至日期"])
            if len(h):
                latest = h["截至日期"].max()
                top = h[h["截至日期"] == latest].copy()
                top["持股比例"] = pd.to_numeric(top.get("持股比例"), errors="coerce")
                top["编号"] = pd.to_numeric(top.get("编号"), errors="coerce")
                # 接口返回的“编号”即官方前十大股东排序，必须按编号排列：
                # 部分公司（如益生股份）第 1 大股东的比例字段为空，按比例排序会把
                # 第 4 大股东误当成第一大股东
                top = top.sort_values("编号", na_position="last")
                out["股权期次"] = str(latest)[:10]
                out["前三大股东"] = "；".join(
                    f"{str(r['股东名称'])[:26]}("
                    + (f"{r['持股比例']:.2f}%" if pd.notna(r["持股比例"]) else "—")
                    + ")" for _, r in top.head(3).iterrows())
                if "股东总数" in top.columns and len(top):
                    out["股东户数"] = pd.to_numeric(top["股东总数"], errors="coerce").iloc[0]
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"    [FAIL] {code} {name} holders: {type(exc).__name__} {str(exc)[:90]}")
        fail += 1

    return out, ok, fail


def rebuild_from_cache() -> pd.DataFrame:
    """不改动原始文件，仅用已有的 _px/_share_chg/_holders 重建公司快照（幂等）。"""
    rows = []
    for code, name in codes():
        out = {"代码": code, "名称": name}
        try:
            px = pd.read_csv(os.path.join(RAW, SUB, f"{code}_px.csv"),
                             encoding="utf-8-sig", dtype={"date": str})
            px["date"] = pd.to_datetime(px["date"], errors="coerce")
            px = px.dropna(subset=["date", "close"]).sort_values("date")
            last = px.iloc[-1]
            out["最新收盘"] = float(last["close"])
            out["行情日期"] = str(last["date"])[:10]
            out["流通股本"] = float(pd.to_numeric(last.get("outstanding_share"), errors="coerce"))
            out["流通市值亿元"] = out["最新收盘"] * out["流通股本"] / 1e8
            past = px[px["date"] <= last["date"] - pd.Timedelta(days=365)]
            if len(past):
                out["近一年涨跌%"] = round((out["最新收盘"] / float(past.iloc[-1]["close"]) - 1) * 100, 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            sc = pd.read_csv(os.path.join(RAW, SUB, f"{code}_share_chg.csv"),
                             encoding="utf-8-sig")
            sc["变动日期"] = pd.to_datetime(sc["变动日期"], errors="coerce")
            sc = sc.dropna(subset=["变动日期"]).sort_values("变动日期")
            last = sc.iloc[-1]
            out["总股本亿股"] = float(pd.to_numeric(last.get("总股本"), errors="coerce")) / 1e4
            out["股本变动日"] = str(last["变动日期"])[:10]
        except Exception:  # noqa: BLE001
            pass
        try:
            hd = pd.read_csv(os.path.join(RAW, SUB, f"{code}_holders.csv"), encoding="utf-8-sig")
            hd["截至日期"] = pd.to_datetime(hd["截至日期"], errors="coerce")
            hd = hd.dropna(subset=["截至日期"])
            latest = hd["截至日期"].max()
            top = hd[hd["截至日期"] == latest].copy()
            top["持股比例"] = pd.to_numeric(top["持股比例"], errors="coerce")
            top["编号"] = pd.to_numeric(top.get("编号"), errors="coerce")
            top = top.sort_values("编号", na_position="last")
            out["股权期次"] = str(latest)[:10]
            out["前三大股东"] = "；".join(
                f"{str(r['股东名称'])[:26]}("
                + (f"{r['持股比例']:.2f}%" if pd.notna(r["持股比例"]) else "—")
                + ")" for _, r in top.head(3).iterrows())
            if "股东总数" in top.columns and len(top):
                out["股东户数"] = pd.to_numeric(top["股东总数"], errors="coerce").iloc[0]
        except Exception:  # noqa: BLE001
            pass
        if "总股本亿股" in out and "最新收盘" in out:
            out["总市值亿元"] = out["最新收盘"] * out["总股本亿股"]
        rows.append(out)
    return pd.DataFrame(rows).sort_values("代码")


def main() -> None:
    if "--from-cache" in sys.argv:
        spot = rebuild_from_cache()
        save(spot, "company_spot", "新浪日行情 × 巨潮股本结构（总市值 = 最新收盘价 × 总股本）",
             note="报告数据时点快照（总市值口径，由本地缓存重建）", force=True)
        print(f"[fetch_refresh] 重建快照：总市值可算 {int(spot['总市值亿元'].notna().sum())}/{len(spot)}")
        if "行情日期" in spot.columns:
            print("  行情日期：", sorted(spot["行情日期"].dropna().unique())[:3])
        if "股权期次" in spot.columns:
            print("  股权结构期次：", sorted(spot["股权期次"].dropna().unique())[:5])
        return
    cl = codes()
    print(f"刷新公司数：{len(cl)}")
    rows, ok, fail = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(refresh_one, c, n): c for c, n in cl}
        done = 0
        for f in as_completed(futs):
            try:
                rec, o, fl = f.result()
            except Exception as exc:  # noqa: BLE001
                print(f"    [EXC] {futs[f]}: {type(exc).__name__} {exc}")
                rec, o, fl = {"代码": futs[f]}, 0, 1
            rows.append(rec)
            ok += o
            fail += fl
            done += 1
            if done % 10 == 0:
                print(f"    进度 {done}/{len(cl)} ok={ok} fail={fail}")
            time.sleep(0.05)

    spot = pd.DataFrame(rows).sort_values("代码")
    if "总股本亿股" in spot.columns and "最新收盘" in spot.columns:
        spot["总市值亿元"] = spot["最新收盘"] * spot["总股本亿股"]
    save(spot, "company_spot", "新浪日行情 × 巨潮股本结构（总市值 = 最新收盘价 × 总股本）",
         note="报告数据时点快照（总市值口径）", force=True)
    n_have = int(spot["总市值亿元"].notna().sum()) if "总市值亿元" in spot.columns else 0
    print(f"[fetch_refresh] ok={ok} fail={fail} 总市值可算 {n_have}/{len(spot)}")
    print(f"  行情日期：{spot['行情日期'].dropna().unique()[:3] if '行情日期' in spot.columns else '—'}")
    print(f"  股权结构期次：{spot['股权期次'].dropna().unique()[:3] if '股权期次' in spot.columns else '—'}")


if __name__ == "__main__":
    main()

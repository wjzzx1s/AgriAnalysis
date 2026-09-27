#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""公用工具：带重试的 akshare 抓取、原始数据落盘与抓取清单（manifest）维护。"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import uuid
import traceback

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CLEAN = os.path.join(ROOT, "data", "clean")
NOTES = os.path.join(ROOT, "notes")
MANIFEST = os.path.join(RAW, "_manifest.json")

for _d in (RAW, CLEAN, NOTES):
    os.makedirs(_d, exist_ok=True)


def _load_manifest() -> dict:
    """读取抓取清单。清单只是元数据，任何损坏都不得中断数据落盘：
    编码异常 / JSON 损坏时把坏文件改名保存并返回空清单重新开始。"""
    if not os.path.exists(MANIFEST):
        return {}
    try:
        with open(MANIFEST, "rb") as fh:
            raw = fh.read()
    except OSError:
        return {}
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    # 彻底损坏（多进程并发写入可能写出撕裂文件）：隔离后重建
    bad = f"{MANIFEST}.bad{int(time.time())}"
    try:
        os.replace(MANIFEST, bad)
        print(f"    [WARN] 抓取清单损坏，已备份为 {os.path.basename(bad)} 并重建")
    except OSError:
        pass
    return {}


def _save_manifest(man: dict) -> None:
    """原子写清单：临时文件名带 pid + 随机后缀，且写失败绝不影响数据落盘。"""
    tmp = f"{MANIFEST}.tmp{os.getpid()}.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(man, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, MANIFEST)
    except OSError as exc:
        # 清单只是元数据：多进程并发或磁盘异常时不得中断抓取
        print(f"    [WARN] 清单写入失败（不影响数据）：{type(exc).__name__}: {exc}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def fetch(fn, *args, retries: int = 3, sleep: float = 2.0, quiet: bool = False, **kwargs):
    """调用 akshare 接口，失败重试；全部失败返回 None 并打印原因。"""
    last = None
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < retries - 1:
                time.sleep(sleep * (i + 1))
    if not quiet:
        print(f"    [FAIL] {getattr(fn, '__name__', fn)} {args} {kwargs} -> "
              f"{type(last).__name__}: {str(last)[:150]}")
    return None


def save(df, name: str, source: str, note: str = "", force: bool = False,
         subdir: str = "") -> bool:
    """保存为 data/raw/<name>.csv 并登记 manifest。已存在则跳过（除非 force）。"""
    target_dir = os.path.join(RAW, subdir) if subdir else RAW
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"{name}.csv")
    key = os.path.relpath(path, RAW)
    if df is None:
        return False
    if os.path.exists(path) and not force:
        return True
    if isinstance(df, pd.DataFrame):
        df.to_csv(path, index=False, encoding="utf-8-sig")
        rows, cols = len(df), list(df.columns)
    else:
        pd.DataFrame(df).to_csv(path, index=False, encoding="utf-8-sig")
        rows, cols = len(df), []
    man = _load_manifest()
    man[key] = {
        "source": source,
        "note": note,
        "rows": rows,
        "columns": [str(c) for c in cols][:40],
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_manifest(man)
    return True


def exists(name: str, subdir: str = "") -> bool:
    return os.path.exists(os.path.join(RAW, subdir if subdir else "", f"{name}.csv"))


def load_raw(name: str, subdir: str = "") -> pd.DataFrame | None:
    path = os.path.join(RAW, subdir if subdir else "", f"{name}.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def norm_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(r"\.0$", "", regex=True),
                          format="mixed", errors="coerce")


def report(script: str, ok: int, fail: int, extra: str = "") -> None:
    print(f"[{script}] saved/ok={ok} failed={fail} {extra}")


def guard(script: str):
    """装饰 main：捕获异常并打印，避免一条链路挂掉整个批处理。"""
    def deco(fn):
        def wrapper(*a, **kw):
            try:
                fn(*a, **kw)
            except Exception:  # noqa: BLE001
                print(f"[{script}] EXCEPTION\n{traceback.format_exc()}")
        return wrapper
    return deco

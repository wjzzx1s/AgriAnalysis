#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""事实底稿的来源 URL 可达性自检。

对 data/facts/*.yaml 中出现的每个唯一 URL 发一次请求（先 HEAD，失败再 GET），
按状态分类并把结果写到 notes/url_check.txt：

  OK        2xx（少数站点不接受 HEAD，用 GET 复核）
  DEAD      404 / 410 / 域名解析失败 / 连接失败
  BLOCKED   401 / 403 / 429 / 5xx（站点反爬或需登录，不能据此判定内容不存在）

DEAD 的条目需要人工复核；BLOCKED 保留（很多公告站点对脚本请求返回 403）。
"""
from __future__ import annotations

import glob
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_BY_CODE: dict[str, list[str]] = {}
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126 Safari/537.36"}


def collect() -> dict[str, list[str]]:
    urls: dict[str, list[str]] = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "facts", "*.yaml"))):
        code = os.path.basename(f)[:6]
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("来源", "来源URL", "url") and isinstance(v, str) and v.startswith("http"):
                        urls.setdefault(v.strip(), []).append(code)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        try:
            walk(yaml.safe_load(open(f, encoding="utf-8")) or {})
        except yaml.YAMLError:
            print(f"    [WARN] 解析失败 {code}")
    return urls


def check(url: str) -> tuple[str, str]:
    for method in ("head", "get"):
        try:
            r = requests.request(method, url, headers=HEADERS, timeout=20, allow_redirects=True,
                                 stream=(method == "get"))
            if r.status_code < 300:
                return url, "OK"
            if r.status_code in (401, 403, 405, 429) or r.status_code >= 500:
                if method == "head":
                    continue
                return url, "BLOCKED"
            if method == "head":
                continue
            return url, "DEAD"
        except Exception as exc:  # noqa: BLE001
            if method == "get":
                return url, f"DEAD({type(exc).__name__})"
    return url, "BLOCKED"


def main() -> None:
    urls = collect()
    print(f"唯一来源 URL：{len(urls)}")
    res: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(check, u) for u in urls]
        done = 0
        for f in as_completed(futs):
            u, st = f.result()
            res[u] = st
            done += 1
            if done % 100 == 0:
                print(f"  已检查 {done}/{len(urls)}")
    dead = {u: s for u, s in res.items() if s.startswith("DEAD")}
    blocked = {u: s for u, s in res.items() if s == "BLOCKED"}
    out = os.path.join(ROOT, "notes", "url_check.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"# 事实底稿来源 URL 可达性自检\n\n唯一 URL {len(urls)} 条：OK "
                 f"{len(res) - len(dead) - len(blocked)}、BLOCKED {len(blocked)}、DEAD {len(dead)}\n\n")
        fh.write("## DEAD（需复核，可能需从底稿中删除）\n")
        for u, s in sorted(dead.items()):
            fh.write(f"- [{s}] {u}  （{','.join(sorted(set(CHECK_BY_CODE.get(u, []))))}）\n")
        fh.write("\n## BLOCKED（反爬/需登录，保留）\n")
        for u in sorted(blocked):
            fh.write(f"- {u}\n")
    print(f"DEAD {len(dead)}、BLOCKED {len(blocked)} → {out}")


if __name__ == "__main__":
    sys.exit(main())

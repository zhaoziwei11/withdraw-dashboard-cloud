#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键补触发云端定时任务（无需打开 GitHub 网页）。

前置条件：fine-grained token 已加 Actions: Read and write 权限
  GitHub → Settings → Developer settings → Fine-grained tokens → wd
  → Repository permissions → Actions: Read and write

用法：
  python sync/trigger_cloud.py morning       # 早间 09:07 同步(跑 --pending)
  python sync/trigger_cloud.py afternoon     # 午间 15:15 同步(跑 --fail --demand2)
  python sync/trigger_cloud.py               # 默认 afternoon

token 读取顺序：环境变量 GH_TOKEN > 同目录 .gh_token(不入库)
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "zhaoziwei11/withdraw-dashboard-cloud"
BRANCH = "main"
_HERE = Path(__file__).resolve().parent


def load_token() -> str:
    t = (os.environ.get("GH_TOKEN") or "").strip()
    if t:
        return t
    for p in (_HERE / ".gh_token", Path(".gh_token")):
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    sys.stderr.write("[FAIL] 未找到 token：请设置环境变量 GH_TOKEN 或放置 sync/.gh_token\n")
    sys.exit(1)


def trigger(which: str):
    wf = f"{which}.yml"
    token = load_token()
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches"
    data = json.dumps({"ref": BRANCH}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "wb-trigger")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"[OK] 已触发 {which}（HTTP {r.status}）。稍后到 workbench 刷新看数据。")
            return 0
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:400]
        except Exception:
            pass
        print(f"[FAIL] HTTP {e.code}：{body}")
        if e.code in (401, 403):
            print("  → 多半是 token 缺少 Actions: Read and write 权限，请按前置条件加上。")
        return 1


if __name__ == "__main__":
    which = (sys.argv[1] if len(sys.argv) > 1 else "afternoon").lower()
    if which not in ("morning", "afternoon"):
        print("用法: trigger_cloud.py [morning|afternoon]")
        sys.exit(2)
    sys.exit(trigger(which))

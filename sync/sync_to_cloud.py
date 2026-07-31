#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本机同步脚本：抓取 8766 控制台(/api/* )的当前数据，写入 Supabase，
供云端看板(withdraw-dashboard-cloud)读取展示。

运行前提（在本机，且 8766 服务在跑）：
    python sync/sync_to_cloud.py

使用 Python 标准库 urllib 实现，无需额外安装 requests。
写入使用 anon key（公开可读写，已在 schema.sql 放开匿名插入）。
若本机 8766 未运行（所有接口无有效数据），则跳过推送，保留云端上一条。
"""
import datetime
import json
import urllib.request
import urllib.error

SUPABASE_URL = "https://kbelxtwmqfbkrbrnetzzm.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtiZWx4dHdtcWZia3JibmV0enptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyMjg2MTIsImV4cCI6MjEwMDgwNDYxMn0.VWHOrivhqd3NlFBGAXakdGWKbGhSnZ79GpLVYPZXDq0"

LOCAL_BASE = "http://127.0.0.1:8766"
ENDPOINTS = [
    "report", "history", "predict", "coefficient",
    "coefficients_auto", "forecast_diff", "settings", "status", "preview_ranges",
]


def _http(method, url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fetch_local():
    payload = {}
    for ep in ENDPOINTS:
        try:
            body = _http("GET", f"{LOCAL_BASE}/api/{ep}", timeout=10)
            payload[ep] = json.loads(body) if body else None
            print(f"  \u2713 {ep} ({len(body)} bytes)")
        except urllib.error.HTTPError as e:
            payload[ep] = None
            print(f"  ! {ep} HTTP {e.code}")
        except Exception as e:
            payload[ep] = None
            print(f"  ! {ep} \u5931\u8d25: {e}")
    return payload


def push(payload):
    row = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "payload": payload,
    }
    body = json.dumps(row).encode("utf-8")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        _http("POST", f"{SUPABASE_URL}/rest/v1/withdraw_reports", data=body, headers=headers, timeout=20)
        print("\u2713 \u5df2\u540c\u6b65\u5230\u4e91\u7aef Supabase")
    except Exception as e:
        print(f"\u2717 \u540c\u6b65\u5931\u8d25: {e}")


if __name__ == "__main__":
    print("\u6293\u53d6\u672c\u673a 8766 \u6570\u636e\u2026")
    payload = fetch_local()
    if not any(v is not None for v in payload.values()):
        print("\u2717 \u672c\u673a 8766 \u65e0\u6709\u6548\u6570\u636e\uff08\u670d\u52a1\u672a\u8fd0\u884c\uff1f\uff09\uff0c\u8df3\u8fc7\u63a8\u9001\uff0c\u4fdd\u7559\u4e91\u7aef\u4e0a\u4e00\u6761\u3002")
    else:
        push(payload)
    print("\u5b8c\u6210\u3002")

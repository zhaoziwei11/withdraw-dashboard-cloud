#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本机同步脚本：抓取 8766 控制台(/api/* )的当前数据，写入 Supabase，
供云端看板(withdraw-dashboard-cloud)读取展示。

运行前提（在本机，且 8766 服务在跑）：
    pip install requests
    python sync/sync_to_cloud.py

写入使用 anon key（公开可读写，已在 schema.sql 放开匿名插入）。
如需更安全，把 SUPABASE_ANON_KEY 换成 service_role key 并收紧策略。
"""
import datetime
import requests

SUPABASE_URL = "https://kbelxtwmqfbkrbrnetzzm.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtiZWx4dHdtcWZia3JibmV0enptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyMjg2MTIsImV4cCI6MjEwMDgwNDYxMn0.VWHOrivhqd3NlFBGAXakdGWKbGhSnZ79GpLVYPZXDq0"

LOCAL_BASE = "http://127.0.0.1:8766"
ENDPOINTS = [
    "report", "history", "predict", "coefficient",
    "coefficients_auto", "forecast_diff", "settings", "status", "preview_ranges",
]


def fetch_local():
    payload = {}
    for ep in ENDPOINTS:
        try:
            r = requests.get(f"{LOCAL_BASE}/api/{ep}", timeout=10)
            payload[ep] = r.json() if r.ok else None
            print(f"  ✓ {ep} ({len(str(payload[ep]))} bytes)")
        except Exception as e:
            payload[ep] = None
            print(f"  ! {ep} 失败: {e}")
    return payload


def push(payload):
    row = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "payload": payload,
    }
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    r = requests.post(f"{SUPABASE_URL}/rest/v1/withdraw_reports", json=row, headers=headers, timeout=15)
    if r.status_code in (200, 201, 204):
        print("✓ 已同步到云端 Supabase")
    else:
        print(f"✗ 同步失败 HTTP {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    print("抓取本机 8766 数据…")
    payload = fetch_local()
    push(payload)
    print("完成。")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端编排器（由 GitHub Actions 调用）：
  1. 启动本地 8766 控制台（dashboard.py，纯标准库 http.server，聚合 /api）
  2. 运行 withdraw_report.py 抓取（morning=--pending / afternoon=--fail --demand2）
  3. 显式调用 sync/sync_to_cloud.py 把数据推到本仓库 data/dashboard.json（GitHub Contents API）
  4. 关闭控制台

环境变量（由 workflow 注入）：
  CW_USER / CW_PASS   登录账号密码（启发式自动登录）
  CW_CHANNEL          浏览器通道，云端留空用 chromium
  GH_TOKEN            写入仓库用的 token（GitHub Actions 自带 GITHUB_TOKEN）
"""
import os
import sys
import time
import subprocess
import urllib.request

PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"


def wait_port(timeout=90):
    for _ in range(timeout):
        try:
            urllib.request.urlopen(f"{BASE}/api/status", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"
    fetch_args = ["--fail", "--demand2"] if mode == "afternoon" else ["--pending"]

    exe = sys.executable
    here = os.path.dirname(os.path.abspath(__file__))

    # 1) 启动本地控制台
    print(f"[run] 启动控制台 {BASE} ...")
    dash = subprocess.Popen([exe, "dashboard.py"], cwd=here)
    if not wait_port():
        print("[run] 控制台启动失败，终止")
        dash.terminate()
        sys.exit(1)
    print("[run] 控制台已就绪")

    # 2) 抓取（结束后 withdraw_report.py 也会后台触发一次 sync，这里再显式跑一次确保成功）
    try:
        subprocess.run([exe, "withdraw_report.py", *fetch_args], cwd=here, check=True)
        print("[run] 抓取完成")
    except subprocess.CalledProcessError as e:
        print(f"[run] 抓取失败（非致命，仍尝试同步已有数据）: {e}")

    # 3) 显式推送（确保控制台在线时完成）
    time.sleep(3)
    try:
        subprocess.run([exe, "sync/sync_to_cloud.py"], cwd=here, timeout=120)
        print("[run] 同步完成")
    except Exception as e:
        print(f"[run] 同步异常: {e}")

    # 4) 关闭控制台
    try:
        dash.terminate()
    except Exception:
        pass
    print("[run] 全部完成")


if __name__ == "__main__":
    main()

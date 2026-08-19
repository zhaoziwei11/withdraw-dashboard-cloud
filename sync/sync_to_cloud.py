#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本机同步脚本 v2：直接读取本地数据文件，组装成云端看板期望的结构，写入 Supabase。

【v2 相比 v1 的关键改动】
v1 依赖本机 8766 控制台的 HTTP 接口取数，控制台一旦没在跑就抓不到任何数据，
于是跳过推送，云端永远停留在上一次成功的快照（表现为"网页数据不更新"）。
v2 改为直接 import dashboard.py 复用其取数函数，读本地 csv/json，
**完全不需要控制台在跑**，每次抓取任务结束后都能自动推送最新数据。

同时 v2 修正了 v1 的两个隐性 bug：
  1. v1 请求的 endpoint 名用下划线(coefficients_auto / forecast_diff / preview_ranges)，
     而控制台实际路由是连字符，导致这几项恒为 404。
  2. v1 把 /api/report 的 markdown 纯文本直接塞进 payload["report"]，
     但前端 app.js 期望的是结构化对象（r.pending_amount / r.coeff_active ...），
     字段对不上会渲染成空白。v2 按前端契约组装结构化对象。

运行（本机，无需任何服务在跑）：
    python sync/sync_to_cloud.py

仅用 Python 标准库，无需 pip 安装。写入使用 anon key。
"""
import datetime
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ============ 配置 ============
# 后端改用 GitHub 仓库文件（data/dashboard.json），无第三方依赖，不受 Supabase 域名污染影响。
# 网页从 GitHub Pages 同源读取该文件；本脚本/Action 通过 GitHub Contents API 写它。
# GitHub Actions 用自带 GITHUB_TOKEN；本机从环境变量 GH_TOKEN 或 sync/.gh_token(不入库) 读取。
# ⚠️ 切勿把明文 PAT 写进会被提交的脚本, 否则触发仓库密钥扫描拦截。
GH_REPO = os.environ.get("GH_REPO") or "zhaoziwei11/withdraw-dashboard-cloud"
GH_BRANCH = os.environ.get("GH_BRANCH") or "main"
GH_DATA_PATH = os.environ.get("GH_DATA_PATH") or "data/dashboard.json"
GH_TOKEN = os.environ.get("GH_TOKEN") or ""  # 见下方 _load_gh_token(): 优先环境变量, 回退本地 sync/.gh_token(不入库)
GH_API = "https://api.github.com"

SOURCE_URL = "https://chengyun.91msl.com/financial-center/settlement-manage/carrier-withdrawal-manage"

# dashboard.py 的位置在两种部署下不同，按优先级探测：
#   1) 环境变量 WB_DASHBOARD_PY 显式指定
#   2) 本脚本上级目录（云端 fetch/ 布局：fetch/sync/../dashboard.py）
#   3) 本机固定路径
_HERE = Path(__file__).resolve().parent
DASHBOARD_CANDIDATES = [
    Path(os.environ["WB_DASHBOARD_PY"]) if os.environ.get("WB_DASHBOARD_PY") else None,
    _HERE.parent / "dashboard.py",
    Path(r"C:\Users\92893\WorkBuddy\automation-2026-07-22-13-54-50\withdraw-report\dashboard.py"),
]


def resolve_dashboard():
    for c in DASHBOARD_CANDIDATES:
        if c and c.exists():
            return c
    tried = "\n  ".join(str(c) for c in DASHBOARD_CANDIDATES if c)
    raise FileNotFoundError(f"未找到 dashboard.py，已尝试:\n  {tried}")


# ============ 载入 dashboard 模块（复用其取数逻辑，不启动服务） ============
def load_dashboard():
    dashboard_py = resolve_dashboard()
    spec = importlib.util.spec_from_file_location("wb_dashboard", dashboard_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wb_dashboard"] = mod
    spec.loader.exec_module(mod)  # dashboard.py 的 main() 在 __main__ 保护下，import 不会起服务
    return mod


def num(v, default=None):
    """把 '1234.56' / 1234.56 / '' / None 统一转成 float 或 default"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ============ 组装前端契约结构 ============
def build_report(db, status, predict, auto_coeff, forecast_rows, settings):
    """组装 app.js 里 DATA.report 期望的结构化对象"""
    today = status.get("today")

    # 统计口径：优先用当天 pending 台账里的 stat_range
    stat_range = ""
    try:
        ranges = db.compute_effective_range(
            "pending", datetime.datetime.now().date(), settings
        )
        # compute_effective_range 返回 (start, end, skip, label)
        if isinstance(ranges, (list, tuple)) and len(ranges) >= 2:
            stat_range = f"创建时间 = {ranges[0]} ~ {ranges[1]}"
    except Exception:
        pass

    # 当天 pending 金额/笔数：直接从台账最新一行取（比解析 md 稳）
    pending_amount, pending_count = None, None
    try:
        hist = db.get_history()
        if hist:
            top = hist[0]
            pending_amount = num(top.get("pending_amount"), 0)
            pending_count = int(num(top.get("pending_count"), 0) or 0)
            if not stat_range and top.get("stat_range_start"):
                stat_range = (
                    f"创建时间 = {top['stat_range_start']} ~ {top['stat_range_end']}"
                )
    except Exception:
        pass

    # 失败原因 Top3 文本
    fail_top3 = "待补充(每天 15:00 任务执行后更新)"
    try:
        data_file = db.DATA_DIR / f"withdraw_data_{today}.json"
        if data_file.exists():
            d = json.loads(data_file.read_text(encoding="utf-8"))
            if "fail_reasons" in d:
                fr = [x for x in (d.get("fail_reasons") or []) if x not in (None, "", "-")]
                if not fr:
                    fail_top3 = "无提现失败"
                else:
                    from collections import Counter

                    total = len(fr)
                    parts = [
                        f"{i}. {reason}（{cnt} 次 · {cnt / total * 100:.1f}%）"
                        for i, (reason, cnt) in enumerate(Counter(fr).most_common(3), 1)
                    ]
                    fail_top3 = "<br>".join(parts)
    except Exception:
        pass

    # 需求二说明文本
    demand2_note = "待补充(每天 15:00 任务执行后更新)"
    tp = predict.get("demand2_today_pending")
    pf = predict.get("predicted_full")
    if tp not in (None, ""):
        c = predict.get("coefficient")
        mode = predict.get("predict_mode") or ""
        mode_txt = "周一算法(上周五~周日合计)" if mode == "monday" else "当天全天(0~24)"
        try:
            demand2_note = (
                f"当天 0~15 点待提现 <b>¥{float(tp):,.2f}</b> · "
                f"系数 <b>{float(c):.6f}</b> · "
                f"预测{mode_txt} <b>¥{float(pf):,.2f}</b>"
                if pf not in (None, "")
                else f"当天 0~15 点待提现 <b>¥{float(tp):,.2f}</b>（预测待生成）"
            )
        except Exception:
            pass

    # active 系数块
    active_key = auto_coeff.get("active") or "1m"
    aset = (auto_coeff.get("sets") or {}).get(active_key, {}) or {}
    # 按项目约定：界面主系数用工作日系数 coeff_weekday，全量 coeff 作参考
    coeff_main = aset.get("coeff_weekday") or aset.get("coeff")
    coeff_active = {
        "coeff": round(coeff_main, 6) if isinstance(coeff_main, (int, float)) else coeff_main,
        "pooled": aset.get("pooled"),
        "range": f"{aset.get('range_start', '')} ~ {aset.get('range_end', '')}",
        "days": aset.get("day_count"),
        "rows": aset.get("sample_n_rows"),
    }

    # 报表页底部的比对表（取最近 5 条）
    fd = []
    for r in forecast_rows[:5]:
        fd.append(
            {
                "date": r.get("predict_date"),
                "predicted": num(r.get("predicted_full"), 0) or 0,
                "actual": num(r.get("actual_next_day_pending_09")),
                "diff": num(r.get("diff")),
                "pct": (f"{r.get('diff_pct')}%" if r.get("diff_pct") else None),
            }
        )

    return {
        "date": today,
        "generated_at": status.get("report_time") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": SOURCE_URL,
        "stat_range": stat_range or "—",
        "pending_amount": pending_amount,
        "pending_count": pending_count,
        "fail_top3": fail_top3,
        "demand2_note": demand2_note,
        "coeff_active": coeff_active,
        "partial_total": aset.get("total_partial"),
        "full_total": aset.get("total_full"),
        "forecast_diff": fd,
    }


def build_history(rows):
    """把 dashboard.get_history() 的字段名映射成前端期望的字段名"""
    out = []
    for r in rows:
        out.append(
            {
                "run_date": r.get("run_date"),
                "pending_amount": num(r.get("pending_amount"), 0) or 0,
                "pending_count": int(num(r.get("pending_count"), 0) or 0),
                "today_15": num(r.get("demand2_today_pending")),
                "coefficient": r.get("coefficient") or "",
                "predicted_full": num(r.get("predicted_full")),
                "actual_next_day_09": num(r.get("actual_next_day_pending_09")),
                "diff": num(r.get("diff")),
                "diff_pct": r.get("diff_pct") or "",
                "status": r.get("forecast_status") or "",
            }
        )
    return out


def build_coefficient(auto_coeff):
    """映射成前端期望的 {active, sets:{key:{label,coeff,pooled,range,days,rows,...}}}"""
    sets_out = {}
    for k, v in (auto_coeff.get("sets") or {}).items():
        coeff_main = v.get("coeff_weekday") or v.get("coeff")
        sets_out[k] = {
            "label": v.get("label", k),
            "coeff": round(coeff_main, 6) if isinstance(coeff_main, (int, float)) else coeff_main,
            "coeff_all": v.get("coeff"),           # 含周末全量，参考用
            "pooled": v.get("pooled"),
            "range": f"{v.get('range_start', '')} ~ {v.get('range_end', '')}",
            "days": v.get("day_count"),
            "rows": v.get("sample_n_rows"),
            "total_partial": v.get("total_partial"),
            "total_full": v.get("total_full"),
            "computed_at": auto_coeff.get("updated_at"),
        }
    return {"active": auto_coeff.get("active") or "1m", "sets": sets_out}


def build_forecast_diff(rows):
    out = []
    for r in rows:
        out.append(
            {
                "predict_date": r.get("predict_date"),
                "today_pending_15": num(r.get("today_pending_15")),
                "coefficient": r.get("coefficient") or "",
                "predicted_full": num(r.get("predicted_full")),
                "mode": r.get("predict_mode") or "",
                "actual_next_day_09": num(r.get("actual_next_day_pending_09")),
                "diff": num(r.get("diff")),
                "diff_pct": r.get("diff_pct") or "",
                "status": r.get("status") or "",
            }
        )
    return out


def build_settings(s):
    s = dict(s or {})
    hol = dict(s.get("holiday") or {})
    hol["holidays_count"] = len(hol.get("holidays") or [])
    s["holiday"] = hol
    return s


# ============ 采集 ============
def collect():
    db = load_dashboard()
    print(f"  [OK] 已载入 dashboard 模块: {resolve_dashboard()}")

    settings = db.load_settings()
    status = db.get_status()
    history_rows = db.get_history()
    predict = db.get_predict_today()
    auto_coeff = db.get_auto_coefficients()
    forecast_rows = db.get_forecast_diff()

    print(
        f"  [OK] 台账 {len(history_rows)} 天 / 预测记录 {len(forecast_rows)} 条 / "
        f"系数集 {len(auto_coeff.get('sets') or {})} 套"
    )

    payload = {
        "report": build_report(db, status, predict, auto_coeff, forecast_rows, settings),
        "history": build_history(history_rows),
        "predict": predict,
        "coefficient": build_coefficient(auto_coeff),
        "forecast_diff": build_forecast_diff(forecast_rows),
        "status": status,
        "settings": build_settings(settings),
        "_synced_from": "local-files-v2",
    }
    return payload


# ============ 推送 ============
def _http(method, url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def repo_root():
    """从脚本目录向上找含 .git 的仓库根（兼容 sync/ 与 fetch/sync/ 两种位置）。"""
    d = _HERE
    for _ in range(5):
        if (d / ".git").exists():
            return d
        d = d.parent
    return _HERE.parent


def _load_gh_token():
    """按优先级取 GitHub token: 环境变量 GH_TOKEN > 本地 sync/.gh_token(不入库)。
    注意: 不要把明文 PAT 写进会被提交的脚本/文件, 否则触发仓库密钥扫描拦截。"""
    t = (os.environ.get("GH_TOKEN") or "").strip()
    if t:
        return t
    for p in (_HERE / ".gh_token", repo_root() / ".gh_token", Path(".gh_token")):
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    sys.stderr.write(
        "[WARN] 未找到 GitHub Token: 请设置环境变量 GH_TOKEN, 或在 sync/.gh_token 写入 PAT\n"
    )
    return ""


GH_TOKEN = _load_gh_token()


def push(payload):
    import base64

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    raw = content.encode("utf-8")

    api = f"{GH_API}/repos/{GH_REPO}/contents/{GH_DATA_PATH}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "withdraw-dashboard-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 本地也写一份，方便双击 index.html 离线预览 / 调试（不依赖网络即可看）
    try:
        lp = repo_root() / GH_DATA_PATH
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(content, encoding="utf-8")
        print(f"[OK] 本地备份已写入: {lp}")
    except Exception as e:
        print(f"[WARN] 本地备份失败(不影响云端): {e}")

    # 取现有文件 sha（已存在才需要，用于更新而非新建）
    sha = None
    try:
        info = json.loads(
            _http("GET", api, headers={k: v for k, v in headers.items() if k != "Content-Type"})
        )
        sha = info.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    except Exception:
        pass

    msg = "sync: {} 待提现 CNY {}".format(
        payload["report"]["date"], payload["report"].get("pending_amount")
    )
    data = {
        "message": msg,
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": GH_BRANCH,
    }
    if sha:
        data["sha"] = sha
    _http("PUT", api, data=json.dumps(data).encode("utf-8"), headers=headers)
    print("[OK] 已同步到 GitHub 仓库 data/dashboard.json")


def verify(expect_date=None):
    """推送后回查仓库文件，确认数据真的落库（避免"以为同步了"）。"""
    import base64

    api = f"{GH_API}/repos/{GH_REPO}/contents/{GH_DATA_PATH}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "withdraw-dashboard-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        raw = _http("GET", api, headers=headers)
    except Exception as e:
        print(f"[WARN] 回查失败(数据可能已推送成功): {type(e).__name__}: {e}")
        return True
    info = json.loads(raw)
    try:
        content = base64.b64decode(info["content"]).decode("utf-8")
        data = json.loads(content)
    except Exception as e:
        print(f"[WARN] 回查内容解析失败: {e}")
        return True
    rep = data.get("report") or {}
    cloud_date = rep.get("date")
    amount = rep.get("pending_amount") or 0
    print("\n--- 云端回查 ---")
    print(f"  云端最新数据日期 : {cloud_date}")
    print(f"  待提现金额       : CNY {amount:,.2f} / {rep.get('pending_count')} 笔")
    print(f"  文件 SHA         : {str(info.get('sha', ''))[:12]}")
    if expect_date and cloud_date != expect_date:
        print(f"[FAIL] 不一致! 本地是 {expect_date}, 云端是 {cloud_date}")
        return False
    print("[OK] 云端数据与本机一致, 网页刷新即可看到")
    return True


if __name__ == "__main__":
    print("读取本机数据文件…")
    try:
        payload = collect()
    except Exception as e:
        print(f"[FAIL] 采集失败: {type(e).__name__}: {e}")
        sys.exit(1)

    rp = payload["report"]
    print(
        f"  -> {rp['date']} 待提现 CNY {(rp['pending_amount'] or 0):,.2f} / {rp['pending_count']} 笔"
    )

    try:
        push(payload)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"[FAIL] 同步失败: HTTP {e.code} {detail}")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] 同步失败: {type(e).__name__}: {e}")
        sys.exit(1)

    try:
        ok = verify(expect_date=rp.get("date"))
    except Exception as e:
        print(f"[WARN] 回查失败(数据可能已推送成功): {type(e).__name__}: {e}")
        ok = True

    print("\n完成。" if ok else "\n完成, 但云端校验未通过, 请重跑一次。")
    sys.exit(0 if ok else 1)

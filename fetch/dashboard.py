# -*- coding: utf-8 -*-
"""
承运提现日报 - 本地网页仪表盘 (控制台) v2

功能:
  1. 发送配置: 待提现推送(时间/数据范围/微信)、失败核查(时间/数据范围/微信)、
     节假日处理(跳过/累计/节假日列表);保存后由"设置同步器"自动化写回 WorkBuddy 自动化。
  2. 手动立即执行: 按当前配置 + 节假日逻辑计算 start/end 后调用脚本。
  3. 今日日报预览 + 状态显示。

技术: Python 内置 http.server + 原生 HTML/JS, 零额外依赖。
运行: python dashboard.py  然后浏览器打开 http://localhost:8766
"""

import csv
import json
import os
import sys
import subprocess
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ============ 路径配置 ============
SCRIPT_DIR = Path(__file__).parent
REPORTS_DIR = SCRIPT_DIR / "reports"
DATA_DIR = SCRIPT_DIR / "data"
DEMAND2_DIR = SCRIPT_DIR / "demand2"
WITHDRAW_SCRIPT = SCRIPT_DIR / "withdraw_report.py"
PYTHON_EXE = sys.executable  # 云端用当前 python（去掉 Windows 绝对路径）
SETTINGS_FILE = SCRIPT_DIR / "dashboard_settings.json"
RUN_LOG = SCRIPT_DIR / "dashboard_run.log"
PENDING_LEDGER = SCRIPT_DIR / "pending_ledger.csv"
FORECAST_CSV = DEMAND2_DIR / "forecast.csv"
COEFFICIENT_FILE = DEMAND2_DIR / "coefficient.json"
COEFFICIENT_CHANGELOG = DEMAND2_DIR / "coefficient_changelog.csv"
COEFFICIENTS_AUTO_FILE = DEMAND2_DIR / "coefficients_auto.json"   # 自动抓取算出的三套系数(近1/2/3月)
PORT = 8766

# 待同步的 WorkBuddy 自动化 ID (由"设置同步器"读取 dashboard_settings.json 后更新)
AUTO_PENDING_PUSH = "automation-1785145863403"   # 09:00 微信推送
AUTO_FAIL_CHECK = "automation-1785205680669"     # 15:00 失败核查

# ============ 运行态 ============
RUN_STATE = {"proc": None, "action": None, "start": None}

# ============ 默认设置 ============
DEFAULT_SETTINGS = {
    "pending": {
        "time": "09:00",
        "data_range": "T-1",       # T-1 = 昨天, T = 今天
        "wechat_push": False,
    },
    "fail": {
        "time": "15:00",
        "data_range": "T-1",
        "wechat_push": False,
    },
    "holiday": {
        "skip": True,              # 节假日当天不推送
        "accumulate": True,        # 跳过则节后第一个工作日累计 [节前最后工作日 ~ 昨天]
        "holidays": [],            # 节假日列表(YYYY-MM-DD), 用户手动维护
    },
}


# ============ 设置读写 ============
def merge_defaults(s):
    """递归合并默认值,防止前端漏传字段导致 KeyError"""
    out = json.loads(json.dumps(DEFAULT_SETTINGS))  # 深拷贝
    for k, v in (s or {}).items():
        if isinstance(v, dict) and k in out and isinstance(out[k], dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return merge_defaults(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(s):
    s = merge_defaults(s)
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s


# ============ 日期范围计算 ============
def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def is_holiday(d, holidays):
    """d 是否在 holidays 列表中"""
    return d.strftime("%Y-%m-%d") in (holidays or [])


def find_last_workday_before(d, holidays):
    """返回 d 之前(含 d-1)最近的非节假日工作日"""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5 or is_holiday(cur, holidays):
        cur -= timedelta(days=1)
    return cur


def find_holiday_period_end(d, holidays):
    """若 d 是节假日,返回这段连续假期的最后一天;否则返回 None

    连续假期定义: 节假日列表中的日期,或与假期相连的周末(避免 10-01~07 国庆含周末的边界问题)
    """
    if not is_holiday(d, holidays):
        return None
    cur = d
    while is_holiday(cur, holidays) or cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur - timedelta(days=1)  # 假期的最后一天


def compute_effective_range(kind, today, settings):
    """根据 kind('pending'|'fail') 和设置,计算实际要跑的数据区间。

    返回 (start, end, is_skipped, label)
      start, end:  YYYY-MM-DD
      is_skipped:  True 表示"今天应跳过" (节假日且开启跳过且不需要累计)
      label:       给前端展示的中文说明
    """
    s = settings
    cfg = s[kind]
    rng = cfg["data_range"]
    hol = s["holiday"]

    # 1) 节假日跳过逻辑
    if hol["skip"] and is_holiday(today, hol["holidays"]):
        # 节假日当天跳过, 不管 data_range
        return (None, None, True, f"{today} 是节假日, 已跳过")

    # 2) 节假日累计逻辑: 今天若是节后第一个工作日, 用 [节前最后工作日, 节后-1] 累计
    if hol["skip"] and hol["accumulate"] and is_holiday(today - timedelta(days=1), hol["holidays"]):
        # 昨天是节假日, 视今天为"节后第一个工作日" (或还在假期里但累计触发的临界)
        # 实际起算: 段尾 = 昨天(段尾是假期最后一天)
        period_end = find_holiday_period_end(today - timedelta(days=1), hol["holidays"])
        if period_end:
            period_start = find_last_workday_before(period_end - timedelta(days=1), hol["holidays"])
            start = period_start.strftime("%Y-%m-%d")
            end = period_end.strftime("%Y-%m-%d")
            return (start, end, False, f"节假日累计: {start} ~ {end}")

    # 3) 常规: T-1 或 T
    if rng == "T":
        target = today
    else:  # T-1
        target = today - timedelta(days=1)
    return (target.strftime("%Y-%m-%d"), target.strftime("%Y-%m-%d"), False, f"{rng} → {target}")


# ============ 状态计算 ============
def get_status():
    today = datetime.now().strftime("%Y-%m-%d")
    report_file = REPORTS_DIR / f"withdraw_report_{today}.md"
    data_file = DATA_DIR / f"withdraw_data_{today}.json"

    report_exists = report_file.exists()
    report_time = None
    if report_exists:
        try:
            head = report_file.read_text(encoding="utf-8")
            for line in head.splitlines():
                if "生成时间" in line:
                    report_time = line.split(":", 1)[-1].strip()
                    break
        except Exception:
            pass

    data = {}
    if data_file.exists():
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pending_amount = data.get("pending_amount")
    pending_count = data.get("pending_count")
    if pending_amount is not None:
        pending_status = f"已生成 ¥{pending_amount:,.2f} / {pending_count} 笔"
    else:
        pending_status = "未生成"

    if "fail_reasons" not in data:
        fail_status = "未运行"
    else:
        fr = data.get("fail_reasons") or []
        if len(fr) == 0:
            fail_status = "无失败"
        else:
            fail_status = f"有失败 ({len(fr)} 条)"

    return {
        "today": today,
        "report_exists": report_exists,
        "report_time": report_time,
        "pending_status": pending_status,
        "fail_status": fail_status,
    }


def get_report_text():
    today = datetime.now().strftime("%Y-%m-%d")
    report_file = REPORTS_DIR / f"withdraw_report_{today}.md"
    if report_file.exists():
        return report_file.read_text(encoding="utf-8")
    return "今日日报尚未生成。"


# ============ 每日提现数据 / 预测 / 差异 ============
def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def get_history():
    """合并 pending_ledger.csv + 各日 data/*.json + forecast.csv -> 每日一行完整数据"""
    rows = []
    if PENDING_LEDGER.exists():
        with open(PENDING_LEDGER, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                r["pending_amount"] = _safe_float(r.get("pending_amount"), 0) or 0
                r["pending_count"]  = int(_safe_float(r.get("pending_count"), 0) or 0)
                r["run_date"]       = r.get("run_date", "")
                r["stat_range_start"] = r.get("stat_range_start", "")
                r["stat_range_end"]   = r.get("stat_range_end", "")
                rows.append(r)
    if not rows:
        return []

    # 合并每日的 data JSON: 失败原因 + 需求二/预测
    for r in rows:
        run_date = r["run_date"]
        data_file = DATA_DIR / f"withdraw_data_{run_date}.json"
        r.update({
            "fail_count": "", "fail_top1": "", "fail_top1_count": "",
            "demand2_today_pending": "", "coefficient": "", "predicted_full": "",
        })
        if data_file.exists():
            try:
                d = json.loads(data_file.read_text(encoding="utf-8"))
                fr = d.get("fail_reasons")
                if fr is not None:
                    r["fail_count"] = len(fr)
                    if fr:
                        c = Counter(fr)
                        top_reason, top_count = c.most_common(1)[0]
                        if top_reason not in (None, "", "-"):
                            r["fail_top1"] = (top_reason[:30] + "…") if len(top_reason) > 30 else top_reason
                            r["fail_top1_count"] = top_count
                if d.get("demand2_today_pending") is not None:
                    r["demand2_today_pending"] = f"{d['demand2_today_pending']:.2f}"
                if d.get("coefficient") is not None:
                    r["coefficient"] = f"{d['coefficient']:.4f}"
                if d.get("predicted_full") is not None:
                    r["predicted_full"] = f"{d['predicted_full']:.2f}"
            except Exception:
                pass

    # 合并 forecast.csv: 实际次日 + 差异 + 状态
    forecast_map = {}
    if FORECAST_CSV.exists():
        with open(FORECAST_CSV, "r", encoding="utf-8-sig", newline="") as f:
            for fr in csv.DictReader(f):
                forecast_map[fr.get("predict_date", "")] = fr
    for r in rows:
        fr = forecast_map.get(r["run_date"], {})
        r["actual_next_day_pending_09"] = fr.get("actual_next_day_pending_09", "")
        r["diff"] = fr.get("diff", "")
        r["diff_pct"] = fr.get("diff_pct", "")
        r["forecast_status"] = fr.get("status", "")

    rows.sort(key=lambda r: r["run_date"], reverse=True)
    return rows


def last_weekend_components(coeff_dict):
    """从系数文件 daily_partial/daily_full 取最近一个完整周末(周五/六/日)实际金额。
    返回 dict 或 None。用于周一预测口径。"""
    if not coeff_dict:
        return None
    daily_full = coeff_dict.get("daily_full", {})
    daily_partial = coeff_dict.get("daily_partial", {})
    if not daily_full:
        return None
    fridays = sorted(d for d in daily_full if datetime.strptime(d, "%Y-%m-%d").date().weekday() == 4)
    if not fridays:
        return None
    fri = fridays[-1]
    fri_dt = datetime.strptime(fri, "%Y-%m-%d").date()
    sat = (fri_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    sun = (fri_dt + timedelta(days=2)).strftime("%Y-%m-%d")
    return {
        "fri_date": fri,
        "fri_partial": float(daily_partial.get(fri, 0.0)),
        "sat_date": sat,
        "sat_full": float(daily_full.get(sat, 0.0)),
        "sun_date": sun,
        "sun_full": float(daily_full.get(sun, 0.0)),
    }


def get_predict_today():
    """今日的需求二(当天0~15点待提现+预测), 按星期切换口径。"""
    today = datetime.now().strftime("%Y-%m-%d")
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    data_file = DATA_DIR / f"withdraw_data_{today}.json"
    out = {"today": today, "has_data": False}
    d = {}
    if data_file.exists():
        try:
            d = json.loads(data_file.read_text(encoding="utf-8"))
            out["has_data"] = True
        except Exception:
            pass
    out["demand2_today_pending"] = d.get("demand2_today_pending")
    out["coefficient"] = d.get("coefficient")
    out["predicted_full"] = d.get("predicted_full")
    out["predict_mode"] = d.get("predict_mode")
    out["predict_breakdown"] = d.get("predict_breakdown")
    # 系数来源 + 工作日系数
    coeff_file = DEMAND2_DIR / "coefficient.json"
    coeff_val = None
    coeff_dict = None
    if coeff_file.exists():
        try:
            coeff_dict = json.loads(coeff_file.read_text(encoding="utf-8"))
            coeff_val = coeff_dict.get("coeff_weekday") or coeff_dict.get("coeff")
            out["coefficient_source"] = f"{coeff_dict.get('date_min','')} ~ {coeff_dict.get('date_max','')}, {coeff_dict.get('sample_n_rows','')} 行"
            out["total_partial"] = coeff_dict.get("total_partial", 0)
            out["total_full"] = coeff_dict.get("total_full", 0)
        except Exception:
            coeff_dict = None
    if out["coefficient"] is None and coeff_val is not None:
        out["coefficient"] = coeff_val
    # 兜底: 若保存的数据里没有预测值, 但有今日0~15点待提现与系数, 现场补算(含周一口径)
    if out["predicted_full"] is None and out["demand2_today_pending"] not in (None, ""):
        if today_dt.weekday() == 0 and coeff_val and coeff_dict:
            wk = last_weekend_components(coeff_dict)
            if wk:
                fri_full_pred = wk["fri_partial"] / coeff_val
                out["predicted_full"] = round(fri_full_pred + wk["sat_full"] + wk["sun_full"], 2)
                out["predict_mode"] = "monday"
                out["predict_breakdown"] = {
                    "fri_date": wk["fri_date"], "fri_partial": round(wk["fri_partial"], 2),
                    "fri_full_pred": round(fri_full_pred, 2),
                    "sat_date": wk["sat_date"], "sat_full": round(wk["sat_full"], 2),
                    "sun_date": wk["sun_date"], "sun_full": round(wk["sun_full"], 2),
                }
        elif coeff_val:
            try:
                out["predicted_full"] = round(float(out["demand2_today_pending"]) / float(coeff_val), 2)
                out["predict_mode"] = "weekday"
            except Exception:
                pass
    return out


def get_forecast_diff():
    """从 demand2/forecast.csv 读全部预测+实际+差异, 倒序"""
    if not FORECAST_CSV.exists():
        return []
    with open(FORECAST_CSV, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r.get("predict_date", ""), reverse=True)
    return rows


def get_coefficient_info():
    """系数管理: 现在系数 / 原有系数 / 变更记录"""
    now = None
    if COEFFICIENT_FILE.exists():
        try:
            now = json.loads(COEFFICIENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    changelog = []
    if COEFFICIENT_CHANGELOG.exists():
        with open(COEFFICIENT_CHANGELOG, "r", encoding="utf-8-sig", newline="") as f:
            changelog = list(csv.DictReader(f))
        changelog.sort(key=lambda r: r.get("imported_at", ""), reverse=True)
    old = None
    if changelog:
        last = changelog[0]
        old = {
            "coeff": _safe_float(last.get("old_coeff"), 0),
            "pooled": _safe_float(last.get("old_pooled"), 0),
        }
    return {
        "now": now,
        "old": old,
        "changelog": changelog[:20],
        "has_now": now is not None,
        "has_old": old is not None,
    }


def get_auto_coefficients():
    """读取自动抓取算出的三套系数(近1/2/3月) + active 选择。
    系数 = 每日(创建时间 0~SPLIT_HOUR 点金额 / 0~24 点金额) 的均值。"""
    if not COEFFICIENTS_AUTO_FILE.exists():
        return {"exists": False, "updated_at": None, "active": None, "sets": {}}
    try:
        data = json.loads(COEFFICIENTS_AUTO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"exists": False, "updated_at": None, "active": None, "sets": {}}
    sets = data.get("sets", {}) or {}
    labels = {"1m": "近1月", "2m": "近2月", "3m": "近3月"}
    out_sets = {}
    for k, v in sets.items():
        if not isinstance(v, dict):
            continue
        out_sets[k] = {
            "label": labels.get(k, k),
            "coeff": v.get("coeff"),
            "coeff_weekday": v.get("coeff_weekday"),
            "pooled": v.get("pooled"),
            "split_hour": v.get("split_hour"),
            "range_start": v.get("range_start"),
            "range_end": v.get("range_end"),
            "sample_n_rows": v.get("sample_n_rows"),
            "day_count": v.get("day_count"),
            "total_partial": v.get("total_partial"),
            "total_full": v.get("total_full"),
            "ratios": v.get("ratios"),
            "overall_daily_avg": v.get("overall_daily_avg"),
            "weekday_daily_avg": v.get("weekday_daily_avg"),
            "weekend_daily_avg": v.get("weekend_daily_avg"),
            "per_weekday_avg": v.get("per_weekday_avg"),
        }
    return {
        "exists": True,
        "updated_at": data.get("updated_at"),
        "active": data.get("active"),
        "sets": out_sets,
    }


def start_auto():
    """自动从财务中心抓取近1/2/3月(不含当天)数据并计算三套系数。
    复用 RUN_STATE + RUN_LOG, 与手动执行共用日志区。登录过期时脚本会打印 [ERROR] 未登录 并退出(不重试)。"""
    global RUN_STATE
    if RUN_STATE["proc"] is not None and RUN_STATE["proc"].poll() is None:
        return {"started": False, "msg": "已有任务在运行中"}
    logf = open(RUN_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON_EXE, str(WITHDRAW_SCRIPT), "--auto-coeff"],
        stdout=logf,
        stderr=subprocess.STDOUT,
        cwd=str(SCRIPT_DIR),
    )
    RUN_STATE = {"proc": proc, "action": "auto", "start": datetime.now(),
                 "args": ["--auto-coeff"], "label": "自动抓取并计算系数(近1/2/3月)"}
    return {"started": True, "msg": "已启动自动计算(近1/2/3月)"}



# ============ 手动执行 ============
def start_run(kind):
    """kind: 'pending' | 'fail'  (按当前设置计算 start/end)"""
    global RUN_STATE
    if RUN_STATE["proc"] is not None and RUN_STATE["proc"].poll() is None:
        return {"started": False, "msg": "已有任务在运行中"}

    settings = load_settings()
    today = datetime.now().date()
    start, end, skipped, label = compute_effective_range(kind, today, settings)

    if skipped:
        return {"started": False, "msg": f"{label} (无需执行)"}

    if kind == "pending":
        args = ["--pending", "--start-date", start, "--end-date", end]
    else:
        args = ["--fail", "--demand2", "--start-date", start, "--end-date", end]

    logf = open(RUN_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON_EXE, str(WITHDRAW_SCRIPT)] + args,
        stdout=logf,
        stderr=subprocess.STDOUT,
        cwd=str(SCRIPT_DIR),
    )
    RUN_STATE = {"proc": proc, "action": kind, "start": datetime.now(),
                 "args": args, "label": label}
    return {"started": True, "msg": f"已启动 {kind} ({label})"}


def get_run_status():
    proc = RUN_STATE.get("proc")
    running = proc is not None and proc.poll() is None
    log_tail = ""
    if RUN_LOG.exists():
        try:
            lines = RUN_LOG.read_text(encoding="utf-8").splitlines()
            log_tail = "\n".join(lines[-40:])
        except Exception:
            pass
    return {
        "running": running,
        "action": RUN_STATE.get("action"),
        "label": RUN_STATE.get("label"),
        "log_tail": log_tail,
    }


# ============ HTTP 处理 ============
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send(200, PAGE_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/settings":
            self._send(200, load_settings())
        elif self.path == "/api/status":
            self._send(200, get_status())
        elif self.path == "/api/report":
            self._send(200, get_report_text(), "text/plain; charset=utf-8")
        elif self.path == "/api/run-status":
            self._send(200, get_run_status())
        elif self.path == "/api/preview-ranges":
            # 当前设置下, 待提现推送/失败核查 即将跑的数据范围
            settings = load_settings()
            today = datetime.now().date()
            self._send(200, {
                "today": today.strftime("%Y-%m-%d"),
                "pending": compute_effective_range("pending", today, settings),
                "fail":    compute_effective_range("fail",    today, settings),
            })
        elif self.path == "/api/history":
            self._send(200, get_history())
        elif self.path == "/api/predict":
            self._send(200, get_predict_today())
        elif self.path == "/api/forecast-diff":
            self._send(200, get_forecast_diff())
        elif self.path == "/api/coefficient":
            self._send(200, get_coefficient_info())
        elif self.path == "/api/coefficients-auto":
            self._send(200, get_auto_coefficients())
        elif self.path == "/api/download-history":
            # 完整版 CSV: 待提现 + 失败 + 需求二 + 预测 + 实际 + 差异
            import io
            rows = get_history()
            fieldnames = ["run_date", "stat_range_start", "stat_range_end",
                          "pending_count", "pending_amount",
                          "fail_count", "fail_top1", "fail_top1_count",
                          "demand2_today_pending", "coefficient", "predicted_full",
                          "actual_next_day_pending_09", "diff", "diff_pct", "forecast_status"]
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
            body = buf.getvalue().encode("utf-8-sig")  # BOM 让 Excel 正确识别中文
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="withdraw_history_{datetime.now().strftime("%Y%m%d")}.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {}

        if self.path == "/api/settings":
            try:
                s = save_settings(payload)
                self._send(200, {"ok": True, "settings": s,
                                 "note": "已保存到 dashboard_settings.json, 设置同步器将在数分钟内写回自动化。"})
            except Exception as e:
                self._send(400, {"ok": False, "error": str(e)})
        elif self.path == "/api/run":
            action = payload.get("action", "pending")
            if action not in ("pending", "fail"):
                self._send(400, {"error": "action must be pending or fail"})
                return
            result = start_run(action)
            self._send(200, result)
        elif self.path == "/api/auto-coefficient":
            result = start_auto()
            self._send(200, result)
        elif self.path == "/api/coefficient-active":
            key = (payload.get("key") or "").strip()
            if key not in ("1m", "2m", "3m"):
                self._send(400, {"ok": False, "error": "key 必须是 1m / 2m / 3m"})
                return
            try:
                proc = subprocess.run(
                    [PYTHON_EXE, str(WITHDRAW_SCRIPT), "--set-active", key],
                    capture_output=True, text=True, cwd=str(SCRIPT_DIR), timeout=120,
                )
                if proc.returncode != 0:
                    self._send(200, {"ok": False, "error": (proc.stderr or proc.stdout or "执行失败").strip()[-300:]})
                    return
                self._send(200, {"ok": True, "key": key,
                                 "msg": f"已切换为 {key} 系数并同步到 coefficient.json"})
            except Exception as e:
                self._send(200, {"ok": False, "error": str(e)})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # 静默


# ============ 前端页面 ============
PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>承运提现日报控制台</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         background:#f4f6fb; color:#1f2937; }
  .wrap { max-width:960px; margin:0 auto; padding:24px 16px 60px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:#6b7280; font-size:13px; margin-bottom:20px; }
  .card { background:#fff; border-radius:14px; padding:20px; margin-bottom:18px;
          box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .card h2 { font-size:16px; margin:0 0 14px; display:flex; align-items:center; gap:8px; }
  .subcard { background:#f8fafc; border:1px solid #e5e7eb; border-radius:10px;
             padding:14px 16px; margin-bottom:12px; }
  .subcard h3 { font-size:14px; margin:0 0 10px; color:#1e3a8a; display:flex;
                align-items:center; gap:6px; }
  .row { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
  .row:last-child { margin-bottom:0; }
  label { font-size:14px; color:#374151; min-width:120px; }
  label.s { min-width:90px; color:#6b7280; font-size:13px; }
  input[type=time], select, textarea {
    padding:8px 10px; border:1px solid #d1d5db; border-radius:8px;
    font-size:14px; font-family: inherit; background:#fff;
  }
  textarea { width:100%; min-height:80px; resize:vertical;
             font-family: ui-monospace, "SFMono-Regular", monospace; }
  .switch { position:relative; width:46px; height:26px; flex-shrink:0; display:inline-block; cursor:pointer; user-select:none; }
  .switch input { opacity:0; width:0; height:0; }
  .slider { position:absolute; inset:0; background:#cbd5e1; border-radius:26px; transition:.2s; cursor:pointer; }
  .slider:before { content:""; position:absolute; height:20px; width:20px; left:3px; top:3px;
                   background:#fff; border-radius:50%; transition:.2s; }
  .switch input:checked + .slider { background:#2563eb; }
  .switch input:checked + .slider:before { transform:translateX(20px); }
  button { border:none; border-radius:9px; padding:10px 16px; font-size:14px; cursor:pointer;
           background:#2563eb; color:#fff; transition:.15s; }
  button:hover { background:#1d4ed8; }
  button.sec { background:#e5e7eb; color:#1f2937; }
  button.sec:hover { background:#d1d5db; }
  button.danger { background:#dc2626; }
  button.danger:hover { background:#b91c1c; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  .note { font-size:13px; color:#16a34a; margin-top:8px; min-height:18px; }
  .badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .b-ok { background:#dcfce7; color:#166534; }
  .b-warn { background:#fef9c3; color:#854d0e; }
  .b-no { background:#fee2e2; color:#991b1b; }
  .b-idle { background:#e5e7eb; color:#374151; }
  .stat { font-size:14px; margin:6px 0; }
  pre { background:#0f172a; color:#e2e8f0; padding:16px; border-radius:10px; overflow:auto;
        max-height:420px; font-size:13px; line-height:1.5; white-space:pre-wrap; }
  .runlog { background:#0f172a; color:#86efac; padding:12px; border-radius:10px; height:180px;
            overflow:auto; font-size:12px; white-space:pre-wrap; font-family:ui-monospace,monospace; }
  .muted { color:#9ca3af; font-size:12px; }
  .preview-box { background:#f1f5f9; border-left:3px solid #2563eb; padding:8px 12px;
                 border-radius:6px; font-size:13px; color:#475569; margin-top:8px; }
  .range-tag { display:inline-block; padding:2px 8px; background:#dbeafe; color:#1e40af;
               border-radius:4px; font-size:12px; font-weight:600; }
  table th, table td { border-bottom:1px solid #f1f5f9; }
  table tbody tr:hover { background:#f8fafc; }
  .num { text-align:right; font-variant-numeric: tabular-nums; }
  .pos { color:#dc2626; font-weight:600; }  /* 实际>预测(差异为正)= 实际更小是负, 但这里 diff = 实际-预测, 越大表示超出预测 */
  .neg { color:#16a34a; }
</style>
</head>
<body>
<div class="wrap">
  <h1>承运提现日报控制台</h1>
  <div class="sub">本地网页仪表盘 · 配置 / 手动执行 / 状态预览</div>

  <div class="card">
    <h2>⚙️ 发送配置</h2>

    <div class="subcard">
      <h3>📤 待提现推送</h3>
      <div class="row">
        <label>推送时间</label>
        <input type="time" id="pendingTime">
        <span class="muted">工作日定时推送</span>
      </div>
      <div class="row">
        <label>数据范围</label>
        <select id="pendingRange">
          <option value="T-1">T-1(创建时间=昨天)</option>
          <option value="T">T(创建时间=今天)</option>
        </select>
        <span class="muted">默认 T-1; 节假日按下方规则处理</span>
      </div>
      <div class="row">
        <label>微信推送</label>
        <label class="switch"><input type="checkbox" id="pendingWechat"><span class="slider"></span></label>
        <span class="muted">开=同时推送到 WorkBuddy 微信</span>
      </div>
    </div>

    <div class="subcard">
      <h3>🔍 失败核查</h3>
      <div class="row">
        <label>核查时间</label>
        <input type="time" id="failTime">
        <span class="muted">工作日定时核查</span>
      </div>
      <div class="row">
        <label>数据范围</label>
        <select id="failRange">
          <option value="T-1">T-1(创建时间=昨天)</option>
          <option value="T">T(创建时间=今天)</option>
        </select>
      </div>
      <div class="row">
        <label>微信推送</label>
        <label class="switch"><input type="checkbox" id="failWechat"><span class="slider"></span></label>
        <span class="muted">开=同时推送到 WorkBuddy 微信</span>
      </div>
    </div>

    <div class="subcard">
      <h3>🏖️ 节假日处理</h3>
      <div class="row">
        <label class="s">节假日跳过</label>
        <label class="switch"><input type="checkbox" id="holidaySkip"><span class="slider"></span></label>
        <span class="muted">节假日当天不推送</span>
      </div>
      <div class="row">
        <label class="s">节后累计</label>
        <label class="switch"><input type="checkbox" id="holidayAccumulate"><span class="slider"></span></label>
        <span class="muted">节后第一个工作日推送 [节前最后工作日 + 节假日所有天] 的累计</span>
      </div>
      <div class="row" style="align-items:flex-start;">
        <label class="s" style="margin-top:8px;">节假日列表</label>
        <div style="flex:1;">
          <textarea id="holidaysList" placeholder="一行一个日期,例如:&#10;2026-10-01&#10;2026-10-02&#10;2026-10-05"></textarea>
          <div class="muted">系统不预置,需在此手动维护;若列表为空则节假日规则不生效</div>
        </div>
      </div>
    </div>

    <div class="row" style="margin-top:14px;">
      <button onclick="saveSettings()">保存设置</button>
      <span class="note" id="saveNote"></span>
    </div>
  </div>

  <div class="card">
    <h2>🚀 手动立即执行</h2>
    <div class="row">
      <button onclick="runAction('pending')">立即跑待提现</button>
      <button class="sec" onclick="runAction('fail')">立即核查失败</button>
      <span class="muted">按当前配置 + 节假日规则自动算区间</span>
    </div>
    <div class="preview-box" id="previewRanges">加载中...</div>
    <div class="runlog" id="runlog">空闲。</div>
  </div>

  <div class="card">
    <h2>📊 今日状态</h2>
    <div class="stat">运行日: <b id="stToday">-</b></div>
    <div class="stat">日报生成: <span id="stReport" class="badge b-idle">-</span>
         <span class="muted" id="stTime"></span></div>
    <div class="stat">待提现: <b id="stPending">-</b></div>
    <div class="stat">失败原因: <span id="stFail" class="badge b-idle">-</span></div>
    <div class="row" style="margin-top:10px;">
      <button class="sec" onclick="refreshStatus()">刷新状态</button>
    </div>
  </div>

  <div class="card">
    <h2>📄 今日日报预览</h2>
    <pre id="report">加载中...</pre>
  </div>

  <div class="card">
    <h2>📈 每日提现数据
      <button class="sec" style="margin-left:auto;font-size:12px;padding:5px 10px;" onclick="downloadHistory()">⬇ 下载 CSV</button>
    </h2>
    <div class="muted" style="margin-bottom:8px;">数据来源: pending_ledger.csv (累积) + 各日 data/*.json (失败/需求二) + demand2/forecast.csv (预测/差异)</div>
    <div style="overflow:auto;max-height:380px;">
      <table id="histTable" style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead style="position:sticky;top:0;background:#f8fafc;">
          <tr style="text-align:left;color:#374151;">
            <th style="padding:8px;">运行日</th>
            <th style="padding:8px;">统计区间</th>
            <th style="padding:8px;text-align:right;">待提现金额</th>
            <th style="padding:8px;text-align:right;">笔数</th>
            <th style="padding:8px;text-align:right;">失败条数</th>
            <th style="padding:8px;">Top1 失败原因</th>
            <th style="padding:8px;text-align:right;">当日待提现(0~15点)</th>
            <th style="padding:8px;text-align:right;">预测当天全天</th>
            <th style="padding:8px;text-align:right;">实际次日09</th>
            <th style="padding:8px;text-align:right;">差异</th>
            <th style="padding:8px;text-align:right;">差异率</th>
          </tr>
        </thead>
        <tbody id="histBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>🔮 今日提现预测</h2>
    <div id="predictCard" style="font-size:14px;">加载中...</div>
  </div>

  <div class="card">
    <h2>📊 预测 vs 真实 差异</h2>
    <div class="muted" style="margin-bottom:8px;">数据来源: demand2/forecast.csv · 真实值取次日 09:00 待提现金额</div>
    <div style="overflow:auto;max-height:380px;">
      <table id="diffTable" style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead style="position:sticky;top:0;background:#f8fafc;">
          <tr style="text-align:left;color:#374151;">
            <th style="padding:8px;">预测基于日</th>
            <th style="padding:8px;text-align:right;">当日(0~15点)待提现</th>
            <th style="padding:8px;text-align:right;">系数</th>
            <th style="padding:8px;text-align:right;">预测当天全天(0~24)</th>
            <th style="padding:8px;text-align:right;">真实次日09待提现</th>
            <th style="padding:8px;text-align:right;">差异</th>
            <th style="padding:8px;text-align:right;">差异率</th>
            <th style="padding:8px;">状态</th>
          </tr>
        </thead>
        <tbody id="diffBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>🧮 系数管理</h2>
    <div class="muted" style="margin-bottom:10px;">系数由系统自动从财务中心抓取(创建时间近1/2/3月,不含当天,状态=全部)并计算,无需手动准备表格。默认采用「近1月」系数,可随时切换其他月份。系数的定义:每日「创建时间 0~15 点金额 ÷ 0~24 点金额」的比值取均值。</div>

    <div class="subcard">
      <h3>🤖 自动抓取并计算系数</h3>
      <div class="muted" style="margin-bottom:8px;">从财务中心-结算管理-提现管理(承运)自动导出「创建时间近1/2/3月(不含当天)」的全部提现数据(状态=全部),按日汇总后计算系数。每周一自动刷新,也可手动点击。</div>
      <div class="row" style="margin-top:6px;">
        <button onclick="startAutoCoefficient()">🧮 自动抓取并计算系数</button>
        <button class="sec" onclick="refreshAutoCoefficient()">刷新</button>
        <span class="note" id="autoNote"></span>
      </div>
      <div class="muted" id="autoUpdated" style="margin-top:4px;"></div>
      <div id="autoSets" style="margin-top:12px;"></div>
    </div>

    <div class="subcard">
      <h3>📐 系数对比 (当前 active vs 上次)</h3>
      <div class="stat">当前系数(active): <b id="coeffNow">-</b></div>
      <div class="stat">上次系数: <b id="coeffOld">-</b></div>
      <div class="muted" id="coeffMeta"></div>
    </div>

    <div class="subcard">
      <h3>📝 系数变更记录</h3>
      <div class="muted" style="margin-bottom:6px;">记录每次自动计算的「旧系数 → 新系数」(比值口径)</div>
      <div style="overflow:auto;max-height:300px;">
        <table id="coeffTable" style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead style="position:sticky;top:0;background:#f8fafc;">
            <tr style="text-align:left;color:#374151;">
              <th style="padding:8px;">计算时间</th>
              <th style="padding:8px;">来源(区间)</th>
              <th style="padding:8px;">样本</th>
              <th style="padding:8px;">区间</th>
              <th style="padding:8px;text-align:right;">原系数</th>
              <th style="padding:8px;text-align:right;">新系数</th>
              <th style="padding:8px;text-align:right;">原汇总比值</th>
              <th style="padding:8px;text-align:right;">新汇总比值</th>
              <th style="padding:8px;text-align:right;">天数</th>
              <th style="padding:8px;">状态</th>
            </tr>
          </thead>
          <tbody id="coeffBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);

async function loadSettings(){
  const r = await fetch('/api/settings'); const s = await r.json();
  $('pendingTime').value    = s.pending.time || '09:00';
  $('pendingRange').value   = s.pending.data_range || 'T-1';
  $('pendingWechat').checked= !!s.pending.wechat_push;
  $('failTime').value       = s.fail.time || '15:00';
  $('failRange').value      = s.fail.data_range || 'T-1';
  $('failWechat').checked   = !!s.fail.wechat_push;
  $('holidaySkip').checked       = !!s.holiday.skip;
  $('holidayAccumulate').checked = !!s.holiday.accumulate;
  $('holidaysList').value   = (s.holiday.holidays || []).join('\\n');
}

async function saveSettings(){
  const holidays = $('holidaysList').value
    .split('\\n').map(s => s.trim()).filter(s => /^\\d{4}-\\d{2}-\\d{2}$/.test(s));
  const body = {
    pending: {
      time:        $('pendingTime').value,
      data_range:  $('pendingRange').value,
      wechat_push: $('pendingWechat').checked,
    },
    fail: {
      time:        $('failTime').value,
      data_range:  $('failRange').value,
      wechat_push: $('failWechat').checked,
    },
    holiday: {
      skip:       $('holidaySkip').checked,
      accumulate: $('holidayAccumulate').checked,
      holidays:   holidays,
    },
  };
  const r = await fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)});
  const j = await r.json();
  $('saveNote').textContent = j.ok ? '已保存 ✓ 设置同步器将写回自动化' : ('保存失败: '+(j.error||''));
  setTimeout(()=>$('saveNote').textContent='', 4000);
  refreshPreview();
}

async function refreshPreview(){
  const r = await fetch('/api/preview-ranges'); const s = await r.json();
  function fmt(x){
    if (x[2]) return `<span class="range-tag">跳过</span> ${x[3]}`;
    return `<span class="range-tag">${x[0]} ~ ${x[1]}</span> <span class="muted">${x[3]}</span>`;
  }
  $('previewRanges').innerHTML =
    `运行日: <b>${s.today}</b><br>` +
    `待提现推送 → ${fmt(s.pending)}<br>` +
    `失败核查   → ${fmt(s.fail)}`;
}

async function refreshStatus(){
  const r = await fetch('/api/status'); const s = await r.json();
  $('stToday').textContent = s.today;
  const rep = $('stReport');
  if(s.report_exists){ rep.className='badge b-ok'; rep.textContent='已生成'; }
  else { rep.className='badge b-no'; rep.textContent='未生成'; }
  $('stTime').textContent = s.report_time ? '(生成于 '+s.report_time+')' : '';
  $('stPending').textContent = s.pending_status;
  const sf = $('stFail');
  if(s.fail_status==='无失败'){ sf.className='badge b-ok'; sf.textContent='无失败'; }
  else if(s.fail_status==='未运行'){ sf.className='badge b-idle'; sf.textContent='未运行'; }
  else if(s.fail_status.startsWith('有失败')){ sf.className='badge b-no'; sf.textContent=s.fail_status; }
  else { sf.className='badge b-warn'; sf.textContent=s.fail_status; }

  const rp = await fetch('/api/report'); const txt = await rp.text();
  $('report').textContent = txt;
}

async function runAction(action){
  const r = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action})});
  const j = await r.json();
  $('runlog').textContent = (j.started ? (j.msg + '\\n') : (j.msg + '\\n'));
  if (j.started) pollLog();
}

async function pollLog(){
  const r = await fetch('/api/run-status'); const s = await r.json();
  const head = s.label ? `[${s.label}]\\n` : '';
  $('runlog').textContent = head + (s.log_tail || '空闲。');
  if(s.running){ setTimeout(pollLog, 2500); }
  else {
    refreshStatus(); refreshHistory(); refreshPredict(); refreshDiff(); refreshCoefficient(); refreshAutoCoefficient();
    if (s.action === 'auto'){
      const t = s.log_tail || '';
      if (t.indexOf('[ERROR] 未登录') >= 0){
        $('autoNote').style.color = '#dc2626';
        $('autoNote').textContent = '登录态已过期,请运行 python withdraw_report.py --setup 重新登录后重试。';
      }
    }
  }
}

function fmtMoney(v){ if(v===''||v==null) return '-'; const n=Number(v); if(isNaN(n)) return v; return '¥'+n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmtPct(v){ if(v===''||v==null) return '-'; const n=Number(v); if(isNaN(n)) return v; return n.toFixed(2)+'%'; }
function esc(s){ return (s==null?'':String(s)).replace(/[<>&]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }

async function refreshHistory(){
  const r = await fetch('/api/history');
  const rows = await r.json();
  const tb = $('histBody');
  if (!rows.length){ tb.innerHTML = '<tr><td colspan="11" style="padding:20px;color:#9ca3af;">暂无数据</td></tr>'; return; }
  tb.innerHTML = rows.map(r => {
    const diffCls = r.diff && Number(r.diff) > 0 ? 'pos' : (r.diff && Number(r.diff) < 0 ? 'neg' : '');
    return '<tr>'
      + '<td style="padding:6px 8px;">' + esc(r.run_date) + '</td>'
      + '<td style="padding:6px 8px;color:#6b7280;">' + esc(r.stat_range_start) + ' ~ ' + esc(r.stat_range_end) + '</td>'
      + '<td class="num" style="padding:6px 8px;font-weight:600;">' + fmtMoney(r.pending_amount) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.pending_count||0) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.fail_count===''?'-':r.fail_count) + '</td>'
      + '<td style="padding:6px 8px;">' + esc(r.fail_top1||'') + (r.fail_top1_count?(' <span class="muted">(' + r.fail_top1_count + ')</span>'):'') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.demand2_today_pending) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.predicted_full) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.actual_next_day_pending_09) + '</td>'
      + '<td class="num ' + diffCls + '" style="padding:6px 8px;">' + fmtMoney(r.diff) + '</td>'
      + '<td class="num ' + diffCls + '" style="padding:6px 8px;">' + fmtPct(r.diff_pct) + '</td>'
      + '</tr>';
  }).join('');
}

async function refreshPredict(){
  const r = await fetch('/api/predict');
  const p = await r.json();
  const el = $('predictCard');
  if (!p.has_data){
    el.innerHTML = '<span class="muted">今日(' + esc(p.today) + ') 15:00 任务尚未执行, 无预测数据。等 15:00 跑完后自动出现。</span>'; return;
  }
  const hasPred = p.predicted_full != null;
  const hasCoeff = p.coefficient != null;
  const mode = p.predict_mode;
  const bk = p.predict_breakdown || {};
  const items = [];
  items.push('<div class="stat">📅 今日: <b>' + esc(p.today) + '</b>' + (mode === 'monday' ? ' <span class="badge b-warn">周一算法</span>' : '') + '</div>');
  items.push('<div class="stat">💰 当天(0~15点)待提现金额: <b>' + fmtMoney(p.demand2_today_pending) + '</b></div>');
  if (hasCoeff) items.push('<div class="stat">📐 工作日系数(0~15点/0~24点 比值均值): <b>' + Number(p.coefficient).toFixed(4) + '</b></div>');
  if (hasPred) {
    if (mode === 'monday' && bk.fri_date) {
      items.push('<div class="stat" style="font-size:16px;color:#1e40af;">🔮 预测(上周五~周日合计)待提现: <b>' + fmtMoney(p.predicted_full) + '</b></div>');
      items.push('<div class="muted" style="font-size:12px;margin-top:2px;">'
        + '上周五(' + esc(bk.fri_date) + ') 0~15点 ¥' + fmtMoney(bk.fri_partial) + ' ÷ 系数 → 全天 ¥' + fmtMoney(bk.fri_full_pred)
        + ' ＋ 周六 ¥' + fmtMoney(bk.sat_full) + ' ＋ 周日 ¥' + fmtMoney(bk.sun_full) + '</div>');
    } else {
      items.push('<div class="stat" style="font-size:16px;color:#1e40af;">🔮 预测当天全天(0~24点)待提现: <b>' + fmtMoney(p.predicted_full) + '</b></div>');
    }
  }
  if (mode === 'monday') items.push('<div class="muted" style="margin-top:4px;">周一预测口径: 取「上周五~周日合计」; 上式「当天0~15点」为周一实时值, 未参与计算。</div>');
  if (!hasCoeff) items.push('<div class="muted" style="margin-top:8px;">⚠️ 系数未计算。请点仪表盘「自动抓取并计算系数」或运行: <code>python withdraw_report.py --auto-coeff</code></div>');
  if (p.coefficient_source) items.push('<div class="muted" style="margin-top:4px;">系数来源: ' + esc(p.coefficient_source) + ' (区间 0~15点合计 ¥' + (p.total_partial||0).toLocaleString('zh-CN',{minimumFractionDigits:2}) + ', 0~24点合计 ¥' + (p.total_full||0).toLocaleString('zh-CN',{minimumFractionDigits:2}) + ')</div>');
  el.innerHTML = items.join('');
}

async function refreshDiff(){
  const r = await fetch('/api/forecast-diff');
  const rows = await r.json();
  const tb = $('diffBody');
  if (!rows.length){ tb.innerHTML = '<tr><td colspan="8" style="padding:20px;color:#9ca3af;">暂无数据 (需先 <code>--import</code> 历史表格, 15:00 跑过一次才有预测)</td></tr>'; return; }
  tb.innerHTML = rows.map(r => {
    const diffCls = r.diff && Number(r.diff) > 0 ? 'pos' : (r.diff && Number(r.diff) < 0 ? 'neg' : '');
    const stBadge = r.status === 'compared' ? '<span class="badge b-ok">已比对</span>' : '<span class="badge b-idle">待比对</span>';
    const modeBadge = r.predict_mode === 'monday' ? ' <span class="badge b-warn">周一算法</span>' : '';
    return '<tr>'
      + '<td style="padding:6px 8px;">' + esc(r.predict_date||'') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.today_pending_15) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.coefficient?Number(r.coefficient).toFixed(4):'-') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.predicted_full) + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + fmtMoney(r.actual_next_day_pending_09) + '</td>'
      + '<td class="num ' + diffCls + '" style="padding:6px 8px;">' + fmtMoney(r.diff) + '</td>'
      + '<td class="num ' + diffCls + '" style="padding:6px 8px;">' + fmtPct(r.diff_pct) + '</td>'
      + '<td style="padding:6px 8px;">' + stBadge + modeBadge + '</td>'
      + '</tr>';
  }).join('');
}

function downloadHistory(){ window.location.href = '/api/download-history'; }

function fmtNum(v){
  if (v === '' || v == null) return '0.00';
  const n = Number(v);
  if (isNaN(n)) return v;
  return n.toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
}

async function refreshCoefficient(){
  const r = await fetch('/api/coefficient');
  const c = await r.json();
  if (c.has_now && c.now){
    const now = c.now;
    const cwNow = Number(now.coeff_weekday || now.coeff || 0);
    $('coeffNow').textContent =
      `工作日系数 ${cwNow.toFixed(4)} (含周末全量 ${Number(now.coeff||0).toFixed(4)} · 汇总比值 ${Number(now.pooled||0).toFixed(4)})`
      + ` · 区间 ${now.date_min || '-'}~${now.date_max || '-'}, ${now.day_count||0} 天, ${now.sample_n_rows || 0} 行`;
    $('coeffMeta').textContent = `区间 0~${now.split_hour||15}点 合计 ¥${fmtNum(now.total_partial)} / 0~24点 合计 ¥${fmtNum(now.total_full)} · 周末日均 ¥${fmtNum(now.weekend_daily_avg||0)}`;
  } else {
    $('coeffNow').textContent = '未计算';
    $('coeffMeta').textContent = '';
  }
  if (c.has_old && c.old){
    $('coeffOld').textContent =
      `系数 ${Number(c.old.coeff||0).toFixed(4)} (汇总比值 ${Number(c.old.pooled||0).toFixed(4)})`;
  } else {
    $('coeffOld').textContent = '首次计算, 无历史';
  }

  const tb = $('coeffBody');
  if (!c.changelog || !c.changelog.length){
    tb.innerHTML = '<tr><td colspan="10" style="padding:20px;color:#9ca3af;">暂无变更记录 (自动计算一次后出现)</td></tr>';
    return;
  }
  tb.innerHTML = c.changelog.map(r => {
    const stBadge = r.status === '替换'
      ? '<span class="badge b-warn">替换</span>'
      : '<span class="badge b-ok">新增</span>';
    return '<tr>'
      + '<td style="padding:6px 8px;">' + esc(r.imported_at || '') + '</td>'
      + '<td style="padding:6px 8px;">' + esc(r.source || '') + '</td>'
      + '<td style="padding:6px 8px;text-align:right;">' + (r.sample_n_rows || '-') + '</td>'
      + '<td style="padding:6px 8px;">' + esc(r.date_min || '') + ' ~ ' + esc(r.date_max || '') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.old_coeff?Number(r.old_coeff).toFixed(4):'-') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.new_coeff?Number(r.new_coeff).toFixed(4):'-') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.old_pooled?Number(r.old_pooled).toFixed(4):'-') + '</td>'
      + '<td class="num" style="padding:6px 8px;">' + (r.new_pooled?Number(r.new_pooled).toFixed(4):'-') + '</td>'
      + '<td class="num" style="padding:6px 8px;text-align:right;">' + (r.day_count || '-') + '</td>'
      + '<td style="padding:6px 8px;">' + stBadge + '</td>'
      + '</tr>';
  }).join('');
}

async function refreshAutoCoefficient(){
  const r = await fetch('/api/coefficients-auto');
  const c = await r.json();
  $('autoUpdated').textContent = (c.exists && c.updated_at)
    ? ('最后更新: ' + c.updated_at + (c.active ? ' · 当前使用: ' + ({"1m":"近1月","2m":"近2月","3m":"近3月"}[c.active]||c.active) : ''))
    : '尚未自动计算(点上方按钮生成)';
  const box = $('autoSets');
  const keys = ['1m', '2m', '3m'];
  if (!c.exists || !c.sets || !Object.keys(c.sets).length){
    box.innerHTML = '<div class="muted" style="padding:12px 0;">暂无自动系数。点击「自动抓取并计算系数」从财务中心导出近1/2/3月数据计算。</div>';
    return;
  }
  box.innerHTML = keys.map(k => {
    const s = c.sets[k];
    if (!s) return '';
    const isActive = c.active === k;
    const coeff = Number(s.coeff || 0);
    const cw = Number(s.coeff_weekday || s.coeff || 0);
    const pooled = Number(s.pooled || 0);
    const sh = s.split_hour || 15;
    const tp = Number(s.total_partial || 0);
    const tf = Number(s.total_full || 0);
    const sampleDays = s.day_count || 0;
    return '<div style="border:1px solid ' + (isActive ? '#2563eb' : '#e5e7eb') + ';border-radius:10px;padding:12px 14px;margin-bottom:10px;background:' + (isActive ? '#eff6ff' : '#fff') + ';">'
      + '<div class="row" style="margin-bottom:4px;">'
        + '<b style="font-size:14px;">' + esc(s.label) + '</b>'
        + (isActive ? '<span class="badge b-ok" style="margin-left:8px;">当前使用</span>' : '')
        + '<span class="muted" style="margin-left:auto;">' + esc(s.range_start || '') + ' ~ ' + esc(s.range_end || '') + ' · ' + (s.sample_n_rows || 0) + ' 行 · ' + sampleDays + ' 天</span>'
      + '</div>'
      + '<div class="stat" style="margin:6px 0;font-size:15px;">工作日系数(0~' + sh + '点/0~24点 比值均值): <b style="color:#1e40af;">' + cw.toFixed(4) + '</b>'
        + ' <span class="muted" style="font-size:12px;">(含周末全量 ' + coeff.toFixed(4) + ' · 汇总比值 ' + pooled.toFixed(4) + ')</span></div>'
      + '<div class="stat" style="margin:2px 0;">区间 0~' + sh + '点 合计 <b>¥' + fmtNum(tp) + '</b> · 0~24点 合计 <b>¥' + fmtNum(tf) + '</b></div>'
      + '<div class="muted" style="margin-top:4px;font-size:12px;">公式: 当天全天(0~24)待提现 ≈ 当天 0~' + sh + '点待提现 ÷ ' + cw.toFixed(4) + '</div>'
      + (function(){
           const N = ["周一","周二","周三","周四","周五","周六","周日"];
           const pw = s.per_weekday_avg || {};
           const wdLine = N.map((nm, i) => nm + ' ¥' + fmtNum(Number(pw[String(i)] || 0))).join(' · ');
           return '<div style="margin-top:8px;border-top:1px dashed #e5e7eb;padding-top:6px;">'
             + '<div class="stat" style="margin:2px 0;font-size:13px;">日均金额: 总体 <b>¥' + fmtNum(Number(s.overall_daily_avg || 0)) + '</b> · 工作日 <b>¥' + fmtNum(Number(s.weekday_daily_avg || 0)) + '</b> · 周末 <b style="color:#b45309;">¥' + fmtNum(Number(s.weekend_daily_avg || 0)) + '</b></div>'
             + '<div class="muted" style="margin-top:2px;font-size:12px;">各星期日均: ' + wdLine + '</div>'
             + '</div>';
         })()
      + (isActive ? '' : '<div class="row" style="margin-top:8px;"><button class="sec" onclick="setActiveCoefficient(' + k + ')">使用此月系数</button></div>')
      + '</div>';
  }).join('');
}

async function startAutoCoefficient(){
  $('autoNote').style.color = '#16a34a';
  $('autoNote').textContent = '抓取计算中(财务中心导出近1/2/3月,约1-2分钟)...';
  const r = await fetch('/api/auto-coefficient', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  const j = await r.json();
  if (j.started){
    $('runlog').textContent = j.msg + '\\n';
    pollLog();
  } else {
    $('autoNote').style.color = '#dc2626';
    $('autoNote').textContent = j.msg;
  }
}

async function setActiveCoefficient(key){
  $('autoNote').style.color = '#16a34a';
  $('autoNote').textContent = '切换中...';
  const r = await fetch('/api/coefficient-active', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key})});
  const j = await r.json();
  if (j.ok){
    $('autoNote').style.color = '#16a34a';
    $('autoNote').textContent = j.msg;
    refreshAutoCoefficient();
    refreshPredict();
    refreshCoefficient();
  } else {
    $('autoNote').style.color = '#dc2626';
    $('autoNote').textContent = '切换失败: ' + (j.error || '');
  }
}

loadSettings();
refreshPreview();
refreshStatus();
refreshHistory();
refreshPredict();
refreshDiff();
refreshCoefficient();
refreshAutoCoefficient();
setInterval(function(){ refreshStatus(); refreshHistory(); refreshPredict(); refreshDiff(); refreshCoefficient(); refreshAutoCoefficient(); }, 8000);
</script>

<!-- === 端口角标: 显示当前仪表盘实例的端口, 默认 8766; 否则红字提示是备用实例 === -->
<style>
  .port-badge {
    position: fixed; top: 10px; right: 10px; z-index: 9999;
    padding: 5px 12px; border-radius: 14px;
    font-size: 12px; font-weight: 600;
    background: #e0e7ff; color: #3730a3;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    user-select: none;
  }
  .port-badge.warn { background: #fee2e2; color: #991b1b; }
  .port-badge .dot { display: inline-block; width: 7px; height: 7px;
    border-radius: 50%; background: #16a34a; margin-right: 7px; vertical-align: middle; }
  .port-badge.warn .dot { background: #dc2626; }
  .port-badge a { color: inherit; text-decoration: underline; margin-left: 6px; }
</style>
<div id="portBadge" class="port-badge"><span class="dot"></span><span id="portBadgeText">…</span></div>
<script>
(function(){
  var p = String(window.location.port || (window.location.protocol==='https:'?'443':'80'));
  var txt = document.getElementById('portBadgeText');
  var badge = document.getElementById('portBadge');
  if (p === '8766') {
    txt.innerHTML = '端口 8766 <span style="opacity:.7">(固定默认)</span>';
  } else {
    txt.innerHTML = '端口 ' + p + ' <span style="opacity:.7">(固定默认 8766, 当前为备用)</span> · <a href="http://localhost:8766" target="_self">前往 8766</a>';
    badge.classList.add('warn');
    console.warn('[dashboard] 当前运行在备用端口 ' + p + '; 若要恢复固定默认 8766, 请先关闭占用 8766 的其它进程,然后重启本脚本。');
  }
})();
</script>
</body>
</html>"""


def main():
    import socket
    # 禁用地址复用: 在 Windows 上, 若不关闭 SO_REUSEADDR, 新进程会与占用 8765 的旧进程共享端口,
    # 导致访问时新旧代码随机命中。关闭后, 8765 被占用时 bind 会失败并自动回退到备用端口。
    ThreadingHTTPServer.allow_reuse_address = False
    server = None
    last_err = None
    for p in [PORT] + list(range(PORT + 1, PORT + 11)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError as e:
            last_err = e
            if p == PORT:
                print(f"[dashboard] 警告: 端口 {PORT} 已被占用 ({e}), 尝试备用端口...")
            server = None
            continue
    if server is None:
        print(f"[dashboard] 无法绑定任何端口 ({PORT}~{PORT + 10}): {last_err}")
        raise SystemExit(1)
    actual = server.server_address[1]
    print(f"[dashboard] 承运提现控制台已启动: http://localhost:{actual}")
    if actual != PORT:
        print(f"[dashboard] 注意: 默认端口 {PORT} 被占用,已使用 {actual}。请关闭占用 {PORT} 的旧进程后重启以恢复默认端口。")
    print(f"[dashboard] 按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] 已停止")


if __name__ == "__main__":
    main()

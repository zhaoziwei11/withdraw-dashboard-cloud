# -*- coding: utf-8 -*-
"""
承运云提现管理 - 每日提现数据统计脚本(工作日统计)

任务:
    09:00  统计"上一个工作日区间"内创建且状态为"待提现"的明细金额之和
    15:00  统计"上一个工作日区间"内创建且状态为"提现失败"的失败原因 Top3
    最终合并为同一张 Markdown 日报

统计范围(工作日补算周末):
    周一运行 -> 上周五 ~ 周日(覆盖周末)
    周二~周五运行 -> 仅昨天
    (周六/周日不运行,任务计划已限制为工作日)

日报文件名使用"运行日(今天)"日期,报告内标注统计范围。

用法:
    python withdraw_report.py --setup            # 首次登录配置(Edge  headed 模式)
    python withdraw_report.py --pending          # 9:00  待提现金额统计(需求一,并写入累积表+回填比对)
    python withdraw_report.py --fail             # 15:00 失败原因统计
    python withdraw_report.py --demand2          # 15:00 需求二:当天0~15点待提现+预测当天全天(0~24)待提现
    python withdraw_report.py --fail --demand2   # 15:00 两个任务一起跑(推荐,任务计划用这个)
    python withdraw_report.py --auto-coeff        # 自动抓取近1/2/3月数据计算三套系数(需求二)
    python withdraw_report.py --pending --debug  # 调试模式(headed)
    python withdraw_report.py --fail --debug      # 调试模式(headed)
"""

import argparse
import csv
import json
import os
import re
import sys
from urllib.parse import urlparse
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("[ERROR] Playwright 未安装,请先运行: pip install playwright && playwright install chromium")
    sys.exit(1)

# ============ 配置 ============
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SITES_PATH = SCRIPT_DIR / "sites.json"
with open(SITES_PATH, "r", encoding="utf-8") as f:
    SITES = json.load(f)

HEADLESS = CONFIG.get("headless", True)
TIMEOUT = CONFIG.get("timeout_ms", 30000)
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============ 站点相关全局变量(由 configure_site 赋值,默认 carrier) ============
BASE_URL = ""
TARGET_PAGE = ""
LOGIN_URL = ""
BROWSER_DATA_DIR = ""
OUTPUT_DIR = SCRIPT_DIR / "reports"
DEMAND2_DIR = SCRIPT_DIR / "demand2"
PENDING_LEDGER = SCRIPT_DIR / "pending_ledger.csv"
COEFFICIENT_FILE = DEMAND2_DIR / "coefficient.json"          # 需求二:系数
COEFFICIENT_CHANGELOG = DEMAND2_DIR / "coefficient_changelog.csv"  # 需求二:系数变更记录
FORECAST_CSV = DEMAND2_DIR / "forecast.csv"                  # 需求二:预测与比对记录
FORECAST_TEMPLATE = DEMAND2_DIR / "forecast_template.csv"    # 需求二:导入模板
COEFFICIENTS_AUTO_FILE = DEMAND2_DIR / "coefficients_auto.json"     # 需求二:自动抓取算出的三套系数(近1/2/3月)
SITE_PREFIX = ""
COEFF_EXCLUDE_THRESHOLD = 0
SITE_NAME = "carrier"
USE_CDP = False   # admin 手动模式: 通过本机 Edge 调试端口接管用户已打开的网页取数


def configure_site(name):
    """按站点名设置全局路径/URL/系数阈值。carrier 与默认一致,admin 走独立前缀 + 系数剔除(≥20万)。"""
    global BASE_URL, TARGET_PAGE, LOGIN_URL, BROWSER_DATA_DIR, OUTPUT_DIR
    global DEMAND2_DIR, PENDING_LEDGER, COEFFICIENT_FILE, COEFFICIENT_CHANGELOG
    global FORECAST_CSV, FORECAST_TEMPLATE, COEFFICIENTS_AUTO_FILE
    global SITE_PREFIX, COEFF_EXCLUDE_THRESHOLD, SITE_NAME
    if name not in SITES:
        raise RuntimeError(f"未知站点: {name} (可选: {', '.join(SITES)})")
    s = SITES[name]
    SITE_NAME = name
    BASE_URL = s["base_url"]
    TARGET_PAGE = s["target_page"]
    LOGIN_URL = s.get("login_url", f"{BASE_URL}/login")
    BROWSER_DATA_DIR = s.get("browser_data_dir", CONFIG["browser_data_dir"])
    OUTPUT_DIR = Path(s.get("output_dir", CONFIG["output_dir"]))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(BROWSER_DATA_DIR).mkdir(parents=True, exist_ok=True)
    prefix = s.get("prefix", "")
    SITE_PREFIX = prefix
    DEMAND2_DIR = SCRIPT_DIR / s.get("demand2_dir", "demand2")
    DEMAND2_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_LEDGER = SCRIPT_DIR / f"{prefix}pending_ledger.csv"
    COEFFICIENT_FILE = DEMAND2_DIR / f"{prefix}coefficient.json"
    COEFFICIENT_CHANGELOG = DEMAND2_DIR / f"{prefix}coefficient_changelog.csv"
    FORECAST_CSV = DEMAND2_DIR / f"{prefix}forecast.csv"
    FORECAST_TEMPLATE = DEMAND2_DIR / f"{prefix}forecast_template.csv"
    COEFFICIENTS_AUTO_FILE = DEMAND2_DIR / f"{prefix}coefficients_auto.json"
    COEFF_EXCLUDE_THRESHOLD = int(s.get("coeff_exclude_threshold", 0))


configure_site("carrier")  # 默认站点

# 列名(按真实页面)
COL_CREATE_TIME = "创建时间"
COL_AMOUNT = "金额"
COL_FAIL_REASON = "失败原因"
COL_STATUS = "提现状态"
COL_DRIVER_NAME = "司机姓名"
COL_PHONE = "手机号"
COL_CARD = "银行卡号"

# ============ 工具函数 ============
def now_str():
    return datetime.now().strftime("%H:%M:%S")


def get_run_date():
    """运行日(今天),用于日报/数据文件名"""
    return datetime.now().strftime("%Y-%m-%d")


def get_business_range(start_date=None, end_date=None):
    """返回统计范围 (start, end)

    显式传 start_date / end_date(YYYY-MM-DD):直接返回(用于节假日累计、自定义区间)。
    否则按工作日补算:
        周一运行: 上一个工作日是上周五,结束为昨天(周日) -> 上周五~周日
        周二~周五运行: 开始=结束=昨天(单日)
    """
    if start_date and end_date:
        return start_date, end_date
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    if today.weekday() == 0:  # 周一
        start = today - timedelta(days=3)  # 上周五
    else:
        start = yesterday
    return start.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")


def get_data_file(run_date):
    return DATA_DIR / f"{SITE_PREFIX}withdraw_data_{run_date}.json"


def get_report_file(run_date):
    return OUTPUT_DIR / f"{SITE_PREFIX}withdraw_report_{run_date}.md"


def save_data(report_date, pending_amount=None, pending_count=None, fail_reasons=None,
              fail_records=None, demand2_today_pending=None, coefficient=None, predicted_full=None,
              predict_mode=None, predict_input=None, predict_breakdown=None):
    """增量保存数据到 JSON"""
    path = get_data_file(report_date)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    if pending_amount is not None:
        data["pending_amount"] = pending_amount
    if pending_count is not None:
        data["pending_count"] = pending_count
    if fail_reasons is not None:
        data["fail_reasons"] = fail_reasons
    if fail_records is not None:
        data["fail_records"] = fail_records
    if demand2_today_pending is not None:
        data["demand2_today_pending"] = demand2_today_pending
    if coefficient is not None:
        data["coefficient"] = coefficient
    if predicted_full is not None:
        data["predicted_full"] = predicted_full
    if predict_mode is not None:
        data["predict_mode"] = predict_mode
    if predict_input is not None:
        data["predict_input"] = predict_input
    if predict_breakdown is not None:
        data["predict_breakdown"] = predict_breakdown

    data["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_data(report_date):
    path = get_data_file(report_date)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ============ 需求一/需求二 辅助 ============
def parse_amount_str(s):
    """从字符串提取金额(支持 ¥、千分位、负号)"""
    if s is None:
        return 0.0
    s = str(s).replace(",", "").replace("¥", "").replace("￥", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        return 0.0


# 系数逻辑: 系数 = 每日(创建时间 0~SPLIT_HOUR 点金额 / 创建时间 0~24 点金额) 的均值
# 15:00 观测当天 0~SPLIT_HOUR 点待提现 ÷ 系数 ≈ 当天全天(0~24点)待提现
SPLIT_HOUR = 15


def parse_datetime_flex(s):
    """从 创建时间 字符串解析出 datetime(兼容 '2026-07-27 23:57:08' / '2026-07-27' / '2026/7/27 9:3')"""
    if s is None:
        return None
    s = str(s).strip()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?", s)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mi = int(m.group(5) or 0)
        ss = int(m.group(6) or 0)
        return datetime(y, mo, d, hh, mi, ss)
    except ValueError:
        return None


def get_today_range():
    """需求二: 统计当天(创建时间=今天)"""
    today = datetime.now().date()
    return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def get_previous_business_day(ref):
    """返回 ref 之前的最后一个工作日(跳过周末)"""
    d = ref - timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六 6=周日
        d -= timedelta(days=1)
    return d


# ---------- 需求一: 待提现累积表 ----------
def append_pending_ledger(run_date, start, end, count, amount):
    """需求一: 把 09:00 待提现数据追加到累积表"""
    header = ["run_date", "stat_range_start", "stat_range_end",
              "pending_count", "pending_amount", "generated_at"]
    exists = PENDING_LEDGER.exists()
    with open(PENDING_LEDGER, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerow([run_date, start, end, count, f"{amount:.2f}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    print(f"[OK] 已写入待提现累积表: {PENDING_LEDGER}")


# ---------- 需求二: 系数 / 预测 / 比对 ----------
def load_coefficient():
    if COEFFICIENT_FILE.exists():
        try:
            return json.loads(COEFFICIENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_coefficient(info):
    COEFFICIENT_FILE.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def last_weekend_components(coeff_dict):
    """从系数文件的 daily_partial/daily_full 取最近一个完整周末(周五/六/日)的实际金额。

    返回 dict: {fri_date, fri_partial, sat_date, sat_full, sun_date, sun_full} 或 None。
    用于周一预测: 预测(周五~周日合计) = 上周五全天(0~24, 由 0~15÷系数推算) + 周六0~24 + 周日0~24。
    系数文件由 --auto-coeff 每周一06:00 刷新, 含最近一个完整周末的真实金额。
    """
    if not coeff_dict:
        return None
    daily_full = coeff_dict.get("daily_full", {})
    daily_partial = coeff_dict.get("daily_partial", {})
    if not daily_full:
        return None
    fridays = sorted(
        d for d in daily_full
        if datetime.strptime(d, "%Y-%m-%d").date().weekday() == 4
    )
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


def _parse_date_flex(s):
    """从创建时间/日期字符串解析出 date 对象(兼容 '2026-07-24 10:00:00' / '2026-07-24' / '2026/7/24')"""
    if s is None:
        return None
    s = str(s).strip()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        return None


def _find_col(fieldnames, keys):
    """按优先级 keys 查找第一个匹配的列名(优先匹配排在前的关键字)"""
    for key in keys:
        for k in fieldnames:
            if key in k.lower():
                return k
    return None


def compute_coeff_from_export(csv_path, label="近1月", exclude_threshold=0):
    """从导出 CSV(表头含 创建时间 + 金额)按日汇总「创建时间 0~SPLIT_HOUR 点」与「0~24 点」金额,
    计算系数 = 每日(0~SPLIT_HOUR点金额 / 0~24点金额) 的均值(用户选定: 每日比值取平均)。

    exclude_threshold: 单笔金额 >= 该阈值的记录整条剔除(不参与系数计算);=0 表示不剔除。
        (admin 站点用 200000:剔除 20万以上大金额,避免偶发大额扭曲 0~15/0~24 比值)

    返回: coeff(主系数), pooled(汇总比值参考), day_count, total_partial(区间0~SPLIT_HOUR合计),
    total_full(区间0~24合计), daily_partial, daily_full, ratios, sample_n_rows 等。
    """
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [c.strip() for c in (reader.fieldnames or [])]
        rows = list(reader)
    date_col = _find_col(fieldnames, ["创建时间", "日期", "date", "时间"])
    amount_col = _find_col(fieldnames, ["金额", "提现金额", "amount"])
    if not (date_col and amount_col):
        raise RuntimeError(f"表格列不匹配,需要包含:创建时间(或日期) + 金额。当前列: {fieldnames}")

    daily_partial = {}   # date -> 0~SPLIT_HOUR 点金额合计
    daily_full = {}      # date -> 0~24 点金额合计
    n = 0
    for r in rows:
        dt = parse_datetime_flex(r.get(date_col, ""))
        if dt is None:
            continue
        amt = parse_amount_str(r.get(amount_col, ""))
        if amt == 0 and not str(r.get(amount_col, "")).strip():
            continue
        # 大金额剔除: 单笔 >= 阈值 的记录整条排除(不参与系数/预测计算);阈值=0 表示不剔除
        if exclude_threshold > 0 and amt >= exclude_threshold:
            continue
        d = dt.date()
        daily_full[d] = daily_full.get(d, 0.0) + amt
        if dt.hour < SPLIT_HOUR:
            daily_partial[d] = daily_partial.get(d, 0.0) + amt
        n += 1
    if not daily_full:
        raise RuntimeError("有效数据行为 0(需要 创建时间 + 金额 均有值)")

    ratios = []
    for d in sorted(daily_full):
        full = daily_full[d]
        if full > 0:
            ratios.append(daily_partial.get(d, 0.0) / full)
    coeff = round(sum(ratios) / len(ratios), 6) if ratios else 0.0
    # 工作日专属比值系数(仅工作日参与): 自动化预测只在工作日跑,工作日系数对预测更准
    wd_ratios = []
    for d in sorted(daily_full):
        if d.weekday() < 5 and daily_full[d] > 0:
            wd_ratios.append(daily_partial.get(d, 0.0) / daily_full[d])
    coeff_weekday = round(sum(wd_ratios) / len(wd_ratios), 6) if wd_ratios else 0.0
    total_partial = sum(daily_partial.values())
    total_full = sum(daily_full.values())
    pooled = round(total_partial / total_full, 6) if total_full else 0.0

    # —— 日均金额(按星期拆分,仅作信息展示,不影响比值系数) ——
    wk_full = {}
    wk_days = {}
    for d, full in daily_full.items():
        wd = d.weekday()  # 0=周一 ... 6=周日
        wk_full[wd] = wk_full.get(wd, 0.0) + full
        wk_days[wd] = wk_days.get(wd, 0) + 1
    per_weekday_avg = {str(wd): round(wk_full[wd] / wk_days[wd], 2) for wd in sorted(wk_full)}
    overall_daily_avg = round(total_full / len(daily_full), 2)
    wd_days = [d for d in daily_full if d.weekday() < 5]
    we_days = [d for d in daily_full if d.weekday() >= 5]
    weekday_daily_avg = round(sum(daily_full[d] for d in wd_days) / len(wd_days), 2) if wd_days else 0.0
    weekend_daily_avg = round(sum(daily_full[d] for d in we_days) / len(we_days), 2) if we_days else 0.0

    return {
        "source": label,
        "computed_at": datetime.now().isoformat(),
        "split_hour": SPLIT_HOUR,
        "method": f"系数 = 每日(创建时间0~{SPLIT_HOUR}点金额 / 创建时间0~24点金额) 的均值",
        "sample_n_rows": n,
        "date_min": min(daily_full).strftime("%Y-%m-%d"),
        "date_max": max(daily_full).strftime("%Y-%m-%d"),
        "day_count": len(daily_full),
        "coeff": coeff,
        "coeff_weekday": coeff_weekday,
        "pooled": pooled,
        "total_partial": round(total_partial, 2),
        "total_full": round(total_full, 2),
        "daily_partial": {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in sorted(daily_partial.items())},
        "daily_full": {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in sorted(daily_full.items())},
        "ratios": [round(r, 6) for r in ratios],
        "overall_daily_avg": overall_daily_avg,
        "weekday_daily_avg": weekday_daily_avg,
        "weekend_daily_avg": weekend_daily_avg,
        "per_weekday_avg": per_weekday_avg,
    }


# ============ 需求二: 自动抓取计算系数(无需手动导入) ============
AUTO_RANGES = [(30, "1m", "近1月"), (60, "2m", "近2月"), (90, "3m", "近3月")]


def export_daily_csv(page, start_date, end_date, status="全部", key="1m"):
    """点「导出」下载当前筛选区间的全部明细(xlsx),跳过标题行转 CSV,
    返回 CSV 路径(供 compute_coeff_from_export 复用)。status=全部 表示忽略状态筛选。"""
    print(f"  -> 导出每日明细: {start_date} ~ {end_date}, 状态={status}")
    set_create_time_range(page, start_date, end_date)
    set_withdraw_status(page, status)
    click_query(page)
    page.wait_for_timeout(800)
    try:
        with page.expect_download(timeout=60000) as dl_info:
            page.locator(":text('导出')").first.click()
    except Exception as e:
        raise RuntimeError(f"点击导出按钮失败(可能登录态过期或未找到导出按钮): {e}")
    dl = dl_info.value
    suffix = (dl.suggested_filename.split('.')[-1] or "xlsx").lower()
    tmp_xlsx = DEMAND2_DIR / f"_auto_export_{key}.xlsx"
    dl.save_as(str(tmp_xlsx))
    # 跳过标题行,转成 CSV(compute_coeff_from_export 以首行为表头)
    from openpyxl import load_workbook
    import csv as _csv
    wb = load_workbook(tmp_xlsx, data_only=True)
    ws = wb.active
    rows = list(ws.values)
    header_idx = 0
    for i, r in enumerate(rows):
        cells = " ".join(str(c) for c in r if c is not None)
        if "创建时间" in cells or "金额" in cells:
            header_idx = i
            break
    header = [("" if c is None else str(c).strip()) for c in rows[header_idx]]
    data_rows = rows[header_idx + 1:]
    csv_path = DEMAND2_DIR / f"_auto_export_{key}.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(header)
        for r in data_rows:
            w.writerow([("" if c is None else c) for c in r])
    try:
        tmp_xlsx.unlink()
    except Exception:
        pass
    print(f"  [OK] 导出完成: {csv_path} ({len(data_rows)} 行)")
    return csv_path


def append_coefficient_changelog(old_info, new_info):
    """需求二: 每次系数更新,把「旧系数 → 新系数」追加到变更记录 CSV。

    old_info/new_info 为 load_coefficient() 的返回(dict 或 None)。
    记录字段: 时间, 来源(区间/auto_key), 样本数, 区间起止, 旧系数, 新系数,
              旧汇总比值, 新汇总比值, 天数, 状态。
    """
    def g(info, key):
        return round(float(info.get(key, 0) or 0), 6) if info else 0.0

    old_exists = bool(old_info)
    row = {
        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": new_info.get("source", new_info.get("auto_key", "")),
        "sample_n_rows": new_info.get("sample_n_rows", ""),
        "date_min": new_info.get("date_min", ""),
        "date_max": new_info.get("date_max", ""),
        "old_coeff": g(old_info, "coeff"),
        "new_coeff": g(new_info, "coeff"),
        "old_pooled": g(old_info, "pooled"),
        "new_pooled": g(new_info, "pooled"),
        "day_count": new_info.get("day_count", ""),
        "status": "替换" if old_exists else "新增",
    }
    header = ["imported_at", "source", "sample_n_rows", "date_min", "date_max",
              "old_coeff", "new_coeff", "old_pooled", "new_pooled", "day_count", "status"]
    exists = COEFFICIENT_CHANGELOG.exists()
    with open(COEFFICIENT_CHANGELOG, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow(row)
    print(f"[OK] 已写入系数变更记录: {COEFFICIENT_CHANGELOG} (状态={row['status']})")


def read_coefficient_changelog(limit=20):
    """读取系数变更记录(倒序,最近在前)"""
    if not COEFFICIENT_CHANGELOG.exists():
        return []
    with open(COEFFICIENT_CHANGELOG, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r.get("imported_at", ""), reverse=True)
    return rows[:limit]


def _sync_active_to_coefficient(key, info):
    """把选中的自动系数集合写入 coefficient.json(供预测管线),并留变更记录"""
    old_info = load_coefficient()
    new_info = dict(info)
    new_info["source_file"] = new_info.get("source_file", f"自动-{key}")
    new_info["auto_key"] = key
    save_coefficient(new_info)
    append_coefficient_changelog(old_info, new_info)
    print(f"[OK] 已应用 active={key} 到 coefficient.json")


def auto_compute_coefficients():
    """自动从财务中心抓取近1/2/3月(排除当天)数据,计算三套系数,写入 coefficients_auto.json。
    默认 active=近1月(若已有选择则保留)。active 对应系数同步写入 coefficient.json 供预测使用。
    """
    today = date.today()
    end = (today - timedelta(days=1)).strftime("%Y-%m-%d")  # 不含当天
    sets = {}
    active = "1m"
    if COEFFICIENTS_AUTO_FILE.exists():
        try:
            prev = json.loads(COEFFICIENTS_AUTO_FILE.read_text(encoding="utf-8"))
            if prev.get("active") in ("1m", "2m", "3m"):
                active = prev["active"]
        except Exception:
            pass

    try:
        page, cleanup = acquire_page(False)
    except CdpError as e:
        print(str(e))
        return None
    if page is None:
        return None
    try:
        for days, key, label in AUTO_RANGES:
            start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
            csv_path = export_daily_csv(page, start, end, status="全部", key=key)
            try:
                stats = compute_coeff_from_export(str(csv_path), label=label,
                                                  exclude_threshold=COEFF_EXCLUDE_THRESHOLD)
            finally:
                try:
                    csv_path.unlink()
                except Exception:
                    pass
            stats["range_start"] = start
            stats["range_end"] = end
            sets[key] = stats
            print(f"[OK] {label}: 样本 {stats['sample_n_rows']} 行 / {stats['day_count']} 天, "
                  f"系数(每日0~{stats['split_hour']}点/0~24点比值均值) = {stats['coeff']:.4f} "
                  f"(汇总比值 {stats['pooled']:.4f})")
    finally:
        cleanup()

    payload = {"updated_at": datetime.now().isoformat(), "active": active, "sets": sets}
    COEFFICIENTS_AUTO_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 三套系数已写入: {COEFFICIENTS_AUTO_FILE} (active={active})")

    if active in sets and "coeff" in sets[active]:
        _sync_active_to_coefficient(active, sets[active])
    else:
        for k in ("1m", "2m", "3m"):
            if k in sets and "coeff" in sets[k]:
                payload["active"] = k
                COEFFICIENTS_AUTO_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                _sync_active_to_coefficient(k, sets[k])
                print(f"[WARN] active={active} 无数据,回退为 {k}")
                break
    return payload


def apply_active_coefficient(key):
    """用户切换 active 系数:把 coefficients_auto.json 中对应集合写入 coefficient.json"""
    if key not in ("1m", "2m", "3m"):
        raise RuntimeError(f"无效的系数key: {key}")
    if not COEFFICIENTS_AUTO_FILE.exists():
        raise RuntimeError("尚未自动计算系数,请先点「自动抓取并计算系数」")
    data = json.loads(COEFFICIENTS_AUTO_FILE.read_text(encoding="utf-8"))
    sets = data.get("sets", {})
    if key not in sets or "coeff" not in sets[key]:
        raise RuntimeError(f"系数集合 {key} 无数据,无法应用")
    data["active"] = key
    COEFFICIENTS_AUTO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _sync_active_to_coefficient(key, sets[key])
    return data


def read_forecast_rows():
    if not FORECAST_CSV.exists():
        return []
    with open(FORECAST_CSV, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_forecast_rows(rows):
    fieldnames = ["predict_date", "today_pending_15", "coefficient",
                  "predicted_full", "predict_mode",
                  "actual_next_day_pending_09",
                  "diff", "diff_pct", "compared_at", "status"]
    with open(FORECAST_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def append_or_update_forecast(predict_date, today_pending, coefficient, predicted, predict_mode=None):
    rows = read_forecast_rows()
    found = False
    for r in rows:
        if r.get("predict_date") == predict_date:
            r["today_pending_15"] = f"{today_pending:.2f}"
            r["coefficient"] = f"{coefficient:.6f}" if coefficient is not None else ""
            r["predicted_full"] = f"{predicted:.2f}" if predicted is not None else ""
            if predict_mode is not None:
                r["predict_mode"] = predict_mode
            found = True
            break
    if not found:
        rows.append({
            "predict_date": predict_date,
            "today_pending_15": f"{today_pending:.2f}",
            "coefficient": f"{coefficient:.6f}" if coefficient is not None else "",
            "predicted_full": f"{predicted:.2f}" if predicted is not None else "",
            "predict_mode": predict_mode or "",
            "actual_next_day_pending_09": "",
            "diff": "",
            "diff_pct": "",
            "compared_at": "",
            "status": "pending",
        })
    write_forecast_rows(rows)
    print(f"[OK] 已写入预测记录: {FORECAST_CSV}")


def fill_forecast_comparison(run_date, today_pending_amount):
    """需求一(09:00) 回填预测比对: 用上一工作日的预测对比今日真实待提现"""
    today = datetime.strptime(run_date, "%Y-%m-%d").date()
    prev_bd = get_previous_business_day(today)
    prev_bd_str = prev_bd.strftime("%Y-%m-%d")
    rows = read_forecast_rows()
    updated = None
    for r in rows:
        if r.get("predict_date") == prev_bd_str and not r.get("actual_next_day_pending_09"):
            # 周一预测为"上周五~周日合计", 口径与次日09待提现不同, 不在此比对
            if r.get("predict_mode") == "monday":
                continue
            actual = today_pending_amount
            predicted = parse_amount_str(r.get("predicted_full", ""))
            diff = actual - predicted if predicted else None
            diff_pct = (diff / predicted * 100) if (predicted and predicted != 0) else None
            r["actual_next_day_pending_09"] = f"{actual:.2f}"
            r["diff"] = f"{diff:.2f}" if diff is not None else ""
            r["diff_pct"] = f"{diff_pct:.2f}" if diff_pct is not None else ""
            r["compared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            r["status"] = "compared"
            updated = r
            break
    if updated:
        write_forecast_rows(rows)
        pred = parse_amount_str(updated.get("predicted_full", ""))
        print(f"[OK] 已回填比对: 预测基于 {prev_bd_str}, 真实次日09待提现 ¥{today_pending_amount:,.2f}, "
              f"差异 ¥{today_pending_amount - pred:,.2f}")
    else:
        print(f"[INFO] 无待比对预测(上一工作日 {prev_bd_str} 无预测记录)")
    return updated


def read_forecast_comparisons(limit=10):
    rows = read_forecast_rows()
    compared = [r for r in rows if r.get("status") == "compared"]
    compared.sort(key=lambda r: r.get("predict_date", ""), reverse=True)
    return compared[:limit]


# ============ 登录态管理 ============
def is_logged_in(page):
    """检查是否已登录(没跳转到登录页就算已登录)"""
    current_url = page.url
    if "/login" in current_url or "login" in current_url.lower():
        return False
    return True


def setup_login():
    """首次登录配置:headed 模式打开 Edge,用户手动登录"""
    print("=" * 50)
    print("  首次登录配置")
    print("  Edge 浏览器会打开,请手动登录你的账号")
    print("  登录成功后,回到这里按回车继续")
    print("=" * 50)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=False,
            channel="msedge",
            viewport={"width": 1440, "height": 900},
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)

        input("\n>>> 登录成功后,按回车继续保存登录态...")

        # 等页面稳定(登录后系统常会跳到 /home 等中间页)
        page.wait_for_timeout(3000)

        # 验证登录状态:只要当前不在登录页/认证页即可
        current_url = page.url
        if "/login" in current_url or "auth.91msl" in current_url:
            print("[WARN] 当前还在登录页,请重新运行 --setup")
        else:
            print(f"[OK] 检测到已登录(当前页: {current_url})")
            print("[OK] 登录态已保存,可以正常运行了")

        context.close()
        print("[OK] 浏览器已关闭,登录态已持久化")


# ============ 浏览器启动/页面打开 ============
def launch_context(p, debug=False):
    """启动 Edge 持久化浏览器上下文"""
    return p.chromium.launch_persistent_context(
        user_data_dir=BROWSER_DATA_DIR,
        headless=HEADLESS if not debug else False,
        channel="msedge",
        viewport={"width": 1440, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )


def open_target_page(page):
    """打开目标页面并检查登录状态"""
    print(f"[{now_str()}] 打开提现管理页面...")
    page.goto(TARGET_PAGE, wait_until="networkidle", timeout=60000)

    if not is_logged_in(page):
        print("[ERROR] 未登录!请先运行: python withdraw_report.py --setup")
        return False

    page.wait_for_timeout(2000)
    return True


class CdpError(RuntimeError):
    """CDP 手动取数模式下的友好错误: 网页未打开 / 未登录 / 连接失败"""


def acquire_page(debug=False):
    """统一取数入口, 返回 (page, cleanup_callable)。

    CDP 模式 (USE_CDP=True, admin 手动模式):
        连接本机带 --remote-debugging-port=9222 的 Edge, 接管用户**已打开并登录**的
        admin 页面取数; 不关闭用户浏览器(只 disconnect)。
        找不到 admin 页面 / 处于登录页 -> 抛 CdpError(友好提示)。
    普通模式 (承运自动化):
        启持久化 Edge context, 打开目标页并校验登录; 结束时 close。
    """
    if USE_CDP:
        host = urlparse(BASE_URL).netloc
        try:
            p = sync_playwright().start()
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            raise CdpError(
                "[ERROR] 无法连接本机 Edge 调试端口(9222)。\n"
                "        请先双击 open_admin_debug.bat 打开 admin 网页并保持窗口打开, 再获取。"
            )
        admin_page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if host in (pg.url or ""):
                    admin_page = pg
                    break
            if admin_page:
                break
        if admin_page is None:
            _safe_cdp_disconnect(browser, p)
            raise CdpError(
                "[ERROR] 网页未打开：本机 Edge 中未找到已打开的 admin 页面。\n"
                "        请先双击 open_admin_debug.bat 打开 admin 网页并登录, 保持窗口打开。"
            )
        if "/login" in (admin_page.url or "").lower():
            _safe_cdp_disconnect(browser, p)
            raise CdpError(
                "[ERROR] 网页未登录：admin 页面当前处于登录页, 无法获取数据。\n"
                "        请在打开的 admin 网页上完成登录(含审核授权)后再获取。"
            )
        admin_page.set_default_timeout(TIMEOUT)

        def cleanup():
            _safe_cdp_disconnect(browser, p)
        return admin_page, cleanup
    else:
        p = sync_playwright().start()
        context = launch_context(p, debug)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(TIMEOUT)
        if not open_target_page(page):
            context.close()
            p.stop()
            return None, (lambda: None)

        def cleanup():
            try:
                context.close()
            except Exception:
                pass
            try:
                p.stop()
            except Exception:
                pass
        return page, cleanup


def _safe_cdp_disconnect(browser, p):
    """断开 CDP 连接(不关闭用户浏览器)并停止 playwright"""
    try:
        browser.disconnect()
    except Exception:
        pass
    try:
        p.stop()
    except Exception:
        pass


# ============ 筛选操作 ============
def find_field_container(label_text, child_selector=None):
    """返回一段 JS 函数,用于通过 .el-form-item__label 文本找到字段容器
    child_selector: 容器内必须包含的子元素选择器(可选)
    """
    child_check = f"""var matches = container.querySelectorAll('{child_selector}'); if (matches.length === 0) continue;""" if child_selector else ""
    return f"""
        (function() {{
            var candidates = Array.from(document.querySelectorAll('.el-form-item__label'))
                .filter(el => el.textContent && el.textContent.trim().includes('{label_text}'));
            for (var i = 0; i < candidates.length; i++) {{
                var label = candidates[i];
                var container = label.closest('.el-form-item');
                if (!container) continue;
                {child_check}
                return container;
            }}
            throw new Error('找不到合适的 label 容器: {label_text}');
        }})()
    """


def set_create_time_range(page, start_date, end_date):
    """设置创建时间范围:用 Playwright fill 模拟用户输入"""
    print(f"  -> 设置创建时间: {start_date} ~ {end_date}")

    # 通过 label 找到"创建时间"表单项,再取其中的 daterange 两个 input
    try:
        label = page.locator(".el-form-item__label:text-is('创建时间')")
        label.wait_for(timeout=10000)
        form_item = label.locator("xpath=..")
        inputs = form_item.locator(".el-form-item__content .el-date-editor--daterange input").all()
        if len(inputs) < 2:
            raise RuntimeError("创建时间编辑器下未找到两个 input")
    except Exception as e:
        # 兜底:直接用页面上第一个 daterange 的两个 input
        inputs = page.locator(".el-date-editor--daterange input").all()[:2]
        if len(inputs) < 2:
            raise RuntimeError(f"无法定位创建时间输入框: {e}")

    inputs[0].click(timeout=5000)
    inputs[0].fill(start_date)
    page.wait_for_timeout(300)
    inputs[1].click(timeout=5000)
    inputs[1].fill(end_date)
    inputs[1].press("Tab")
    page.wait_for_timeout(600)


def set_withdraw_status(page, status_text):
    """设置提现状态下拉框:按原始成功方式查找 label→容器→select,优先 Vue 设置"""
    print(f"  -> 设置提现状态: {status_text}")

    res = page.evaluate(
        """(status_text) => {
            // 最稳定位:通过 placeholder "请选择提现状态" 找到 select 容器
            let selectWrap = null;
            const placeholderInput = document.querySelector("input[placeholder='请选择提现状态']");
            if (placeholderInput) {
                selectWrap = placeholderInput.closest('.el-select');
            }
            // 兜底:按 label 文本找
            if (!selectWrap) {
                let labelEl = Array.from(document.querySelectorAll('.el-form-item__label'))
                    .find(el => el.textContent && el.textContent.trim().includes('提现状态'));
                if (!labelEl) {
                    const labels = Array.from(document.querySelectorAll('label, span, div'));
                    labelEl = labels.find(el => el.textContent && el.textContent.trim().includes('提现状态'));
                }
                if (labelEl) {
                    selectWrap = labelEl.closest('.el-form-item, .el-col, div')?.querySelector('.el-select');
                    if (!selectWrap) {
                        let sibling = labelEl.nextElementSibling;
                        while (sibling) {
                            const s = sibling.querySelector('.el-select');
                            if (s) { selectWrap = s; break; }
                            sibling = sibling.nextElementSibling;
                        }
                    }
                }
            }
            if (!selectWrap) return {error: 'select not found', hasPlaceholder: !!placeholderInput};

            // 优先 Vue 直接设置
            const vue = selectWrap.__vue__ || selectWrap.__VUE__;
            if (vue && vue.handleOptionSelect) {
                const option = (vue.options || []).find(o =>
                    (o.currentLabel || o.label || '') === status_text
                );
                if (option) {
                    vue.handleOptionSelect(option, true);
                    const input = selectWrap.querySelector('.el-input__inner');
                    return {ok: true, via: 'vue', selected: option.currentLabel || option.label, value: input ? input.value : ''};
                }
            }

            // 兜底点击 input 展开,然后从所有下拉面板中找到含目标选项的那个
            const input = selectWrap.querySelector('.el-input__inner') || selectWrap.querySelector('input');
            if (!input) return {error: 'input not found'};
            input.click();
            let option = null;
            for (let i = 0; i < 30; i++) {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const d of dropdowns) {
                    const opts = d.querySelectorAll('.el-select-dropdown__item');
                    option = Array.from(opts).find(o => o.textContent.trim() === status_text);
                    if (option) break;
                }
                if (option) break;
                const start = Date.now();
                while (Date.now() - start < 100) {}
            }
            if (!option) return {error: 'option not found after click'};
            option.click();
            return {ok: true, via: 'click', selected: option.textContent.trim()};
        }""",
        status_text,
    )
    if not res.get("ok"):
        raise RuntimeError(f"提现状态设置失败: {res}")
    page.wait_for_timeout(600)


def verify_filters(page, expected_status, start_date, end_date):
    """校验筛选条件是否真的生效,未生效则抛异常"""
    date_container = find_field_container("创建时间", child_selector=".el-date-editor--daterange")
    res = page.evaluate(
        """([dateContainerExpr, expected_status, start_date, end_date]) => {
            const dateContainer = eval(dateContainerExpr);
            const inputs = dateContainer.querySelectorAll('.el-date-editor--daterange input');
            const actual_start = inputs[0] ? inputs[0].value : '';
            const actual_end = inputs[1] ? inputs[1].value : '';

            // 通过 placeholder 找到状态 select,读 selectedLabel(不一定在 input.value 里)
            let selected_status = '';
            const placeholderInput = document.querySelector("input[placeholder='请选择提现状态']");
            if (placeholderInput) {
                const selectWrap = placeholderInput.closest('.el-select');
                if (selectWrap) {
                    const vue = selectWrap.__vue__ || selectWrap.__VUE__;
                    selected_status = (vue && vue.selectedLabel) ? vue.selectedLabel : '';
                    if (!selected_status) {
                        const selectedItem = selectWrap.querySelector('.el-select__selected-item');
                        if (selectedItem) selected_status = selectedItem.innerText.trim();
                    }
                }
            }

            const firstRow = document.querySelector('.el-table__body-wrapper .el-table__row, .el-table__body .el-table__row');
            let rowStatus = '';
            if (firstRow) {
                const headers = Array.from(document.querySelectorAll('.el-table__header-wrapper th .cell, .el-table__header th .cell'));
                const statusIdx = headers.findIndex(h => h.textContent.includes('提现状态'));
                const cells = firstRow.querySelectorAll('td');
                rowStatus = statusIdx >= 0 && cells[statusIdx] ? cells[statusIdx].innerText.trim() : '';
            }
            return {actual_start, actual_end, selected_status, rowStatus};
        }""",
        [date_container, expected_status, start_date, end_date],
    )
    print(f"  [VERIFY] 创建时间: {res['actual_start']} ~ {res['actual_end']}")
    print(f"  [VERIFY] 提现状态: {res['selected_status']}")
    print(f"  [VERIFY] 首行状态: {res['rowStatus']}")
    if start_date not in res["actual_start"] or end_date not in res["actual_end"]:
        raise RuntimeError(f"创建时间校验失败: 期望 {start_date}~{end_date}, 实际 {res['actual_start']}~{res['actual_end']}")
    # 状态以表格首行为准(最可靠);select 的 selectedLabel 仅作参考
    if res["rowStatus"] and expected_status not in res["rowStatus"]:
        raise RuntimeError(f"表格首行状态校验失败: 期望包含 {expected_status}, 实际 {res['rowStatus']}")


def click_query(page):
    """点击查询按钮"""
    print("  -> 点击查询")
    page.locator("button:has-text('查询'), .el-button--primary:has-text('查询')").first.click(timeout=10000)
    # 等表格刷新:先让 loading 消失,再让行出现
    page.wait_for_timeout(2500)


def set_filters(page, start_date, end_date, status_text):
    """设置完整筛选条件并查询,查询后校验是否生效"""
    set_create_time_range(page, start_date, end_date)
    set_withdraw_status(page, status_text)
    click_query(page)
    verify_filters(page, status_text, start_date, end_date)


# ============ 表格读取 ============
def wait_table_loaded(page):
    """等待表格有数据行"""
    try:
        page.wait_for_selector(".el-table__body-wrapper .el-table__row, .el-table__body .el-table__row", timeout=30000)
        page.wait_for_timeout(1500)
    except PlaywrightTimeout:
        # 可能无数据:等无数据提示
        page.wait_for_timeout(2000)


def get_column_index(page, column_name):
    """根据表头文本找到列索引"""
    headers = page.locator(".el-table__header-wrapper th .cell, .el-table__header th .cell").all_inner_texts()
    for i, h in enumerate(headers):
        if column_name in h:
            return i
    # 备选:直接匹配 th
    headers2 = page.locator(".el-table__header-wrapper th, .el-table__header th").all_inner_texts()
    for i, h in enumerate(headers2):
        if column_name in h:
            return i
    return None


def get_total_count(page):
    """从分页栏读取'共 N 条'的总条数,用于精确翻页"""
    try:
        # Element UI 分页通常包含 '共 X 条'
        total_text = page.locator(".el-pagination__total").inner_text(timeout=5000)
        m = re.search(r"(\d+)", total_text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    # 备选:在分页区域搜索 '共 ... 条'
    try:
        pag_text = page.locator(".el-pagination").inner_text(timeout=5000)
        m = re.search(r"共\s*([\d,]+)\s*条", pag_text)
        if m:
            return int(m.group(1).replace(",", ""))
    except Exception:
        pass
    return None


def read_table_column_texts(page, column_name, max_pages=500):
    """跨分页读取指定列的所有文本(按分页总条数精确翻页)"""
    texts = []
    wait_table_loaded(page)

    # 检查无数据提示
    body_text = page.locator("body").inner_text(timeout=5000)
    if "暂无数据" in body_text or "没有数据" in body_text or "empty" in body_text.lower():
        print(f"  [INFO] 当前筛选条件下无数据")
        return texts

    col_idx = get_column_index(page, column_name)
    if col_idx is None:
        print(f"[WARN] 找不到列: {column_name}")
        return texts

    # 计算总页数(优先用分页总条数,兜底用 max_pages)
    total = get_total_count(page)
    if total is not None:
        page_size = 10
        total_pages = max(1, (total + page_size - 1) // page_size)
        print(f"  [INFO] 分页总条数: {total}, 预计 {total_pages} 页")
    else:
        total_pages = max_pages
        print(f"  [INFO] 未能读取总条数,按最多 {total_pages} 页读取")

    for page_num in range(1, total_pages + 1):
        wait_table_loaded(page)

        rows = page.locator(".el-table__body-wrapper .el-table__row, .el-table__body .el-table__row").all()
        if not rows:
            print(f"  [INFO] 第 {page_num} 页无行数据,停止翻页")
            break

        for row in rows:
            cells = row.locator("td").all()
            if col_idx < len(cells):
                text = cells[col_idx].inner_text().strip()
                texts.append(text)

        print(f"  [INFO] 第 {page_num} 页读取 {len(rows)} 行,累计 {len(texts)} 条")

        # 已是最后一页则停止
        if page_num >= total_pages:
            break

        # 点击下一页
        try:
            next_btn = page.locator(".el-pagination .btn-next, .el-pagination button:has-text('下一页')").first
            if not next_btn.is_visible(timeout=2000):
                break
            cls = next_btn.get_attribute("class") or ""
            if "disabled" in cls or "is-disabled" in cls:
                break
            next_btn.click(timeout=5000)
            page.wait_for_timeout(1800)
        except Exception as e:
            print(f"  [INFO] 翻页终止: {e}")
            break

    return texts


def sum_amount_column(page, column_name=COL_AMOUNT, max_pages=500):
    """读取金额列并求和"""
    texts = read_table_column_texts(page, column_name, max_pages)
    total = 0.0
    for t in texts:
        # 提取数字,支持 ¥, 千分位
        m = re.search(r"[\d,]+\.?\d*", t)
        if m:
            try:
                total += float(m.group().replace(",", ""))
            except ValueError:
                pass
    return total, len(texts)


def collect_failure_reasons(page, column_name=COL_FAIL_REASON, max_pages=500):
    """读取失败原因列并收集(兼容旧逻辑,现由 collect_failure_records 取代)"""
    texts = read_table_column_texts(page, column_name, max_pages)
    reasons = []
    for t in texts:
        if not t or t in ("-", "--", "", "无", "/"):
            continue
        # 过滤纯数字
        if re.sub(r"[.,]", "", t).isdigit():
            continue
        reasons.append(t)
    return reasons


def collect_failure_records(page, max_pages=500):
    """读取失败记录的所有可见字段,返回字典列表。
    列按截图格式: 司机姓名、手机号、银行卡号、提现金额、交易状态、失败原因。
    如果某列在页面不存在,对应字段为空字符串,避免抓取崩溃。"""
    wait_table_loaded(page)

    body_text = page.locator("body").inner_text(timeout=5000)
    if "暂无数据" in body_text or "没有数据" in body_text or "empty" in body_text.lower():
        print(f"  [INFO] 当前筛选条件下无数据")
        return []

    # 一次性读取所有列索引,缺失则返回 None
    cols = {
        "driver_name": get_column_index(page, COL_DRIVER_NAME),
        "phone": get_column_index(page, COL_PHONE),
        "card": get_column_index(page, COL_CARD),
        "amount": get_column_index(page, COL_AMOUNT),
        "status": get_column_index(page, COL_STATUS),
        "reason": get_column_index(page, COL_FAIL_REASON),
    }
    print(f"  [INFO] 失败记录列索引: {cols}")

    # 计算总页数
    total = get_total_count(page)
    if total is not None:
        page_size = 10
        total_pages = max(1, (total + page_size - 1) // page_size)
        print(f"  [INFO] 分页总条数: {total}, 预计 {total_pages} 页")
    else:
        total_pages = max_pages
        print(f"  [INFO] 未能读取总条数,按最多 {total_pages} 页读取")

    records = []
    for page_num in range(1, total_pages + 1):
        wait_table_loaded(page)

        rows = page.locator(".el-table__body-wrapper .el-table__row, .el-table__body .el-table__row").all()
        if not rows:
            print(f"  [INFO] 第 {page_num} 页无行数据,停止翻页")
            break

        for row in rows:
            cells = row.locator("td").all()
            if not cells:
                continue

            def cell_text(idx):
                if idx is None or idx < 0 or idx >= len(cells):
                    return ""
                return cells[idx].inner_text().strip()

            reason = cell_text(cols["reason"])
            if not reason or reason in ("-", "--", "", "无", "/"):
                continue
            if re.sub(r"[.,]", "", reason).isdigit():
                continue

            amount_str = cell_text(cols["amount"])
            amount = parse_amount_str(amount_str)

            records.append({
                "driver_name": cell_text(cols["driver_name"]),
                "phone": cell_text(cols["phone"]),
                "card": cell_text(cols["card"]),
                "amount": amount,
                "status": cell_text(cols["status"]) or "提现失败",
                "reason": reason,
            })

        print(f"  [INFO] 第 {page_num} 页读取 {len(rows)} 行,累计 {len(records)} 条失败记录")

        if page_num >= total_pages:
            break

        try:
            next_btn = page.locator(".el-pagination .btn-next, .el-pagination button:has-text('下一页')").first
            if not next_btn.is_visible(timeout=2000):
                break
            cls = next_btn.get_attribute("class") or ""
            if "disabled" in cls or "is-disabled" in cls:
                break
            next_btn.click(timeout=5000)
            page.wait_for_timeout(1800)
        except Exception as e:
            print(f"  [INFO] 翻页终止: {e}")
            break

    return records


# ============ 报表生成 ============
def render_markdown(run_date, start_date=None, end_date=None):
    """根据数据文件生成合并日报(文件名用运行日,标注统计范围)

    start_date/end_date 仅作兼容参数;报告头统一用工作日业务区间,
    需求二章节单独使用"当天"口径,确保任一阶段渲染口径一致。
    """
    # 业务区间(一/二章节)与当天(三章节)各自独立计算
    biz_start, biz_end = get_business_range()
    today = get_today_range()[0]
    data = load_data(run_date)

    lines = []
    site_name = SITES[SITE_NAME].get("name", "承运提现")
    lines.append(f"# {site_name}日报 - {run_date}")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 数据来源: {TARGET_PAGE}")
    lines.append(f"> 统计口径(待提现/失败): 创建时间 = {biz_start} ~ {biz_end}")
    lines.append("")

    # 一、待提现金额
    lines.append("## 一、待提现金额(需求一 · 09:00)")
    lines.append("")
    pending_amount = data.get("pending_amount")
    pending_count = data.get("pending_count")
    if pending_amount is not None:
        lines.append(f"- 待提现金额合计: **¥{pending_amount:,.2f}**")
        lines.append(f"- 待提现笔数: **{pending_count}** 笔")
    else:
        lines.append(f"- 待补充(每天 {CONFIG.get('pending_fetch_time', '09:00')} 任务执行后更新)")
    lines.append("")

    # 二、失败原因 Top3
    lines.append("## 二、失败原因 Top 3(15:00)")
    lines.append("")
    fail_records = data.get("fail_records") or []
    # 兼容旧数据: 旧版只有 fail_reasons 字符串数组
    if not fail_records:
        fail_reasons = data.get("fail_reasons", [])
        if fail_reasons:
            counter = Counter(fail_reasons)
            top3 = counter.most_common(3)
            lines.append("| 排名 | 失败原因 | 出现次数 | 占比 |")
            lines.append("|------|----------|----------|------|")
            total = len(fail_reasons)
            for i, (reason, count) in enumerate(top3, 1):
                pct = count / total * 100 if total > 0 else 0
                reason_short = reason[:50] + "..." if len(reason) > 50 else reason
                lines.append(f"| {i} | {reason_short} | {count} | {pct:.1f}% |")
            lines.append("")
            lines.append(f"> 共收集到 {total} 条失败记录")
        else:
            lines.append(f"- 待补充(每天 {CONFIG.get('fail_fetch_time', '15:00')} 任务执行后更新)")
    else:
        # 仅在有真实失败原因时使用完整记录格式；多条记录用序号逐条排列
        total = len(fail_records)
        reasons = [r.get("reason", "") for r in fail_records if r.get("reason")]
        if not reasons:
            lines.append("- 无提现失败")
        else:
            for idx, r in enumerate(fail_records, 1):
                lines.append(f"{idx}. 司机姓名：{r.get('driver_name') or '-'}")
                lines.append(f"   手机号：{r.get('phone') or '-'}")
                lines.append(f"   银行卡号：{r.get('card') or '-'}")
                lines.append(f"   提现金额：¥{r.get('amount', 0):,.2f}")
                lines.append(f"   交易状态：{r.get('status') or '交易失败'}")
                lines.append(f"   失败原因：{r.get('reason') or ''}")
                lines.append("")
        lines.append(f"> 共收集到 {total} 条失败记录")
    lines.append("")

    # 三、需求二 · 当日待提现与明日提现预测
    lines.append("## 三、需求二 · 当日待提现与明日提现预测(15:00)")
    lines.append("")
    lines.append(f"> 口径: 创建时间 = {today} (当天), 提现状态 = 待提现")
    lines.append("")
    demand2_today = data.get("demand2_today_pending")
    coefficient_val = data.get("coefficient")
    predicted = data.get("predicted_full")
    predict_mode = data.get("predict_mode")
    breakdown = data.get("predict_breakdown")
    if demand2_today is not None:
        lines.append(f"- 当天(0~{SPLIT_HOUR}点)待提现金额: **¥{demand2_today:,.2f}**")
        if coefficient_val is not None:
            lines.append(f"- 预测系数(工作日 0~{SPLIT_HOUR}点/0~24点 比值均值): **{coefficient_val}**")
            if predicted is not None:
                if predict_mode == "monday" and breakdown:
                    lines.append(f"- 预测(上周五~周日合计)待提现: **¥{predicted:,.2f}**")
                    lines.append(f"  - 上周五({breakdown.get('fri_date','')} 0~{SPLIT_HOUR}点) ¥{breakdown.get('fri_partial',0):,.2f} ÷ 系数 → 上周五全天 ¥{breakdown.get('fri_full_pred',0):,.2f}")
                    lines.append(f"  - 周六(0~24点) ¥{breakdown.get('sat_full',0):,.2f}")
                    lines.append(f"  - 周日(0~24点) ¥{breakdown.get('sun_full',0):,.2f}")
                else:
                    lines.append(f"- 预测当天全天(0~24点)待提现: **¥{predicted:,.2f}** (当天 0~{SPLIT_HOUR}点待提现 ÷ 系数)")
        else:
            lines.append(f"- 预测系数: **未计算** → 请先点仪表盘「自动抓取并计算系数」或运行 `python withdraw_report.py --auto-coeff`")
    else:
        lines.append(f"- 待补充(每天 {CONFIG.get('fail_fetch_time', '15:00')} 任务执行后更新)")
    lines.append("")

    # 系数对比: 当前 active 系数 vs 上次系数
    lines.append("### 系数对比(当前 active vs 上次)")
    lines.append("")
    coeff_now = load_coefficient()
    changelog = read_coefficient_changelog(1)
    coeff_old = None
    if changelog:
        last = changelog[0]
        coeff_old = {
            "coeff": float(last.get("old_coeff") or 0),
            "pooled": float(last.get("old_pooled") or 0),
        }

    def fmt_c(v):
        return f"{v:.4f}" if v else "(无)"

    if coeff_now:
        lines.append(f"- 当前系数(active={coeff_now.get('auto_key', '-')}): 系数 **{fmt_c(coeff_now.get('coeff'))}** "
                     f"(汇总比值 {fmt_c(coeff_now.get('pooled'))}) · 区间 {coeff_now.get('date_min')} ~ {coeff_now.get('date_max')}, "
                     f"{coeff_now.get('day_count', 0)} 天, 样本 {coeff_now.get('sample_n_rows', 0)} 行")
        lines.append(f"  - 区间 0~{coeff_now.get('split_hour', SPLIT_HOUR)}点 合计 **¥{coeff_now.get('total_partial', 0):,.2f}** / "
                     f"0~24点 合计 **¥{coeff_now.get('total_full', 0):,.2f}**")
    else:
        lines.append(f"- 当前系数: **未计算**")
    if coeff_old:
        lines.append(f"- 上次系数: 系数 {fmt_c(coeff_old['coeff'])} (汇总比值 {fmt_c(coeff_old['pooled'])})")
    else:
        lines.append(f"- 上次系数: (首次计算,无历史)")
    lines.append("")

    # 四、预测 vs 真实 比对
    lines.append("## 四、预测 vs 真实 比对")
    lines.append("")
    comparisons = read_forecast_comparisons(10)
    if comparisons:
        lines.append("| 预测基于日 | 预测当天全天(0~24)待提现 | 次日09实测待提现(近似) | 差异 | 差异率 |")
        lines.append("|------------|----------------------------|--------------------------|------|--------|")
        for r in comparisons:
            pred = parse_amount_str(r.get("predicted_full", ""))
            act = parse_amount_str(r.get("actual_next_day_pending_09", ""))
            diff_raw = r.get("diff", "")
            pct_raw = r.get("diff_pct", "")
            diff_disp = f"¥{parse_amount_str(diff_raw):,.2f}" if diff_raw not in (None, "") else "-"
            pct_disp = f"{pct_raw}%" if pct_raw not in (None, "") else "-"
            lines.append(
                f"| {r.get('predict_date', '')} "
                f"| ¥{pred:,.2f} | ¥{act:,.2f} | {diff_disp} | {pct_disp} |"
            )
        lines.append("")
        lines.append("> 差异 = 真实 − 预测；差异率 = 差异 ÷ 预测 × 100%。预测值=当天 0~15点待提现 ÷ 系数；"
                     "真实值取次日 09:00 待提现金额(需求一)作为当天全天的近似实测。")
    else:
        lines.append("- 暂无比对数据(需先完成至少一次 15:00 预测 + 次日 09:00 真实数据)")
    lines.append("")

    # 注: 需求二(当天0~15点待提现+预测当天全天)已在「## 三」渲染, 系数变更在「系数对比」子节留存;
    #      仪表盘「🧮 系数管理」卡片另有完整变更记录与导入入口。

    lines.append("---")
    lines.append("")
    lines.append("*本报表由 WorkBuddy 自动化脚本生成*")
    lines.append("")

    report = "\n".join(lines)
    report_file = get_report_file(run_date)
    report_file.write_text(report, encoding="utf-8")
    return report_file


# ============ 主流程 ============
def run_pending_phase(debug=False, start_date=None, end_date=None):
    """9:00 执行:统计指定区间待提现金额(默认工作日补算)"""
    run_date = get_run_date()
    start, end = get_business_range(start_date, end_date)
    print(f"[{now_str()}] 开始统计 {start} ~ {end} 待提现金额(运行日 {run_date})...")

    try:
        page, cleanup = acquire_page(debug)
    except CdpError as e:
        print(str(e))
        return None
    if page is None:
        return None
    try:
        set_filters(page, start, end, "待提现")
        amount, count = sum_amount_column(page)

        save_data(run_date, pending_amount=amount, pending_count=count)
        # 需求一: 追加到累积表
        append_pending_ledger(run_date, start, end, count, amount)
        # 需求一: 回填预测比对(用今日真实待提现对比上一工作日的预测)
        fill_forecast_comparison(run_date, amount)
        report_file = render_markdown(run_date, start, end)

        print(f"\n[OK] 待提现金额: ¥{amount:,.2f}, 笔数: {count}")
        print(f"[OK] 日报已保存: {report_file}")

        if not debug:
            print("\n" + "=" * 50)
            print(report_file.read_text(encoding="utf-8"))
            print("=" * 50)

        return report_file
    finally:
        cleanup()


def run_fail_phase(debug=False, start_date=None, end_date=None):
    """15:00 执行:统计指定区间失败原因 Top3(默认工作日补算)"""
    run_date = get_run_date()
    start, end = get_business_range(start_date, end_date)
    print(f"[{now_str()}] 开始统计 {start} ~ {end} 失败原因(运行日 {run_date})...")

    try:
        page, cleanup = acquire_page(debug)
    except CdpError as e:
        print(str(e))
        return None
    if page is None:
        return None
    try:
        set_filters(page, start, end, "提现失败")
        records = collect_failure_records(page)
        reasons = [r["reason"] for r in records if r.get("reason")]

        save_data(run_date, fail_reasons=reasons, fail_records=records)
        report_file = render_markdown(run_date, start, end)

        print(f"\n[OK] 共收集 {len(records)} 条失败记录")
        if reasons:
            counter = Counter(reasons)
            print("[OK] 失败原因 Top3:")
            for reason, count in counter.most_common(3):
                print(f"    - {reason}: {count} 次")
        print(f"[OK] 日报已保存: {report_file}")

        if not debug:
            print("\n" + "=" * 50)
            print(report_file.read_text(encoding="utf-8"))
            print("=" * 50)

        return report_file
    finally:
        cleanup()


def run_demand2_phase(debug=False):
    """15:00 执行(需求二): 观测待提现金额, 用工作日系数预测, 按星期切换口径。

    - 周二~周五: 预测当天全天(0~24点)待提现 ≈ 当天 0~SPLIT_HOUR 点待提现 ÷ 工作日系数。
    - 周一:     预测(上周五~周日合计)待提现 = 上周五全天(0~24, 由 0~15÷系数推算)
                                                 + 周六0~24 + 周日0~24。
      周末明细取自系数文件(近1月)的 daily_partial/daily_full(周一06:00 --auto-coeff 已含最近周末)。
    系数统一用工作日专属系数 coeff_weekday(自动化仅工作日跑, 工作日系数更准)。
    """
    run_date = get_run_date()
    today = date.today()
    start = end = today.strftime("%Y-%m-%d")
    print(f"[{now_str()}] 开始统计 {start} 当天待提现(需求二, 运行日 {run_date})...")

    try:
        page, cleanup = acquire_page(debug)
    except CdpError as e:
        print(str(e))
        return None
    if page is None:
        return None
    try:
        # 导出当天(创建时间=今天)待提现明细, 本地按 创建时间 小时切 0~SPLIT_HOUR / 0~24
        csv_path = export_daily_csv(page, start, end, status="待提现", key="today")
        try:
            today_stats = compute_coeff_from_export(str(csv_path), label="今日待提现",
                                                    exclude_threshold=COEFF_EXCLUDE_THRESHOLD)
        finally:
            try:
                csv_path.unlink()
            except Exception:
                pass
        obs_partial = today_stats["total_partial"]   # 当天 0~SPLIT_HOUR 点待提现
        obs_full = today_stats["total_full"]         # 当天 0~24 点待提现(已创建部分)
        count = today_stats["day_count"]

        coeff_info = load_coefficient()
        # 界面与预测统一使用工作日专属系数(自动化仅工作日跑,工作日系数更准);
        # coeff(全量含周末)保留作参考。
        coefficient = (coeff_info.get("coeff_weekday") if coeff_info else None) or (coeff_info.get("coeff") if coeff_info else None)
        predicted = None
        predict_mode = None
        predict_input = None
        predict_breakdown = None
        if coefficient:
            wd = today.weekday()  # 0=周一 ... 4=周五
            if wd == 0:
                # 周一: 预测(上周五~周日合计) = 上周五全天(0~24, 由 0~15÷系数推算) + 周六0~24 + 周日0~24
                wk = last_weekend_components(coeff_info)
                if wk:
                    fri_full_pred = wk["fri_partial"] / coefficient
                    predicted = round(fri_full_pred + wk["sat_full"] + wk["sun_full"], 2)
                    predict_mode = "monday"
                    predict_input = wk["fri_partial"]
                    predict_breakdown = {
                        "fri_date": wk["fri_date"], "fri_partial": round(wk["fri_partial"], 2),
                        "fri_full_pred": round(fri_full_pred, 2),
                        "sat_date": wk["sat_date"], "sat_full": round(wk["sat_full"], 2),
                        "sun_date": wk["sun_date"], "sun_full": round(wk["sun_full"], 2),
                    }
                    print(f"[OK] 周一预测(上周五~周日合计): 上周五0~15 ¥{wk['fri_partial']:,.2f} ÷ {coefficient:.4f}"
                          f" = 上周五全天 ¥{fri_full_pred:,.2f}; 周六 ¥{wk['sat_full']:,.2f}; 周日 ¥{wk['sun_full']:,.2f}"
                          f" → 预测合计 ¥{predicted:,.2f}")
                else:
                    # 系数文件无周末明细, 兜底用当天公式
                    predicted = round(obs_partial / coefficient, 2)
                    predict_mode = "weekday"
                    predict_input = obs_partial
                    print(f"[WARN] 系数文件无周末明细, 兜底用当天公式: 当天0~{SPLIT_HOUR} ¥{obs_partial:,.2f} ÷ {coefficient:.4f} = ¥{predicted:,.2f}")
            else:
                # 周二~周五: 预测当天全天(0~24) = 当天0~15点待提现 ÷ 工作日系数
                predicted = round(obs_partial / coefficient, 2)
                predict_mode = "weekday"
                predict_input = obs_partial
                print(f"[OK] 当天 0~{SPLIT_HOUR} 点待提现 = ¥{obs_partial:,.2f}; "
                      f"系数 = {coefficient:.4f}; 预测当天全天(0~24点)待提现 ≈ ¥{predicted:,.2f}")
        else:
            print("[WARN] 系数尚未计算(请先点「自动抓取并计算系数」或运行 --auto-coeff),无法预测。")

        save_data(run_date, demand2_today_pending=obs_partial, coefficient=coefficient,
                  predicted_full=predicted, predict_mode=predict_mode,
                  predict_input=predict_input, predict_breakdown=predict_breakdown)
        append_or_update_forecast(run_date, predict_input, coefficient, predicted, predict_mode)
        report_file = render_markdown(run_date, start, end)

        print(f"\n[OK] 当天(0~{SPLIT_HOUR}点)待提现金额: ¥{obs_partial:,.2f}, 全天已创建: ¥{obs_full:,.2f}, 笔数: {count}")
        if coefficient:
            print(f"[OK] 系数 = {coefficient:.4f}, 预测当天全天待提现 ≈ ¥{predicted:,.2f}")
        else:
            print("[WARN] 系数未计算,无法预测。")
        print(f"[OK] 日报已保存: {report_file}")

        if not debug:
            print("\n" + "=" * 50)
            print(report_file.read_text(encoding="utf-8"))
            print("=" * 50)

        return report_file
    finally:
        cleanup()


def main():
    parser = argparse.ArgumentParser(description="提现管理 - 每日统计(多站点)")
    parser.add_argument("--site", default="carrier", choices=list(SITES.keys()),
                        help="站点: carrier(承运提现) / admin(提现拦截)")
    parser.add_argument("--setup", action="store_true", help="首次登录配置(配合 --site)")
    parser.add_argument("--cdp", action="store_true",
                        help="CDP 手动模式: 接管本机已打开并登录的 admin 网页取数(需先运行 open_admin_debug.bat)")
    parser.add_argument("--pending", action="store_true", help="9:00 需求一:待提现金额统计(写入累积表+回填比对)")
    parser.add_argument("--fail", action="store_true", help="15:00 失败原因统计")
    parser.add_argument("--demand2", action="store_true", help="15:00 需求二:当天0~15点待提现+预测当天全天(0~24)待提现")
    parser.add_argument("--auto-coeff", action="store_true", help="自动抓取近1/2/3月数据计算三套系数(需求二)")
    parser.add_argument("--set-active", dest="set_active", metavar="KEY", help="切换 active 系数: 1m/2m/3m")
    parser.add_argument("--debug", action="store_true", help="调试模式(headed)")
    parser.add_argument("--start-date", metavar="YYYY-MM-DD", help="覆盖默认工作日区间起始日期")
    parser.add_argument("--end-date", metavar="YYYY-MM-DD", help="覆盖默认工作日区间结束日期")
    args = parser.parse_args()

    configure_site(args.site)
    global USE_CDP
    USE_CDP = args.cdp

    did = False
    if args.setup:
        setup_login()
    elif args.auto_coeff:
        auto_compute_coefficients()
    elif args.set_active:
        apply_active_coefficient(args.set_active)
    else:
        if args.pending:
            run_pending_phase(debug=args.debug, start_date=args.start_date, end_date=args.end_date)
            did = True
        if args.fail:
            run_fail_phase(debug=args.debug, start_date=args.start_date, end_date=args.end_date)
            did = True
        if args.demand2:
            run_demand2_phase(debug=args.debug)
            did = True
        if not did:
            print("[ERROR] 请指定模式: --pending / --fail / --demand2 / --import, 或 --setup")
            print("        示例: python withdraw_report.py --pending")
            print("        15:00 同时跑: python withdraw_report.py --fail --demand2")
            sys.exit(1)

    # 抓取完成后，自动同步最新数据到云端看板（失败不影响本次统计）
    if did:
        try:
            sync_cloud()
        except Exception as e:
            print(f"[sync] 云端同步跳过: {e}")


def sync_cloud():
    """抓取成功后，自动把最新数据推送到云端 Supabase 看板。

    同步脚本 v2 已改为直接读本地文件，不再依赖 8766 控制台在跑。
    这里改为前台等待（通常 1~3 秒）并把结果落盘到 cloud_sync.log，
    避免过去 DETACHED + DEVNULL 时同步失败完全无声、导致云端看板
    长期停留在旧快照却没人发现。
    """
    import subprocess, os, sys
    sync_script = r"C:\Users\92893\WorkBuddy\2026-07-30-18-09-13\withdraw-dashboard-cloud\sync\sync_to_cloud.py"
    if not os.path.exists(sync_script):
        print("[sync] 未找到云端同步脚本，跳过:", sync_script)
        return
    print("[sync] 正在同步最新数据到云端看板…")
    log_file = SCRIPT_DIR / "cloud_sync.log"
    try:
        proc = subprocess.run(
            [sys.executable, sync_script],
            cwd=os.path.dirname(sync_script),
            capture_output=True, text=True, timeout=90,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n===== {stamp} (exit={proc.returncode}) =====\n{out}")
        except Exception:
            pass
        if proc.returncode == 0:
            print("[sync] 云端看板已更新")
        else:
            print(f"[sync] 云端同步失败(非致命, 不影响本次统计), 详见: {log_file}")
            tail = out.strip().splitlines()[-3:] if out.strip() else []
            for line in tail:
                print(f"[sync]   {line}")
    except subprocess.TimeoutExpired:
        print("[sync] 云端同步超时(非致命), 已跳过")
    except Exception as e:
        print(f"[sync] 启动同步进程失败（非致命）: {e}")


if __name__ == "__main__":
    main()

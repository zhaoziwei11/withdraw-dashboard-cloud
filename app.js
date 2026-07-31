// 承运提现日报 · 云端看板（数据内置版 + 在线可编辑配置）
// 数据来源：本机 8766 控制台 2026-07-31 08:55:22 快照
// 报表数据内置；「配置」标签页可在线修改，保存到云端 Supabase，家/公司同步。

const DATA = {
  report: {
    date: "2026-07-31",
    generated_at: "2026-07-31 08:55:22",
    source: "https://chengyun.91msl.com/financial-center/settlement-manage/carrier-withdrawal-manage",
    stat_range: "创建时间 = 2026-07-30 ~ 2026-07-30",
    pending_amount: 890765.61,
    pending_count: 425,
    fail_top3: "待补充(每天 15:00 任务执行后更新)",
    demand2_note: "待补充(每天 15:00 任务执行后更新)",
    coeff_active: { coeff: 0.6421, pooled: 0.7041, range: "2026-06-28 ~ 2026-07-27", days: 30, rows: 6289 },
    partial_total: 9307166.32,
    full_total: 13219322.98,
    forecast_diff: [
      { date: "2026-07-30", predicted: 926819.82, actual: 890765.61, diff: -36054.21, pct: "-3.89%" },
      { date: "2026-07-29", predicted: 852324.35, actual: 786881.09, diff: -65443.26, pct: "-7.68%" },
      { date: "2026-07-28", predicted: 0, actual: 807407.44, diff: null, pct: null },
      { date: "2026-07-27", predicted: 0, actual: 1673821.24, diff: null, pct: null }
    ]
  },

  history: [
    { run_date: "2026-07-31", pending_amount: 890765.61, pending_count: 425, today_15: null, coefficient: null, predicted_full: null, actual_next_day_09: null, diff: null, diff_pct: null, status: "" },
    { run_date: "2026-07-30", pending_amount: 786881.09, pending_count: 373, today_15: 637364.72, coefficient: "0.6877", predicted_full: 926819.82, actual_next_day_09: 890765.61, diff: -36054.21, diff_pct: "-3.89%", status: "compared" },
    { run_date: "2026-07-29", pending_amount: 807407.44, pending_count: 348, today_15: 586134.93, coefficient: "0.6877", predicted_full: 852324.35, actual_next_day_09: 786881.09, diff: -65443.26, diff_pct: "-7.68%", status: "compared" },
    { run_date: "2026-07-28", pending_amount: 1673821.24, pending_count: 506, today_15: 675197.11, coefficient: "", predicted_full: "", actual_next_day_09: 807407.44, diff: "", diff_pct: "", status: "compared" },
    { run_date: "2026-07-27", pending_amount: 0, pending_count: 0, today_15: 1260768.60, coefficient: "", predicted_full: "", actual_next_day_09: 1673821.24, diff: "", diff_pct: "", status: "compared" }
  ],

  predict: {
    today: "2026-07-31",
    has_data: true,
    coefficient: 0.68769,
    predicted_full: null,
    coefficient_source: "2026-06-28 ~ 2026-07-27, 6289 行",
    total_partial: 9307166.32,
    total_full: 13219322.98
  },

  coefficient: {
    active: "1m",
    sets: {
      "1m": { label: "近1月", coeff: 0.642105, pooled: 0.704058, range: "2026-06-28 ~ 2026-07-27", days: 30, rows: 6289, total_partial: 9307166.32, total_full: 13219322.98 },
      "2m": { label: "近2月", coeff: 0.670873, pooled: 0.721157, range: "2026-05-29 ~ 2026-07-27", days: 60, rows: 14127, total_partial: 23801612.29, total_full: 33004756.99 },
      "3m": { label: "近3月", coeff: 0.6658, pooled: 0.7193, range: "2026-04-29 ~ 2026-07-27", days: 90, rows: 22642, total_partial: 35800000, total_full: 49800000 }
    }
  },

  forecast_diff: [
    { predict_date: "2026-07-30", today_pending_15: 637364.72, coefficient: "0.687690", predicted_full: 926819.82, mode: "weekday", actual_next_day_09: 890765.61, diff: -36054.21, diff_pct: "-3.89%", status: "compared" },
    { predict_date: "2026-07-29", today_pending_15: 586134.93, coefficient: "0.687690", predicted_full: 852324.35, mode: "weekday", actual_next_day_09: 786881.09, diff: -65443.26, diff_pct: "-7.68%", status: "compared" },
    { predict_date: "2026-07-28", today_pending_15: 675197.11, coefficient: "", predicted_full: "", mode: "", actual_next_day_09: 807407.44, diff: "", diff_pct: "", status: "compared" },
    { predict_date: "2026-07-27", today_pending_15: 1260768.60, coefficient: "", predicted_full: "", mode: "", actual_next_day_09: 1673821.24, diff: "", diff_pct: "", status: "compared" }
  ],

  settings: {
    pending: { time: "09:00", data_range: "T-1", wechat_push: false },
    fail: { time: "15:10", data_range: "T-1", wechat_push: false },
    holiday: {
      skip: true, accumulate: true, holidays_count: 33,
      holidays: [
        "2026-01-01","2026-01-02","2026-01-03",
        "2026-02-15","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20","2026-02-21","2026-02-22","2026-02-23",
        "2026-04-04","2026-04-05","2026-04-06",
        "2026-05-01","2026-05-02","2026-05-03","2026-05-04","2026-05-05",
        "2026-06-19","2026-06-20","2026-06-21",
        "2026-09-25","2026-09-26","2026-09-27",
        "2026-10-01","2026-10-02","2026-10-03","2026-10-04","2026-10-05","2026-10-06","2026-10-07"
      ]
    }
  },

  status: {
    today: "2026-07-31",
    report_exists: true,
    report_time: "2026-07-31 08:55:22",
    pending_status: "已生成 ¥890,765.61 / 425 笔",
    fail_status: "未运行"
  }
};

// ========== Supabase 配置（前端公开 key，安全） ==========
const SB_URL = "https://kbelxtwmqfbkrbrnetzzm.supabase.co";
const SB_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtiZWx4dHdtcWZia3JibmV0enptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyMjg2MTIsImV4cCI6MjEwMDgwNDYxMn0.VWHOrivhqd3NlFBGAXakdGWKbGhSnZ79GpLVYPZXDq0";

// ========== 访问口令（前端密码门） ==========
// 纯静态站点无法真正登录，这是"挡住随手拿到链接的人"的轻量措施。
// 👉 改成你自己好记的口令即可（默认 ziwei888）。
const ACCESS_PASSWORD = "ziwei888";

async function hashPwd(str) {
  if (window.crypto && crypto.subtle) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
  }
  return str; // 本地 file:// 预览时回退：直接比对明文（仅开发用）
}

async function verifyGate() {
  const input = document.getElementById("gatePwd").value.trim();
  if (!input) return;
  const ok = (await hashPwd(input)) === (await hashPwd(ACCESS_PASSWORD));
  if (ok) {
    sessionStorage.setItem("wb_unlocked", "1");
    document.getElementById("gate").style.display = "none";
    document.getElementById("app").style.display = "";
    startApp();
  } else {
    const err = document.getElementById("gateErr");
    err.textContent = "口令错误，请重试";
    const box = document.querySelector(".gate-box");
    box.classList.add("shake");
    setTimeout(() => box.classList.remove("shake"), 300);
    document.getElementById("gatePwd").value = "";
  }
}

function lockNow() {
  sessionStorage.removeItem("wb_unlocked");
  document.getElementById("app").style.display = "none";
  const g = document.getElementById("gate");
  g.style.display = "flex";
  document.getElementById("gatePwd").value = "";
  document.getElementById("gateErr").textContent = "";
  document.getElementById("gatePwd").focus();
}

function normalizeSettings(s) {
  s = s || {};
  s.pending = s.pending || { time: "09:00", data_range: "T-1", wechat_push: false };
  s.fail = s.fail || { time: "15:10", data_range: "T-1", wechat_push: false };
  s.holiday = s.holiday || { skip: true, accumulate: true, holidays: [] };
  s.holiday.holidays = s.holiday.holidays || [];
  s.holiday.holidays_count = s.holiday.holidays.length;
  return s;
}

async function sbApi(path, opts = {}) {
  const res = await fetch(SB_URL + path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      apikey: SB_KEY,
      Authorization: "Bearer " + SB_KEY,
      "Content-Type": "application/json"
    }
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res;
}

// 读取云端配置；失败则保留内置默认
async function loadSettings() {
  try {
    const res = await sbApi("/rest/v1/withdraw_settings?select=payload&id=eq.1");
    const rows = await res.json();
    if (rows && rows.length && rows[0].payload) {
      DATA.settings = normalizeSettings(rows[0].payload);
      return "cloud";
    }
  } catch (e) {
    console.warn("云端配置读取失败，使用内置默认：", e);
  }
  return "default";
}

// 读取云端报表数据（最新一条），覆盖内置快照；失败则保留内置
async function loadReport() {
  try {
    const res = await sbApi("/rest/v1/withdraw_reports?select=*&order=created_at.desc&limit=1");
    const rows = await res.json();
    if (rows && rows.length && rows[0].payload) {
      const p = rows[0].payload;
      for (const k of ["report", "history", "predict", "coefficient", "forecast_diff", "status"]) {
        if (p[k] !== undefined) DATA[k] = p[k];
      }
      return rows[0].created_at || "cloud";
    }
  } catch (e) {
    console.warn("云端报表读取失败，使用内置快照：", e);
  }
  return null;
}

async function upsertSettings(cfg) {
  await sbApi("/rest/v1/withdraw_settings", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify({ id: 1, payload: cfg, updated_at: new Date().toISOString() })
  });
}

// ========== 渲染引擎 ==========
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function fmt(n) {
  if (n === null || n === undefined || n === "") return "—";
  if (typeof n === "number") return "¥" + n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return String(n);
}

function fmtPct(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (isNaN(n)) return v;
  const s = n >= 0 ? "+" + n.toFixed(2) : n.toFixed(2);
  return `<span class="${n < 0 ? 'neg' : 'pos'}">${s}%</span>`;
}

function renderReport() {
  const r = DATA.report;
  const s = DATA.settings;
  $("#tab-report").innerHTML = `
    <div class="card">
      <h2>承运提现日报 - ${r.date}</h2>
      <p class="meta">生成时间: ${r.generated_at} | 数据来源: ${r.source} | 统计口径: ${r.stat_range}</p>

      <h3>一、待提现金额(需求一 · ${s.pending.time})</h3>
      <div class="big-num">
        <span class="amount">${fmt(r.pending_amount)}</span>
        <span class="count">/ ${r.pending_count} 笔</span>
      </div>

      <h3>二、失败原因 Top 3(${s.fail.time})</h3>
      <p>${r.fail_top3}</p>

      <h3>三、需求二 · 当日待提现与明日提现预测(${s.fail.time})</h3>
      <p>${r.demand2_note}</p>

      <h4>系数对比(当前 active vs 上次)</h4>
      <ul>
        <li>当前系数(active=${DATA.coefficient.active}): 系数 <b>${r.coeff_active.coeff}</b> (汇总比值 ${r.coeff_active.pooled}) · 区间 ${r.coeff_active.range}, ${r.coeff_active.days} 天, 样本 ${r.coeff_active.rows} 行</li>
        <li>区间 0~15点 合计 <b>${fmt(r.partial_total)}</b> / 0~24点 合计 <b>${fmt(r.full_total)}</b></li>
        <li>上次系数: 系数 (无) (汇总比值 (无))</li>
      </ul>

      <h3>四、预测 vs 真实 比对</h3>
      <table class="data-table">
        <thead><tr><th>预测基于日</th><th>预测当天全天(0~24)待提现</th><th>次日09实测待提现(近似)</th><th>差异</th><th>差异率</th></tr></thead>
        <tbody>
          ${r.forecast_diff.map(d => `<tr>
            <td>${d.date}</td><td>${fmt(d.predicted)}</td><td>${fmt(d.actual)}</td><td>${fmt(d.diff)}</td><td>${d.pct || "—"}</td>
          </tr>`).join("")}
        </tbody>
      </table>
      <p class="note">差异 = 真实 − 预测；差异率 = 差异 ÷ 预测 × 100%。预测值=当天 0~15点待提现 ÷ 系数；真实值取次日 09:00 待提现金额作为当天全天的近似实测。</p>
      <p class="footnote">*本报表由 WorkBuddy 自动化脚本生成*</p>
    </div>`;
}

function renderHistory() {
  const h = DATA.history;
  $("#tab-history").innerHTML = `
    <div class="card">
      <h2>📈 历史记录</h2>
      <div class="scroll-x">
        <table class="data-table">
          <thead><tr>
            <th>日期</th><th>待提现金额</th><th>笔数</th><th>当日待提现(15点)</th>
            <th>系数</th><th>预测全天</th><th>次日09实测</th><th>差异</th><th>差异率</th><th>状态</th>
          </tr></thead>
          <tbody>
            ${h.map(d => `<tr>
              <td>${d.run_date}</td><td>${fmt(d.pending_amount)}</td><td>${d.pending_count}</td>
              <td>${fmt(d.today_15)}</td><td>${d.coefficient || "—"}</td><td>${fmt(d.predicted_full)}</td>
              <td>${fmt(d.actual_next_day_09)}</td><td class="${d.diff && d.diff < 0 ? 'neg' : ''}">${fmt(d.diff)}</td>
              <td>${fmtPct(d.diff_pct)}</td><td>${d.status || "—"}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
}

function renderPredict() {
  const p = DATA.predict;
  const s = DATA.settings;
  $("#tab-predict").innerHTML = `
    <div class="card">
      <h2>🔮 预测</h2>
      <div class="grid-2">
        <div class="stat-box"><label>今日</label><b>${p.today}</b></div>
        <div class="stat-box"><label>日报</label><b>${DATA.status.report_exists ? "已生成 " + DATA.status.report_time : "未生成"}</b></div>
        <div class="stat-box"><label>待提现状态</label><b>${DATA.status.pending_status}</b></div>
        <div class="stat-box"><label>失败核查</label><b>${DATA.status.fail_status}</b></div>
        <div class="stat-box"><label>今日系数</label><b>${p.coefficient}</b></div>
        <div class="stat-box"><label>系数来源</label><span class="small">${p.coefficient_source}</span></div>
        <div class="stat-box"><label>预测全天</label><b>${p.predicted_full ? fmt(p.predicted_full) : "待 " + s.fail.time + " 生成"}</b></div>
        <div class="stat-box"><label>0~15点合计</label><b>${fmt(p.total_partial)}</b></div>
        <div class="stat-box"><label>0~24点合计</label><b>${fmt(p.total_full)}</b></div>
      </div>
    </div>`;
}

function renderCoefficient() {
  const c = DATA.coefficient;
  const sets = Object.entries(c.sets).map(([k, v]) => ({ key: k, ...v }));
  $("#tab-coefficient").innerHTML = `
    <div class="card">
      <h2>📊 预测系数</h2>
      <div class="grid-2">
        <div class="stat-box"><label>来源</label><b>${sets.find(s => s.key === c.active)?.label || c.active}</b></div>
        <div class="stat-box"><label>计算时间</label><span class="small">${c.sets[c.active]?.computed_at || "2026-07-28 19:48:16"}</span></div>
        <div class="stat-box"><label>系数(coeff)</label><b>${c.sets[c.active]?.coeff}</b></div>
        <div class="stat-box"><label>汇总比值(pooled)</label><b>${c.sets[c.active]?.pooled}</b></div>
        <div class="stat-box"><label>区间</label><span class="small">${c.sets[c.active]?.range}</span></div>
        <div class="stat-box"><label>天数 / 样本</label><b>${c.sets[c.active]?.days} 天 / ${c.sets[c.active]?.rows?.toLocaleString()} 行</b></div>
        <div class="stat-box"><label>0~15点合计</label><b>${fmt(c.sets[c.active]?.total_partial)}</b></div>
        <div class="stat-box"><label>0~24点合计</label><b>${fmt(c.sets[c.active]?.total_full)}</b></div>
      </div>
      <h3>系数集</h3>
      <table class="data-table">
        <thead><tr><th>系数集</th><th>当前</th><th>系数</th><th>汇总比值</th><th>区间</th><th>天数</th><th>样本</th></tr></thead>
        <tbody>
          ${sets.map(s => `<tr class="${s.key === c.active ? 'active-row' : ''}">
            <td>${s.label}</td><td>${s.key === c.active ? "✅" : ""}</td>
            <td>${s.coeff}</td><td>${s.pooled}</td><td>${s.range}</td><td>${s.days}</td><td>${s.rows?.toLocaleString()}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderForecastDiff() {
  const f = DATA.forecast_diff;
  $("#tab-forecast").innerHTML = `
    <div class="card">
      <h2>🔍 预测 vs 真实 比对</h2>
      <table class="data-table">
        <thead><tr>
          <th>预测基于日</th><th>当日15点待提现</th><th>系数</th><th>预测全天</th>
          <th>模式</th><th>次日09实测</th><th>差异</th><th>差异率</th><th>状态</th>
        </tr></thead>
        <tbody>
          ${f.map(d => `<tr>
            <td>${d.predict_date}</td><td>${fmt(d.today_pending_15)}</td><td>${d.coefficient || "—"}</td>
            <td>${fmt(d.predicted_full)}</td><td>${d.mode || "—"}</td><td>${fmt(d.actual_next_day_09)}</td>
            <td class="${d.diff && d.diff < 0 ? 'neg' : ''}">${fmt(d.diff)}</td>
            <td>${fmtPct(d.diff_pct)}</td><td>${d.status || "—"}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderSettings() {
  const s = DATA.settings;
  $("#status").innerHTML = `
    <div class="settings-bar">
      <strong>⚙️ 当前配置</strong> &nbsp;|&nbsp;
      待提现推送: 时间 ${s.pending.time} · 范围 ${s.pending.data_range} · 微信推送 ${s.pending.wechat_push ? "开" : "关"} &nbsp;|&nbsp;
      失败核查: 时间 ${s.fail.time} · 范围 ${s.fail.data_range} · 微信推送 ${s.fail.wechat_push ? "开" : "关"} &nbsp;|&nbsp;
      节假日处理: 跳过 ${s.holiday.skip ? "是" : "否"} · 累积 ${s.holiday.accumulate ? "是" : "否"} · 已配置 ${s.holiday.holidays_count} 天
      &nbsp;|&nbsp; <a href="#" id="gotoConfig">去修改 →</a>
    </div>`;
  const gc = $("#gotoConfig");
  if (gc) gc.addEventListener("click", (e) => {
    e.preventDefault();
    $$(".tab").forEach(b => b.classList.remove("active"));
    $$(".panel").forEach(p => p.classList.remove("active"));
    $('.tab[data-tab="config"]').classList.add("active");
    $("#tab-config").classList.add("active");
  });
}

const RANGE_OPTS = ["T-1", "T-2", "T-3", "T-0"];
function rangeOptions(v) {
  return RANGE_OPTS.map(r => `<option value="${r}" ${r === v ? "selected" : ""}>${r}</option>`).join("");
}

function renderConfig() {
  const s = DATA.settings;
  $("#tab-config").innerHTML = `
    <div class="card">
      <h2>⚙️ 配置（可在线修改）</h2>
      <p class="meta">修改后点「保存配置」，写入云端 Supabase，家/公司任意浏览器同步生效。</p>

      <h3>待提现推送</h3>
      <div class="form-row">
        <label>推送时间</label><input type="time" id="pending_time" value="${s.pending.time}">
        <label>数据范围</label><select id="pending_range">${rangeOptions(s.pending.data_range)}</select>
        <label><input type="checkbox" id="pending_wechat" ${s.pending.wechat_push ? "checked" : ""}> 微信推送</label>
      </div>

      <h3>失败核查</h3>
      <div class="form-row">
        <label>核查时间</label><input type="time" id="fail_time" value="${s.fail.time}">
        <label>数据范围</label><select id="fail_range">${rangeOptions(s.fail.data_range)}</select>
        <label><input type="checkbox" id="fail_wechat" ${s.fail.wechat_push ? "checked" : ""}> 微信推送</label>
      </div>

      <h3>节假日处理</h3>
      <div class="form-row">
        <label><input type="checkbox" id="holiday_skip" ${s.holiday.skip ? "checked" : ""}> 跳过节假日</label>
        <label><input type="checkbox" id="holiday_accumulate" ${s.holiday.accumulate ? "checked" : ""}> 累计</label>
      </div>
      <div class="form-row col">
        <label>已配置节假日（每行一个日期 YYYY-MM-DD）</label>
        <textarea id="holiday_list" rows="7">${(s.holiday.holidays || []).join("\n")}</textarea>
        <span class="small" id="holiday_count">共 ${(s.holiday.holidays || []).length} 天</span>
      </div>

      <div class="form-row">
        <label><input type="checkbox" id="confirmEdit"> 我确认要修改以上配置</label>
      </div>
      <div class="form-actions">
        <button id="saveConfig" class="btn">💾 保存配置</button>
        <span id="configStatus" class="config-status"></span>
      </div>
      <p class="note">说明：配置保存在云端 Supabase，公开网页均可读写（仅供内部使用）。若日后需限制修改权限，可加访问口令。本地 8766 自动化要真正采用这些配置，需让其改为读取云端配置（可后续对接）。</p>
    </div>`;

  // 实时统计节假日天数
  const listEl = $("#holiday_list");
  const countEl = $("#holiday_count");
  listEl.addEventListener("input", () => {
    const n = listEl.value.split("\n").map(x => x.trim()).filter(Boolean).length;
    countEl.textContent = "共 " + n + " 天";
  });

  $("#saveConfig").addEventListener("click", saveSettings);
}

async function saveSettings() {
  const status = $("#configStatus");
  if (!$("#confirmEdit").checked) {
    status.textContent = "请先勾选「我确认要修改以上配置」";
    status.className = "config-status err";
    return;
  }
  const holidays = $("#holiday_list").value.split("\n").map(x => x.trim()).filter(Boolean);
  const cfg = {
    pending: { time: $("#pending_time").value, data_range: $("#pending_range").value, wechat_push: $("#pending_wechat").checked },
    fail: { time: $("#fail_time").value, data_range: $("#fail_range").value, wechat_push: $("#fail_wechat").checked },
    holiday: { skip: $("#holiday_skip").checked, accumulate: $("#holiday_accumulate").checked, holidays }
  };
  status.textContent = "保存中…";
  status.className = "config-status";
  try {
    await upsertSettings(cfg);
    DATA.settings = normalizeSettings(cfg);
    status.textContent = "✅ 已保存到云端";
    status.className = "config-status ok";
    renderReport();
    renderPredict();
    renderSettings();
  } catch (e) {
    status.textContent = "❌ 保存失败：" + e.message + "（可能云端不可达，请检查网络后重试）";
    status.className = "config-status err";
  }
}

// ========== Tab 切换 ==========
$$(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach(b => b.classList.remove("active"));
    $$(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $("#" + "tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ========== 初始化 ==========
function startApp() {
  (async () => {
    try {
      const src = await loadSettings();
      const src2 = await loadReport();
      renderReport();
      renderHistory();
      renderPredict();
      renderCoefficient();
      renderForecastDiff();
      renderConfig();
      renderSettings();
      const cfgTxt = src === "cloud" ? "配置已从云端加载" : "配置为内置默认";
      const repTxt = src2 ? ("报表已从云端加载(" + new Date(src2).toLocaleString("zh-CN") + ")") : "报表为内置快照";
      $("#genTime").textContent = "快照时间: " + (DATA.report.generated_at || "?") + " · " + cfgTxt + " · " + repTxt;
      $("#status").className = "status ok";
    } catch (e) {
      $("#status").textContent = "渲染错误: " + e.message;
      $("#status").className = "status err";
    }
  })();
}

document.addEventListener("DOMContentLoaded", () => {
  // 口令门接线
  document.getElementById("gateBtn").addEventListener("click", verifyGate);
  document.getElementById("gatePwd").addEventListener("keydown", (e) => {
    if (e.key === "Enter") verifyGate();
  });
  const lb = document.getElementById("lockBtn");
  if (lb) lb.addEventListener("click", lockNow);

  // 已在本会话解锁过（刷新/切 tab 不重复弹），否则弹出口令框
  if (sessionStorage.getItem("wb_unlocked") === "1") {
    document.getElementById("gate").style.display = "none";
    document.getElementById("app").style.display = "";
    startApp();
  } else {
    document.getElementById("gate").style.display = "flex";
    document.getElementById("app").style.display = "none";
    document.getElementById("gatePwd").focus();
  }
});

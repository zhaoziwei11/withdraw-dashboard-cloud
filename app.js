// 承运提现日报 · 云端看板（数据内置版）
// 数据来源：本机 8766 控制台 2026-07-31 08:55:22 快照
// 不依赖 Supabase / 本机服务，纯静态可部署

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
    holiday: { skip: true, accumulate: true, holidays_count: 33 }
  },

  status: {
    today: "2026-07-31",
    report_exists: true,
    report_time: "2026-07-31 08:55:22",
    pending_status: "已生成 ¥890,765.61 / 425 笔",
    fail_status: "未运行"
  }
};

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
  $("#tab-report").innerHTML = `
    <div class="card">
      <h2>承运提现日报 - ${r.date}</h2>
      <p class="meta">生成时间: ${r.generated_at} | 数据来源: ${r.source} | 统计口径: ${r.stat_range}</p>

      <h3>一、待提现金额(需求一 · ${DATA.settings.pending.time})</h3>
      <div class="big-num">
        <span class="amount">${fmt(r.pending_amount)}</span>
        <span class="count">/ ${r.pending_count} 笔</span>
      </div>

      <h3>二、失败原因 Top 3(${DATA.settings.fail.time})</h3>
      <p>${r.fail_top3}</p>

      <h3>三、需求二 · 当日待提现与明日提现预测(${DATA.settings.fail.time})</h3>
      <p>${r.demand2_note}</p>

      <h4>系数对比(当前 active vs 上次)</h4>
      <ul>
        <li>当前系数(active=${DATA.coefficient.active}): 系数 <b>${r.coeff_active.coeff}</b> (汇总比值 ${r.coeff_active.pooled}) · 区间 ${r.coeff_active.range}, ${r.coeff_active.days} 天, 样本 ${r.coeff_active.rows} 行</li>
        <li>区间 0~${DATA.coefficient.sets[DATA.coefficient.active].split_hour || 15}点 合计 <b>${fmt(r.partial_total)}</b> / 0~24点 合计 <b>${fmt(r.full_total)}</b></li>
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
        <div class="stat-box"><label>预测全天</label><b>${p.predicted_full ? fmt(p.predicted_full) : "待 " + DATA.settings.fail.time + " 生成"}</b></div>
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
  // Settings shown inline in the status area
  $("#status").innerHTML = `
    <div class="settings-bar">
      <strong>⚙️ 当前配置</strong> &nbsp;|&nbsp;
      待提现推送: 时间 ${s.pending.time} · 范围 ${s.pending.data_range} · 微信推送 ${s.pending.wechat_push ? "开" : "关"} &nbsp;|&nbsp;
      失败核查: 时间 ${s.fail.time} · 范围 ${s.fail.data_range} · 微信推送 ${s.fail.wechat_push ? "开" : "关"} &nbsp;|&nbsp;
      节假日处理: 跳过 ${s.holiday.skip ? "是" : "否"} · 累积 ${s.holiday.accumulate ? "是" : "否"} · 已配置 ${s.holiday.holidays_count} 天
    </div>`;
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
document.addEventListener("DOMContentLoaded", () => {
  try {
    renderReport();
    renderHistory();
    renderPredict();
    renderCoefficient();
    renderForecastDiff();
    renderSettings();
    $("#genTime").textContent = "快照时间: " + DATA.report.generated_at;
    $("#status").className = "status ok";
  } catch(e) {
    $("#status").textContent = "渲染错误: " + e.message;
    $("#status").className = "status err";
  }
});

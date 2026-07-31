// 承运提现日报 · 云端看板前端
// 数据来自 Supabase（本机 sync_to_cloud.py 抓取后写入），此处只读渲染。
const SUPABASE_URL = "https://kbelxtwmqfbkrbrnetzzm.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtiZWx4dHdtcWZia3JibmV0enptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyMjg2MTIsImV4cCI6MjEwMDgwNDYxMn0.VWHOrivhqd3NlFBGAXakdGWKbGhSnZ79GpLVYPZXDq0";

function el(id) { return document.getElementById(id); }

function renderMarkdown(container, md) {
  if (md == null) { container.innerHTML = '<p class="empty">（无数据）</p>'; return; }
  try { container.innerHTML = marked.parse(String(md)); }
  catch (e) { container.textContent = String(md); }
}

function renderTable(container, rows) {
  if (!rows || !Array.isArray(rows) || !rows.length) {
    container.innerHTML = '<p class="empty">（无数据）</p>';
    return;
  }
  const cols = Object.keys(rows[0]);
  let html = '<table class="grid"><thead><tr>';
  cols.forEach(c => html += `<th>${esc(c)}</th>`);
  html += '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>';
    cols.forEach(c => html += `<td>${esc(r[c])}</td>`);
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderJson(container, obj) {
  if (obj == null) { container.innerHTML = '<p class="empty">（无数据）</p>'; return; }
  if (Array.isArray(obj)) { renderTable(container, obj); return; }
  if (typeof obj === 'object') {
    const keys = Object.keys(obj);
    let html = '<table class="grid"><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>';
    keys.forEach(k => html += `<tr><td>${esc(k)}</td><td>${esc(obj[k])}</td></tr>`);
    html += '</tbody></table>';
    container.innerHTML = html;
    return;
  }
  container.textContent = String(obj);
}

function esc(v) {
  if (v == null) return '';
  return String(v).replace(/[&<>]/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[s]));
}

async function load() {
  const statusEl = el('status');
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/withdraw_reports?select=*&order=created_at.desc&limit=1`,
      { headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` } }
    );
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const rows = await res.json();
    if (!rows.length) {
      statusEl.textContent = '暂无数据：请先在本机运行 sync/sync_to_cloud.py 同步。';
      return;
    }
    const row = rows[0];
    const p = row.payload || {};
    if (row.generated_at) {
      el('genTime').textContent = '生成于 ' + new Date(row.generated_at).toLocaleString('zh-CN');
    }
    renderMarkdown(el('tab-report'), p.report);
    renderTable(el('tab-history'), p.history);
    renderJson(el('tab-predict'), p.predict);
    renderJson(el('tab-coefficient'), p.coefficient || p.coefficients_auto);
    renderJson(el('tab-forecast'), p.forecast_diff);
    statusEl.textContent = '';
  } catch (e) {
    statusEl.textContent = '加载失败：' + e.message;
  }
}

// Tab 切换
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    el('tab-' + btn.dataset.tab).classList.add('active');
  });
});

load();

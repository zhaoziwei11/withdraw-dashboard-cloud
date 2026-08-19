# 承运提现日报 · 云端看板（前端）

把「承运提现日报控制台」(本机 8766) 的**显示前端**拆出来上云，让你在**家 / 公司任意浏览器**都能看、都能改功能；**抓取引擎**仍留在本机（需登录公司财务中心）。

## 架构

```
本机(8766 控制台) / GitHub Actions
  ├─ dashboard.py 抓取公司财务数据 → 本地文件
  └─ sync/sync_to_cloud.py  → 写入本仓库 data/dashboard.json (GitHub Contents API)
                                      │
                                      ▼
云端看板(本仓库, GitHub Pages 同源)
  └─ index.html + app.js  → 读 ./data/dashboard.json → 渲染展示
```

- **数据**：本机抓取后由 `sync/sync_to_cloud.py` 推到本仓库 `data/dashboard.json`（GitHub Contents API，无需第三方数据库）。
- **显示**：本仓库静态页（GitHub Pages），任意浏览器同源访问 `./data/dashboard.json`。
- **改功能**：编辑本仓库源码 → 重新部署（见下）。抓取/登录仍在本机触发。

> 注：此前用 Supabase 作后端，但其域名在国内被 DNS 污染，浏览器无法读取，故改为 GitHub 仓库文件（同源、稳定）。

## 本机同步（每次抓取后跑一次）

双击 `sync/同步到云端看板.bat`，或：

```bash
python sync/sync_to_cloud.py
```

脚本默认使用内置 PAT 写仓库；也可用环境变量 `GH_TOKEN` 覆盖，`GH_REPO` / `GH_BRANCH` / `GH_DATA_PATH` 可自定义。

## 跨设备开发（在家 / 公司都能改、都能部署）

源码已纳入 Git（本仓库）。你**通过 WorkBuddy 对话让我改代码**即可：我在任意设备的 WorkBuddy 里
`git clone` 本仓库 → 编辑 `index.html` / `app.js` / `styles.css` → 重新部署成公网网址。

### 把源码推到 GitHub（一次性）
```bash
git remote add origin https://github.com/zhaoziwei11/withdraw-dashboard-cloud.git
git branch -M main
git push -u origin main
```
> 需要 GitHub Personal Access Token（不能用账号密码）。生成：GitHub → Settings → Developer settings → PAT → fine-grained，勾 repo。

### 重新部署成公网网址
- 让 WorkBuddy 部署：说「部署 withdraw-dashboard-cloud 最新版」，它拉取仓库并发布新链接。
- 或把仓库连到 CloudStudio，配置构建命令（无需构建，静态站直接指定入口 `index.html`），每次 push 自动上线。

## 隐私说明
看板为**只读快照**，URL 公开可读（与之前部署的只读快照同理）。`schema.sql` 已放开匿名读取。
如含敏感财务数据，建议改为登录后可见（收紧 RLS 策略）。

-- 承运提现日报 · 云端看板数据表
-- 在 Supabase 控制台 → SQL Editor 粘贴运行一次即可。
create table if not exists public.withdraw_reports (
  id bigint generated always as identity primary key,
  owner uuid references auth.users,
  generated_at timestamptz,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_withdraw_reports_created
  on public.withdraw_reports (created_at desc);

alter table public.withdraw_reports enable row level security;

-- 看板为只读快照，URL 本就公开，允许匿名读取最新一条
drop policy if exists "public read withdraw_reports" on public.withdraw_reports;
create policy "public read withdraw_reports"
  on public.withdraw_reports for select
  using (true);

-- 写入仅由本机 sync_to_cloud.py 完成（使用 anon key，故放开匿名插入）
-- 如需更严格，可改为 service_role 写入并删除此策略
drop policy if exists "anon insert withdraw_reports" on public.withdraw_reports;
create policy "anon insert withdraw_reports"
  on public.withdraw_reports for insert
  with check (true);

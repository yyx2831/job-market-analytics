# 第二阶段执行计划：规模化采集 + 数据挖掘

> 接续 MVP 框架验证（51job xbrowser 已跑通 74 条）  
> 目标：真实数据量突破 1000 条 → 数据挖掘初探  
> 创建：2026-06-06  
> 更新：2026-06-06（Phase 1.3 + Phase 2.1 + Phase 2.2 已完成）

---

## 前置状态

- ✅ 51job xbrowser 采集器稳定（74 条成都 Python 岗位）
- ✅ 全链路：采集 → 归一化 → SQLite → Streamlit
- ✅ 字段覆盖率 100%，薪资解析 95%+
- ✅ 断点续传（job51_xbrowser collect 支持 `reset_progress` 参数）
- ✅ 反爬工具模块 `src/scraping/anti_crawl.py`（随机等待、UA轮换、行为模拟、重试装饰器）
- ✅ 增量 upsert：database.py 支持 `import_csv_with_stats`，按 dedupe_key ON CONFLICT UPDATE
- ✅ crawl_runs 表：每次采集自动记录 source/city/keywords/start_time/end_time/新增/更新/跳过数
- ❌ 只有 1 个城市 / 1 个关键词 / 74 条真实数据（待规模采集）
- ❌ 企业官网 SPA 未解决
- ❌ 无多源去重（多平台合并，Phase 4 后续）

---

## Phase 1：规模化采集（今日）

目标：把 51job 真实数据从 74 条拉到 1000+ 条

### 1.1 验证多城市代码

先对北京/上海/广州/深圳/杭州做单页试探，确认 `jobArea` 参数正确。

**任务：**
- [x] 成都: 090200 ✅
- [ ] 上海: 020000 → 需验证（代码已配置，待运行验证）
- [ ] 北京: 010000 → 需验证（注意：北京代码原为 030000，已修正为 010000）
- [ ] 广州: 030200 → 需验证
- [ ] 深圳: 040000 → 需验证
- [ ] 杭州: 080200 → 需验证

> ⚠️ 注意：北京城市代码原文档标注 030000，实际应为 010000，代码中已修正。运行前建议先单页测试：
> ```bash
> python scripts/run_spider.py --source job51_xbrowser --city 北京 --keywords Python --limit 20
> ```

### 1.2 多关键词批量采集

10 个关键词 × 成都 × 每词 50 条 = 500 条  
5 个城市 × Python × 每城 40 条 = 200 条

**关键词列表：**
`Python`, `Java`, `前端`, `数据分析`, `测试`, `运维`, `产品经理`, `UI设计`, `运营`, `销售`

**产出：** `data/raw/YYYY-MM-DD/job51.jsonl` 新增 700+ 条

### 1.3 批量采集脚本 ✅ 已完成

`run_spider.py` 已支持：
- `--all-keywords` 模式（使用全部 10 个默认关键词）
- `--cities` 多城市（自动城市间等待 20-40 秒）
- `--limit-per-kw` 每关键词上限
- 关键词间自动随机等待 5-12 秒（反爬保护）
- 断点续传（中断后自动从上次页码继续）

**推荐执行命令：**

```bash
# 第一步：成都 10 个关键词，每个 50 条 → 预计 500 条
python scripts/run_spider.py --source job51_xbrowser --city 成都 --all-keywords --limit-per-kw 50

# 第二步（成都跑完确认数据质量后）：5 个城市 Python，每城 40 条 → 预计 200 条
python scripts/run_spider.py --source job51_xbrowser --cities 上海 北京 广州 深圳 杭州 --keywords Python --limit-per-kw 40

# 断点续传（中断后重跑，自动继续上次进度）
python scripts/run_spider.py --source job51_xbrowser --city 成都 --all-keywords --limit-per-kw 50

# 强制重置进度从头采集
python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python --limit-per-kw 50
# 注意：如需重置需在 collect() 传 reset_progress=True，或手动删除 data/raw/progress/ 下对应文件
```

---

## Phase 2：数据管道加固 ✅ 已完成

### 2.1 增量 upsert ✅

`src/database.py` 新增 `import_csv_with_stats()`：
- 以 `dedupe_key`（= `source|source_job_id`）为唯一键
- 已存在的记录：UPDATE 可变字段（薪资、技能、描述等），保留 created_at
- 新记录：INSERT
- 返回 `ImportStats(inserted, updated, skipped)` 明细统计
- `import_csv()` 保持向后兼容（返回 inserted 数量）

### 2.2 采集日志与运行记录 ✅

新增 `crawl_runs` 表（已加入 SCHEMA）：

| 字段 | 说明 |
|------|------|
| source | 数据源（job51_xbrowser） |
| city | 采集城市 |
| keywords | 关键词（逗号分隔） |
| start_time | 开始时间 |
| end_time | 结束时间 |
| total_collected | 本次采集总条数 |
| new_inserted | 新增入库条数 |
| updated | 更新条数 |
| skipped | 跳过条数（去重键冲突/缺失） |

查询历史运行记录：
```sql
SELECT * FROM crawl_runs ORDER BY created_at DESC LIMIT 20;
```

新增反爬工具 `src/scraping/anti_crawl.py`：
- `random_sleep(min, max)` — 随机等待
- `page_interval_sleep(page)` — 页间等待（随页码适当增加）
- `keyword_interval_sleep()` — 关键词间等待（5-12 秒）
- `city_interval_sleep()` — 城市间等待（20-40 秒）
- `build_human_behavior_js()` — 生成滚动/鼠标模拟 JS
- `retry_on_failure(max_retries, ...)` — 指数退避重试装饰器

### 2.3 定时采集（可选，后续）

cron job 每日自动跑一批关键词，待数据规模稳定后接入。  
建议用 `APScheduler` 或系统 crontab：

```bash
# crontab 示例（每日凌晨 2:00 增量采集成都 Python）
0 2 * * * cd /path/to/job-market-analytics && python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python --limit-per-kw 50
```

---

## Phase 3：数据挖掘 MVP（500+ 条数据后启动）

### 3.1 技能共现网络

基于岗位的 skills 字段，构建技能共现矩阵，输出交互式网络图。

### 3.2 薪资影响因素分析

多变量回归：学历、经验年限、行业、区域 → 薪资区间。

### 3.3 岗位描述聚类

对 description 做 TF-IDF 或 embedding → 自动发现岗位类型集群。

### 3.4 城市对比仪表盘

多城市数据足够后，在 Streamlit 增加城市切换和对比视图。

---

## Phase 4：企业官网 SPA（待研究）

### 4.1 技术方案评估

- Playwright headful（比 xbrowser 更轻量）
- Puppeteer
- 直接调用企业招聘 API（如字节的 job.bytedance.com API）

### 4.2 先行验证

选 1 个站点（美团或字节），尝试 Playwright 渲染 + API 拦截方案。

---

## 执行顺序

```
Phase 1.1（30min，验证北京等城市代码）→ 
Phase 1.2 成都全关键词（约 2h 跑采集）→ 
Phase 1.2 多城市 Python（约 1h 跑采集）→ 
Phase 3（半天，需数据达标 500+ 条）
```

**当前状态：Phase 1.3 + Phase 2.1 + Phase 2.2 已完成，可直接执行 Phase 1.1 城市验证。**

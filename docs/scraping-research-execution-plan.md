# 国内招聘数据采集研究与执行计划

> 项目：job-market-analytics  
> 日期：2026-06-04  
> 目标：在当前 CSV -> SQLite -> Streamlit 分析链路基础上，接入真实岗位数据，并形成可维护、可审计、可逐步扩展的数据采集工程。

---

## 1. 总体策略

当前项目已经具备样例数据生成、CSV 导入、清洗、去重、技能抽取、SQLite 入库和 Streamlit 分析能力。真实数据采集不应直接以“攻克最强反爬平台”为第一目标，而应先建立稳定的数据契约和端到端闭环：

```text
数据源发现 -> 小规模采集 -> 原始数据留存 -> 字段归一化 -> 兼容 CSV -> SQLite 入库 -> 仪表盘验证 -> 质量统计
```

第一阶段目标是拿到可分析、可复跑、可解释的真实岗位数据，而不是追求最高日采集量。平台接入按风险和可持续性分层推进：

| 层级 | 数据源类型 | 优先级 | 目标 | 说明 |
| --- | --- | --- | --- | --- |
| L1 | 授权 API、开放数据、合作数据 | P0 | 长期稳定数据源 | 成本可能较高，但法律和维护风险最低 |
| L2 | 企业官网招聘页、校园招聘页、ATS 页面 | P0 | 快速建立真实数据闭环 | 字段结构分散，但限制通常较低 |
| L3 | 公开搜索结果页、轻交互招聘站 | P1 | 扩大岗位覆盖 | 需要限速、缓存、结构变更监控 |
| L4 | 高限制平台，如 BOSS、智联、拉勾 | P2 | 技术研究和可行性评估 | 不作为 MVP 主路径，避免依赖绕过机制 |

---

## 2. 成功标准

### 2.1 MVP 成功标准

MVP 只要求完成一个数据源的端到端闭环：

- 支持成都岗位数据采集，至少覆盖 5 个关键词。
- 单次运行可输出 200 条以内的真实岗位记录。
- 输出兼容当前 `scripts/build_database.py --csv ...` 的 CSV。
- 导入后 Streamlit 仪表盘可以正常展示城市概览、岗位分析、区域分析、技能分析和岗位明细。
- 采集过程生成可追踪日志和质量报告。

### 2.2 第一阶段质量指标

| 指标 | 验收线 | 说明 |
| --- | ---: | --- |
| `title` 非空率 | >= 98% | 岗位名称是核心字段 |
| `company_name` 非空率 | >= 95% | 用于公司统计和去重 |
| `salary_text` 非空率 | >= 70% | 不强制所有岗位有薪资 |
| 薪资解析成功率 | >= 60% | 以 `salary_avg` 非空为准 |
| `source_url` 非空率 | >= 98% | 方便追溯 |
| 重复率 | <= 20% | 以统一去重规则计算 |
| 入库成功率 | >= 95% | CSV 到 SQLite 导入无结构错误 |

---

## 3. 数据契约

### 3.1 兼容当前项目的 CSV 字段

采集清洗后的 CSV 必须优先保持当前项目兼容。字段如下：

| 字段 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `source_job_id` | 否 | 平台原始岗位 ID，能拿到时必须填 | `51job-123456` |
| `title` | 是 | 岗位名称 | `Python 后端工程师` |
| `company_name` | 是 | 公司名称 | `成都某某科技有限公司` |
| `salary_text` | 否 | 原始薪资文本 | `12-20K·13薪` |
| `city` | 是 | 城市 | `成都` |
| `district` | 否 | 区域 | `高新区` |
| `experience` | 否 | 经验要求 | `3-5年` |
| `education` | 否 | 学历要求 | `本科` |
| `industry` | 否 | 行业 | `互联网` |
| `company_size` | 否 | 公司规模 | `100-499人` |
| `financing_stage` | 否 | 融资阶段 | `B轮` |
| `skills` | 否 | 技能，逗号分隔 | `Python,SQL,Redis` |
| `description` | 否 | 岗位描述 | `负责后端服务开发...` |
| `source` | 是 | 数据源标识 | `job51` |
| `source_url` | 是 | 原始岗位链接 | `https://...` |
| `publish_time` | 否 | 发布时间，优先 ISO 日期 | `2026-06-04` |

### 3.2 建议新增的中间字段

这些字段用于 raw/processed 阶段，不要求当前 SQLite 立即支持：

| 字段 | 用途 |
| --- | --- |
| `crawl_time` | 采集时间，用于增量和数据新鲜度 |
| `raw_hash` | 原始内容 hash，用于结构变更和重复检测 |
| `source_platform_status` | 页面状态，如 `ok`、`blocked`、`not_found`、`parse_error` |
| `normalized_status` | 归一化状态，如 `ok`、`missing_required_field` |
| `parser_version` | 解析器版本，便于回溯 |

### 3.3 去重规则

后续应把当前 `title|company_name|district` 去重升级为分层去重：

1. 优先使用 `source + source_job_id`。
2. 如果没有 `source_job_id`，使用 `source_url` 的规范化结果。
3. 如果 URL 不稳定，回退到 `title + company_name + city + district`。
4. 多平台合并时，使用 `title + company_name + city` 作为候选重复，再人工抽样评估误杀率。

---

## 4. 工程架构

### 4.1 推荐目录

```text
job-market-analytics/
  app.py
  scripts/
    build_database.py
    generate_sample_data.py
    run_spider.py
    normalize_raw_jobs.py
  src/
    analytics.py
    cleaning.py
    database.py
    scraping/
      __init__.py
      base.py
      models.py
      pipeline.py
      quality.py
      sources/
        __init__.py
        job51.py
        company_site.py
  data/
    raw/
      job51/2026-06-04/*.jsonl
      company_site/2026-06-04/*.jsonl
    processed/
      jobs_job51_20260604.csv
      jobs_company_site_20260604.csv
      jobs.db
  logs/
    scraping/
  docs/
    scraping-plan.md
    scraping-research-execution-plan.md
```

### 4.2 核心模块职责

| 模块 | 职责 |
| --- | --- |
| `src/scraping/models.py` | 定义查询参数、原始岗位、归一化岗位的数据结构 |
| `src/scraping/base.py` | 抽象采集器接口、限速、重试、日志上下文 |
| `src/scraping/sources/*.py` | 各数据源的搜索、翻页、详情解析 |
| `src/scraping/pipeline.py` | raw JSONL 到兼容 CSV 的转换 |
| `src/scraping/quality.py` | 生成质量报告，统计缺失率、重复率、解析成功率 |
| `scripts/run_spider.py` | 单次采集入口 |
| `scripts/normalize_raw_jobs.py` | 原始数据离线归一化入口 |

### 4.3 运行入口设计

```bash
python scripts/run_spider.py \
  --source job51 \
  --city 成都 \
  --keywords Python Java 前端 数据分析 产品经理 \
  --limit 200 \
  --output data/raw/job51/2026-06-04/jobs.jsonl
```

归一化：

```bash
python scripts/normalize_raw_jobs.py \
  --source job51 \
  --input data/raw/job51/2026-06-04/jobs.jsonl \
  --output data/processed/jobs_job51_20260604.csv
```

导入现有数据库：

```bash
python scripts/build_database.py \
  --csv data/processed/jobs_job51_20260604.csv \
  --db data/processed/jobs.db
```

启动仪表盘：

```bash
streamlit run app.py
```

---

## 5. 数据源执行路线

### 5.1 阶段 A：企业官网和 ATS 页面

企业官网招聘页、校招页和常见 ATS 系统适合作为第一批真实数据源。它们的优势是页面结构通常稳定，反爬限制较少，缺点是单站岗位量有限。

执行步骤：

1. 建立成都重点企业清单，优先覆盖互联网、软件服务、智能制造、金融科技、教育培训。
2. 对每个企业招聘页记录：入口 URL、城市筛选方式、分页方式、详情页字段。
3. 先选 5-10 个结构清晰的网站，实现 `company_site` 采集器。
4. 输出统一 JSONL，再归一化为兼容 CSV。
5. 对低字段覆盖的网站只保留列表页字段，不强行补齐。

验收标准：

- 至少接入 5 个企业招聘页。
- 合计拿到 100 条以上岗位。
- 每条记录有 `title`、`company_name`、`source_url`、`source`。
- 可导入 SQLite 并在仪表盘展示。

### 5.2 阶段 B：前程无忧公开搜索结果

前程无忧可作为第一个聚合平台研究对象。执行策略应以公开页面解析和低频访问为主，优先验证字段覆盖和稳定性。

执行步骤：

1. 固定城市为成都，关键词从当前样例岗位类型中选择。
2. 小批量访问搜索结果页，记录 HTML 结构、分页参数、详情 URL。
3. 优先解析列表页已有字段；详情页作为增强，不作为 MVP 必需。
4. 设置保守限速：页面间隔 5-15 秒，失败后指数退避。
5. 每次运行限制总量，默认 `--limit 200`。

重点字段：

- 列表页：`title`、`company_name`、`salary_text`、`district`、`experience`、`education`、`source_url`。
- 详情页：`description`、`company_size`、`industry`、`publish_time`。

失败处理：

- HTTP 403、验证码页、登录页、空结果都记录为 `source_platform_status`。
- 同一关键词连续失败 3 次后停止该关键词。
- 不在主流程中依赖验证码处理服务。

### 5.3 阶段 C：BOSS、智联、拉勾高限制平台研究

这些平台岗位量大，但登录、验证码、动态 token、设备指纹和频率限制都可能显著增加法律、账号和维护风险。它们不应阻塞 MVP。

研究目标：

- 判断公开可访问字段覆盖率。
- 评估是否存在官方、合作或授权渠道。
- 评估低频人工授权导出的可行性。
- 记录字段结构、失败模式和维护成本。

不纳入默认执行路径的事项：

- 不把破解动态 token 作为交付前提。
- 不把验证码识别或打码平台作为稳定依赖。
- 不采集登录后私有数据、聊天数据、简历数据、联系方式。
- 不绕过付费墙或访问控制。

可接受的研究产出：

- 平台字段映射表。
- 小规模人工授权样本的归一化结果。
- 结构变化监控建议。
- 是否值得进入下一阶段的 Go/No-Go 结论。

---

## 6. 高级技术方案

### 6.1 自适应解析

不同招聘站字段命名和 DOM 结构差异很大，建议实现两层解析：

1. 规则解析：CSS selector、XPath、JSON-LD、页面内嵌 JSON。
2. 兜底解析：基于文本块的字段识别，例如薪资、经验、学历、城市、公司规模。

兜底解析只做字段补充，不覆盖明确结构化字段。每条记录保留 `parser_version` 和 `normalized_status`，方便后续回溯。

### 6.2 原始数据留存

所有采集结果先写 JSONL，不直接入库。每行记录包含：

```json
{
  "source": "job51",
  "query": {"city": "成都", "keyword": "Python", "page": 1},
  "source_url": "https://...",
  "fetched_at": "2026-06-04T10:00:00+08:00",
  "status": "ok",
  "raw": {
    "title": "...",
    "company_name": "...",
    "salary_text": "..."
  },
  "raw_html_path": null,
  "raw_hash": "sha256:..."
}
```

这样可以把采集、解析、入库拆开，后续平台结构变化时可以重新解析历史 raw 数据。

### 6.3 限速与断点续跑

限速策略：

- 默认串行采集，MVP 不开并发。
- 搜索页间隔 5-15 秒。
- 详情页间隔 3-10 秒。
- 遇到 403、验证码、登录页时停止当前关键词，不继续重试轰炸。

断点续跑：

- 以 `source + city + keyword + page` 记录进度。
- 已成功写入 JSONL 的 `source_url` 不重复采集。
- 中断后从最后一个未完成 query 恢复。

### 6.4 质量报告

每次归一化后输出质量报告，建议路径：

```text
data/processed/reports/quality_job51_20260604.json
```

报告字段：

```json
{
  "source": "job51",
  "date": "2026-06-04",
  "raw_count": 200,
  "normalized_count": 186,
  "duplicate_count": 24,
  "missing_rates": {
    "title": 0.0,
    "company_name": 0.03,
    "salary_text": 0.22,
    "source_url": 0.0
  },
  "salary_parse_success_rate": 0.68,
  "status_counts": {
    "ok": 186,
    "parse_error": 9,
    "blocked": 5
  }
}
```

---

## 7. 数据库演进建议

当前 `jobs` 表已经能支撑 MVP，但真实数据接入后建议逐步增强：

### 7.1 短期

- 保持 CSV 导入兼容，先不破坏现有 `app.py`。
- `import_csv` 增加 upsert 能力：同一岗位重复出现时更新 `updated_at` 和最新字段。
- `dedupe_key` 生成逻辑纳入 `source` 和 `source_job_id` 优先级。
- 增加导入报告：新增数、跳过数、更新数、失败数。

### 7.2 中期

建议增加表：

| 表 | 用途 |
| --- | --- |
| `crawl_runs` | 每次采集任务的参数、开始时间、结束时间、状态 |
| `raw_jobs` | 原始 JSON、hash、状态、来源 URL |
| `import_errors` | 字段缺失、解析失败、入库失败的审计 |

SQLite 仍可继续使用。只有当数据量、并发写入或多人访问成为瓶颈时，再迁移 PostgreSQL。

---

## 8. 分阶段执行计划

### 阶段 0：准备和边界确认，0.5 天

交付物：

- 确认目标城市：成都。
- 确认第一批关键词：`Python`、`Java`、`前端`、`数据分析`、`测试`、`运维`、`产品经理`、`UI 设计`、`运营`、`销售`。
- 确认不采集个人联系方式、简历、聊天内容、登录后私有内容。
- 建立 `data/raw/`、`data/processed/reports/`、`logs/scraping/` 的输出约定。

### 阶段 1：采集框架 MVP，1-2 天

交付物：

- `src/scraping/models.py`：数据结构。
- `src/scraping/base.py`：采集器接口、限速、重试。
- `src/scraping/pipeline.py`：JSONL 到兼容 CSV。
- `src/scraping/quality.py`：质量报告。
- `scripts/run_spider.py`：统一入口。
- `scripts/normalize_raw_jobs.py`：离线归一化入口。

验收：

- 使用 mock raw 数据可以生成兼容 CSV。
- 生成的 CSV 可以被当前 `scripts/build_database.py` 导入。
- 现有测试继续通过。

### 阶段 2：企业官网数据源，2-4 天

交付物：

- `company_site` 采集器。
- 5-10 个成都相关企业招聘页配置。
- 100 条以上真实岗位样本。
- 质量报告。

验收：

- 采集、归一化、导入、仪表盘展示完整跑通。
- 字段缺失率和重复率满足 MVP 标准。

### 阶段 3：前程无忧研究接入，3-5 天

交付物：

- `job51` 采集器。
- 搜索页解析和可选详情页解析。
- 城市、关键词、limit 参数支持。
- 200 条以内小规模真实数据。
- 失败状态记录。

验收：

- 运行命令可稳定完成，不依赖人工验证码。
- 遇到限制时能停止并记录，而不是无限重试。
- 输出 CSV 可导入并展示。

### 阶段 4：多源合并和增量更新，2-3 天

交付物：

- 多 CSV 合并策略。
- source 级别去重。
- 导入报告。
- 日级数据目录规范。

验收：

- 同一天多数据源导入后，重复岗位可控。
- 仪表盘能按 `source` 筛选或展示来源。

### 阶段 5：高限制平台研究，持续进行

交付物：

- BOSS、智联、拉勾的平台可行性报告。
- 字段映射表。
- 合规和维护成本评估。
- Go/No-Go 结论。

验收：

- 不把高限制平台作为主数据链路依赖。
- 只有当存在授权、稳定、低风险方式时才进入工程实现。

---

## 9. 测试计划

### 9.1 单元测试

新增测试建议：

- 薪资文本：继续覆盖 `K`、`千`、`万`、年薪、日薪、面议。
- 技能抽取：覆盖岗位标题、技能标签、描述混合输入。
- URL 规范化：去掉追踪参数、统一尾斜杠。
- 去重 key：覆盖有 `source_job_id`、只有 URL、只有标题公司区域三种情况。
- JSONL 解析：坏行、缺字段、空 raw 的容错。

### 9.2 集成测试

必须覆盖：

```text
mock raw JSONL -> normalize_raw_jobs.py -> processed CSV -> build_database.py -> SQLite -> load_jobs
```

验收条件：

- CSV header 与当前导入逻辑兼容。
- SQLite 中 `jobs` 和 `job_skills` 都有数据。
- 重复导入不会产生不可控重复。

### 9.3 小规模真实数据测试

每个新数据源先执行：

```bash
python scripts/run_spider.py --source <source> --city 成都 --keywords Python --limit 20
```

通过后再扩大到 200 条以内。不要直接执行大规模采集。

---

## 10. 风险与合规边界

### 10.1 明确不采集的数据

- 求职者简历、姓名、手机号、邮箱、微信等个人信息。
- 招聘者聊天内容、私信内容。
- 登录后才可见的私有数据。
- 付费墙后的内容。
- 明确禁止自动化访问的数据。

### 10.2 访问控制

- 尊重 robots.txt 和网站服务条款。
- 默认低频访问，不做高并发压测式采集。
- 遇到验证码、403、登录墙时停止当前任务并记录。
- 不把规避访问控制作为稳定生产路径。

### 10.3 内容使用

- 岗位描述可能具有版权属性，分析展示时优先使用摘要、技能、薪资、城市等结构化字段。
- 不对外分发原始岗位详情全文。
- 数据集如需共享，应先脱敏、去重、删除长文本描述和可识别链接。

---

## 11. 当前文档相对原计划的主要优化

相比 `docs/scraping-plan.md`，本计划做了以下调整：

- 从“反爬攻坚优先”调整为“端到端真实数据闭环优先”。
- 明确与当前 CSV、SQLite、Streamlit 架构对接。
- 增加 raw JSONL、质量报告、失败状态、断点续跑、去重升级。
- 把 BOSS、智联、拉勾放入高限制平台研究，不作为 MVP 阻塞项。
- 增加可执行命令、验收标准和测试路径。
- 明确合规边界和不采集的数据类型。

---

## 12. 推荐下一步

按阶段 1 开始实现采集框架 MVP。第一版不需要接入真实网站，先用 mock raw JSONL 跑通：

```text
mock raw JSONL -> compatible CSV -> SQLite -> Streamlit
```

这一步完成后，再接入企业官网或前程无忧小规模真实数据。这样可以把采集不确定性和项目内部数据链路风险分开处理。

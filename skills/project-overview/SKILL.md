# job-market-analytics 项目全貌

> 城市岗位大数据分析平台 — 51job 真实采集 → SQLite 入库 → Streamlit 仪表盘
> 更新时间：2026-06-20 | 基于 commit `1e5b214`（含 uncommitted 修改，Bug 修复完成）

---

## 1. 项目定位

采集 51job 真实招聘数据（成都为主），进行薪资解析、技能抽取、去重入库，最终通过 Streamlit 仪表盘展示市场分析、观点洞察和趋势。

### 核心数据流

```
51job SPA (xbrowser DOM注入) → JSONL → 归一化(CSV) → SQLite(jobs.db) → Streamlit(app.py)
```

### 当前数据规模
- **DB 总量**：2,413 条
- **真实数据**：成都 382 / 西安 221 / 武汉 213 / 重庆 209 / 南京 205 / 广州 97 / 上海 94 / 深圳 87 / 杭州 60 / 北京 50
- **Mock 数据**：约 500 条（boss/lagou/liepin 源标记）

---

## 2. 技术栈

| 层 | 技术 | 用途 |
|---|------|------|
| 采集 | xbrowser (Chrome CDP) + xb.cjs | 操纵系统 Chrome，通过 Vue 组件状态注入切换城市/搜索 |
| 数据处理 | pandas | CSV 清洗、归一化、聚合分析 |
| 存储 | SQLite | 轻量本地库，dedupe_key 唯一约束增量 upsert |
| 展示 | Streamlit + Plotly | 交互式仪表盘，5 个标签页 |
| 技能抽取 | src/skill_dict.py | 预定义关键词字典，子串匹配 |

---

## 3. 项目结构

```
job-market-analytics/
├── app.py                          # Streamlit 仪表盘入口 (356行)
├── requirements.txt                # Python 依赖
├── README.md                       # (过时，需更新)
├── USAGE.md                        # 使用指南
├── .gitignore
│
├── data/
│   ├── raw/                        # 原始采集 JSONL（按日期或按城市归档）
│   └── processed/
│       ├── jobs.db                 # SQLite 数据库（核心）
│       └── reports/                # 采集质量报告 JSON
│
├── src/
│   ├── analytics.py                # 仪表盘指标计算
│   ├── cleaning.py                 # 薪资解析 + 技能抽取 + 去重键生成
│   ├── database.py                 # SQLite 建表 + CSV 导入(upsert) + 采集记录
│   ├── insights.py                 # 行动级观点引擎 (319行)
│   ├── skill_dict.py               # 技能关键词字典
│   ├── sample_data.py              # Mock 数据生成
│   ├── trends.py                   # 趋势分析引擎 (186行)
│   └── scraping/
│       ├── models.py               # RawJob / NormalizedJob dataclass
│       ├── base.py                 # RateLimiter / BaseCollector
│       ├── pipeline.py             # 归一化批处理 + 写入 CSV
│       ├── quality.py              # 质量报告生成
│       ├── anti_crawl.py           # 反爬工具（UA池、随机等待、重试装饰器）
│       └── sources/
│           ├── job51_xbrowser.py   # ★ 主力采集器：DOM+Vue注入 (566行)
│           ├── job51.py            # 静态 HTTP 采集器（备用）
│           └── company_site.py     # 企业官网采集器（未完成）
│
├── scripts/
│   ├── run_spider.py               # ★ 采集入口（核心）
│   ├── run_chengdu_pipeline.py     # 成都采集→入库管道
│   ├── run_pipeline.py             # Mock 全链路
│   ├── build_database.py           # CSV→SQLite 导入
│   ├── normalize_raw_jobs.py       # JSONL→CSV 归一化
│   ├── generate_mock_jsonl.py      # Mock 数据生成
│   ├── jsonl_to_csv.py             # JSONL/CSV 转换
│   ├── collect_near_zhonghe_v2.py  # 一次性定制采集（保留参考）
│   └── archived/                   # 过时脚本归档（7个）
│       ├── README.md
│       ├── collect_chengdu_dom.py  # → 已被 run_spider.py 替代
│       ├── collect_multicity.py    # → 已被 run_spider.py 替代
│       ├── collect_simple.py       # → sync XHR 方案已弃用
│       ├── collect_chengdu_zhaopin.py # → 智联低产源
│       ├── collect_near_zhonghe.py # → 已被 v2 替代
│       ├── collect_simple.sh       # → shell wrapper
│       └── generate_sample_data.py # → 已被 generate_mock_jsonl.py 替代
│
├── tests/
│   └── test_cleaning.py            # 仅有 cleaning.py 的单测
│
├── docs/
│   ├── scraping-plan.md
│   ├── phase2-plan.md
│   ├── scraping-research-execution-plan.md
│   └── expansion-plan.md
│
└── skills/
    └── project-overview/
        └── SKILL.md                # ← 本文件
```

---

## 4. 核心设计决策

### 4.1 采集策略演进
| 代 | 方案 | 结果 |
|----|------|------|
| v1 | sync XHR 直接调用 `we.51job.com/api/job/search-pc` | 约25次后被 WAF 封杀 |
| v2 | SPA DOM 方案：通过 `document.querySelector('#app').__vue__.$store.state` 注入城市 + 关键词 | ✅ 当前主力，绕过 WAF |
| v3 | xb.cjs eval 传参 chengdu-specific URL（`jobArea=090200`） | ✅ 稳定方案 |

### 4.2 51job 城市切换机制（已验证）
- URL 参数：**必须用 `jobArea=090200`**，`location` 参数无效
- 切词时：必须在 Vue 状态中写入 `jobArea`、`cityInfo.code`、`areaTags`
- 城市码规律：**直辖市=XX0000**（北京010000/上海020000/重庆060000），**省会=XX0200**（成都090200/杭州080200/广州030200）

### 4.3 反爬策略
- 页面间隔：1.5-4.0s（加翻页累进）
- 关键词间隔：5-12s
- 城市间隔：60-120s
- `retry_on_failure` 装饰器：指数退避，最多3次重试
- 切换到 DOM 注入方案后 WAF 问题基本解决

### 4.4 数据库设计
- **jobs 表**：`dedupe_key` 列 UNIQUE 约束，实现增量 upsert
- **job_skills 表**：多对多关联，按 job_id 存储技能
- **crawl_runs 表**：审计每次采集的源/城市/关键词/数量统计
- `import_csv_with_stats()` 返回 `ImportStats(inserted, updated, skipped)`

### 4.5 多源结论（2026-06-09~10）
| 来源 | 状态 | 详情 |
|------|------|------|
| **51job** | ✅ 主力 | DOM+Vue注入，已稳定跑通 |
| 智联招聘 | ⚠️ 低产 | URL参数 `jl=489` 不生效，搜索结果中仅~5%为成都岗位 |
| 猎聘 | ❌ | 需要登录态 |
| BOSS直聘 | ❌ | 需要登录态 + API 签名 |
| 拉勾 | ❌ | 需要登录态 |

---

## 5. 关键文件说明

### `app.py` — Streamlit 仪表盘
- 5 个标签页：城市概览、观点洞察、趋势分析、城市对比、岗位明细
- 侧边栏筛选：城市、仅真实数据、技能、区域、行业、学历、经验、搜索
- ⚠️ **已知 Bug**：`real_only` 筛选逻辑反了（勾选"仅真实数据"时过滤掉了真实源）
- 使用 `@st.cache_data(ttl=300)` 缓存数据加载

### `src/scraping/sources/job51_xbrowser.py` — 核心采集器
- `Job51XBrowserCollector` 类
- `CITY_CODES` 字典（有重复项，需要去重）
- 通过 `xb.cjs eval` 注入 JS 代码操作 51job SPA 的 Vue 组件状态
- 关键方法：`search_keyword()`、`collect()`、`_ensure_session()`
- WAF 检测：通过 HTML 内容识别（`WAFBlockError` 异常）

### `src/insights.py` — 观点引擎 v2
- `Insight` 数据类：title + body + level + section + action
- 5 个分类：市场全貌、薪资、技能、公司、职业建议
- 每个 insight 附带可执行行动建议

### `src/trends.py` — 趋势引擎
- `Trend` 数据类：title + body + direction(↑↓→) + strength
- 月度薪资趋势、技能需求变化、行业热度

---

## 6. 已知问题与待优化

### 🐛 Bug
| 位置 | 问题 | 优先级 |
|------|------|--------|
| ~~`app.py:82`~~ | ~~`real_only` 筛选逻辑反了~~ → ✅ 已修复（改为按 source 过滤 mock 源） | ~~🔴~~ ✅ |
| ~~`job51_xbrowser.py`~~ | ~~`CITY_CODES` 字典有重复 key~~ → ✅ 已验证无重复（可能历史版本已修复） | ~~🟡~~ ✅ |
| ~~`USAGE.md`~~ | ~~城市码表有误（北京=030000 应为 010000）~~ → ✅ 已修复并补齐全部10城 | ~~🟡~~ ✅ |
| DB | `job51` 和 `51job_dom` 是同一来源但标记不同 | 🟡 中 |
| DB | 混入了5条上海 + 少量"远程办公"/其他城市数据 | 🟢 低 |

### 🔧 代码质量
| 位置 | 问题 | 建议 |
|------|------|------|
| `app.py` | 单体 373 行，渲染逻辑与数据逻辑混在一起 | 拆分为 pages/ 模块 |
| 全局 | 多处硬编码路径 | 使用 config 对象或环境变量 |
| ~~`scripts/`~~ | ~~7个采集脚本功能重叠~~ → ✅ 已归档到 `scripts/archived/` | ~~合并或标记过时~~ |
| 全局 | 使用 `print()` 而非 logging | 统一使用 logging 模块 |
| `src/analytics.py` | 仅提供 `overview_metrics`，大部分功能已在 app.py 内联 | 评估是否保留 |
| `requirements.txt` | 缺少 jieba | 已部分 pin，但缺少采集框架用到的一些依赖 |

### 📋 项目工程
| 项 | 状态 | 建议 |
|----|------|------|
| `.gitignore` | 有，但可能不完整 | 加 `data/raw/job51_*.jsonl`、`*.log` |
| Git | `app.py` 已修改未提交，6个文件未跟踪 | 整理后提交 |
| 测试 | ✅ 已补齐至 40 个用例（database + scraping + insights） | 覆盖核心模块 |
| README | ✅ 已重写（反映当前架构） | 与 USAGE.md 互补 |
| 类型注解 | 不统一 | 部分文件有 `from __future__ import annotations`，其他无 |

---

## 7. 常用操作速查

```bash
# 进入项目环境
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate

# 启动仪表盘
streamlit run app.py                    # 默认 8501 端口
streamlit run app.py --server.port 8502  # 指定端口

# 查看数据库
sqlite3 data/processed/jobs.db "SELECT source, city, COUNT(*) FROM jobs GROUP BY source, city;"

# 运行采集
python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python --limit 60

# 成都全量采集管道
python scripts/run_chengdu_pipeline.py

# 运行测试
python -m pytest tests/ -v

# Git 操作
git status
git add -A && git commit -m "..."
git push origin main
```

---

## 8. 扩展方向

| 状态 | 项目 | 说明 |
|------|------|------|
| ✅ | 修复 real_only 筛选 Bug | 按 source 过滤 mock 源 |
| ✅ | 修复 CITY_CODES 缺陷 | 已验证无重复 key |
| ✅ | 修正 USAGE.md 城市码 | 北京 030000→010000，补全10城 |
| ✅ | 清理脚本层重叠 | 7个脚本归档至 scripts/archived/ |
| ✅ | 重写 README | 反映当前架构和数据规模 |
| ✅ | 补核心模块 docstring | analytics/cleaning/database/skill_dict |
| ✅ | 扩展测试覆盖 | 6→40 个测试用例 |
| 🔜 | 多城市并行采集 | 10城 × ~1500条 = 15000条目标 |
| 🔜 | 统一 source 标记 | 标准化为枚举（合并 job51 / 51job_dom） |
| 🔜 | 清理非目标城市数据 | DB 中混入上海/远程办公等 |
| 🔜 | app.py 模块化拆分 | 拆为 pages/ 子目录 |
| 🔜 | print() → logging | 统一日志模块 |
| 🔜 | requirements.txt 补全 | 添加 jieba 等缺失依赖 |
| 📋 | PostgreSQL 替代 SQLite | 多并发写入 + 更大数据量 |
| 📋 | 定时采集 + 推送通知 | cron + Telegram/微信 |
| 📋 | NLP 岗位分类模型 | 替代简单子串匹配 |
| 📋 | 技能实体识别升级 | jieba + TF-IDF |
| 📋 | 接入 BOSS/智联登录态 | 需解决 Cookie/签名 |

---

## 9. 开发 Skill 体系

本项目配套的 Agent 技能栈（安装于 `~/.openclaw/skills/`）：

| 技能 | ⭐ | 用途 |
|------|-----|------|
| systematic-debugging | 226K | 系统性调试方法论 |
| coding-agent | 132K | Claude Code 代理 |
| python-pro | 40K | Python 最佳实践 |
| developing-with-streamlit | 204 | Streamlit 官方开发指南 |
| python-performance | 309 | Python 性能优化 |
| bug-review | 159 | 代码审查 |
| python-code-review | 63 | Python 专项审查 |
| code-review | - | 通用代码审查 |
| pytest-coverage | - | 测试覆盖 |
| git-commit-workflow | - | Git 提交工作流 |
| changelog-writer | - | 变更日志 |
| context7 | 57K | 实时文档注入 |

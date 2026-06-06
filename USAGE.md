# 城市岗位大数据分析平台 — 使用指南

> 面向城市就业市场的本地分析原型。  
> 支持真实岗位采集（51job）→ 归一化 → SQLite 入库 → Streamlit 仪表盘全链路。

---

## 1. 项目概览

### 1.1 能力矩阵

| 层级 | 能力 | 状态 |
|------|------|------|
| 采集 | 51job 真实岗位（xbrowser + API） | ✅ 已跑通 |
| 采集 | 企业官网（美团/字节/腾讯/阿里） | ❌ SPA 动态渲染，待解决 |
| 采集 | Mock 数据生成（4 个模拟源） | ✅ |
| 处理 | JSONL → CSV 归一化 | ✅ |
| 处理 | 薪资文本解析（10-15K / 8千-1.2万 / 200-300元/天） | ✅ |
| 处理 | 技能关键词抽取 | ✅ |
| 处理 | 去重（source_job_id + title + company） | ✅ |
| 存储 | SQLite 入库 | ✅ |
| 展示 | Streamlit 仪表盘（城市/区域/行业/技能/薪资分析） | ✅ |
| 质量 | 采集质量报告（缺失率/解析率/去重率） | ✅ |

### 1.2 数据全链路

```
                    ┌──────────────┐
                    │  采集层       │
                    │  run_spider   │
                    │  (xbrowser)   │
                    └──────┬───────┘
                           │ raw JSONL
                    ┌──────▼───────┐
                    │  归一化层     │
                    │  normalize    │
                    │  → CSV       │
                    └──────┬───────┘
                           │ CSV
                    ┌──────▼───────┐
                    │  入库层       │
                    │  build_db    │
                    │  → SQLite    │
                    └──────┬───────┘
                           │ DB
                    ┌──────▼───────┐
                    │  展示层       │
                    │  Streamlit   │
                    │  app.py      │
                    └──────────────┘
```

### 1.3 技术栈

- Python 3.9+
- 采集：httpx + xbrowser (Chrome CDP)
- 处理：pandas + jieba
- 存储：SQLite
- 展示：Streamlit + Plotly

---

## 2. 环境准备（首次）

```bash
# 进入项目
cd /Users/yangyuxiao/codes/job-market-analytics

# 创建虚拟环境
python3 -m venv .venv

# 安装依赖
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.1 依赖文件 `requirements.txt`

```
streamlit>=1.28
pandas>=2.0
plotly>=5.15
jieba>=0.42
httpx>=0.25
beautifulsoup4>=4.12
lxml>=4.9
```

### 2.2 xbrowser 前置条件（仅 51job 真实采集需要）

xbrowser 是真实浏览器自动化工具，已随 OpenClaw 安装。采集时会自动启动浏览器。

---

## 3. 使用方式

> ⚠️ **每次打开新终端窗口，第一步必须是：**
> ```bash
> cd /Users/yangyuxiao/codes/job-market-analytics
> source .venv/bin/activate
> ```
> 如果跳过这一步直接输命令，会报 `zsh: command not found: streamlit`。

### 3.1 方式一：Mock 数据快速体验（最快，无需网络）

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate

# 生成 500 条模拟数据（4 个数据源）
python scripts/generate_mock_jsonl.py

# JSONL → CSV
python scripts/jsonl_to_csv.py \
  --input data/raw/mock_jobs.jsonl \
  --output data/raw/mock_jobs.csv

# 入库
python scripts/build_database.py --csv data/raw/mock_jobs.csv

# 启动仪表盘
streamlit run app.py
```

或者一步到位：

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate
python scripts/run_pipeline.py
```

### 3.2 方式二：真实 51job 采集（需要浏览器运行）

这是核心功能，通过 xbrowser 控制真实浏览器，调用 51job 内部 API 获取岗位数据。

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate

# 单关键词采集成都 Python 岗位（最多 60 条）
python scripts/run_spider.py \
  --source job51_xbrowser \
  --city 成都 \
  --keywords Python \
  --limit 60

# 多关键词采集
python scripts/run_spider.py \
  --source job51_xbrowser \
  --city 成都 \
  --keywords Python Java 前端 数据分析 \
  --limit 200
```

**执行后自动完成：**
1. 打开浏览器 → 访问 51job → 建立会话
2. 调用 `we.51job.com/api/job/search-pc` API 分页抓取
3. 写入 `data/raw/YYYY-MM-DD/job51.jsonl`
4. JSONL → 归一化 → CSV
5. CSV → 质量报告
6. CSV → SQLite 入库

### 3.3 方式三：离线归一化已有 JSONL

如果你有原始 JSONL 文件，可以单独跑归一化：

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate

python scripts/normalize_raw_jobs.py \
  --input data/raw/2026-06-05/job51.jsonl \
  --output data/normalized/2026-06-05/job51.jsonl
```

输出质量报告示例：
```
归一化完成: 60 条 → data/normalized/...

==================================================
质量报告: 2026-06-05
==================================================
  raw: 60 | normalized: 60 | failed: 0
  duplicates: 0 | queries: 1
  duration: 0.0s

  字段缺失率:
    title:      0.0%
    company:    0.0%
    salary:     0.0%
    source_url: 0.0%
    district:   20.0%
  薪资解析成功率: 100.0%
```

### 3.4 方式四：查看仪表盘

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate
streamlit run app.py
```

浏览器访问 `http://localhost:8501`

仪表盘包含 5 个标签页：
- **城市概览**：岗位总数、公司数、行业分布、薪资分布
- **岗位分析**：按行业/学历/经验/薪资分组统计
- **区域分析**：各区岗位数量、平均薪资、热门行业
- **技能分析**：高频技能排行、技能薪资关联
- **岗位明细**：可搜索/筛选/排序的岗位表格

---

## 4. 城市代码映射（51job）

| 城市 | 代码 | 验证 |
|------|------|------|
| 全国 | 000000 | ✅ |
| 北京 | 030000 | 待验证 |
| 上海 | 020000 | ✅ |
| 广州 | 030200 | 待验证 |
| 深圳 | 040000 | 待验证 |
| 成都 | 090200 | ✅ |
| 杭州 | 080200 | 待验证 |

如需添加城市，在 `src/scraping/sources/job51_xbrowser.py` 的 `CITY_CODES` 字典中添加。

---

## 5. 项目文件结构

```
job-market-analytics/
├── app.py                       # Streamlit 仪表盘入口
├── requirements.txt             # Python 依赖
├── README.md                    # 项目说明
├── USAGE.md                     # ← 本文件
│
├── data/
│   ├── raw/                     # 原始数据
│   │   ├── YYYY-MM-DD/          # 按日期归档
│   │   │   └── job51.jsonl      # 51job 采集原始 JSONL
│   │   ├── mock_jobs.jsonl      # 模拟数据
│   │   └── chengdu_jobs_sample.csv
│   ├── normalized/              # 归一化后数据
│   └── processed/               # 处理结果
│       ├── jobs.db              # SQLite 数据库
│       └── reports/             # 质量报告 JSON
│
├── scripts/
│   ├── run_spider.py            # ★ 采集入口（核心）
│   ├── normalize_raw_jobs.py    # JSONL → CSV 归一化
│   ├── build_database.py        # CSV → SQLite
│   ├── run_pipeline.py          # 全链路编排（Mock 数据用）
│   ├── generate_mock_jsonl.py   # Mock 数据生成
│   └── jsonl_to_csv.py          # JSONL → CSV 转换
│
├── src/
│   ├── analytics.py             # Streamlit 数据源
│   ├── cleaning.py              # 薪资解析 / 技能抽取 / 去重
│   ├── database.py              # SQLite 导入
│   ├── sample_data.py           # 样例数据
│   ├── skill_dict.py            # 技能词典
│   └── scraping/                # 采集框架
│       ├── __init__.py
│       ├── models.py            # RawJob / NormalizedJob dataclass
│       ├── base.py              # RateLimiter / BaseCollector
│       ├── pipeline.py          # normalize_batch / write_csv
│       ├── quality.py           # 质量报告生成
│       └── sources/
│           ├── __init__.py      # 采集器注册
│           ├── job51.py         # 51job 静态采集器（备用）
│           ├── job51_xbrowser.py # ★ 51job xbrowser 采集器（主力）
│           └── company_site.py  # 企业官网采集器（未完成）
│
├── docs/
│   ├── scraping-plan.md
│   └── scraping-research-execution-plan.md
│
└── tests/
    └── test_cleaning.py
```

---

## 6. 常用命令速查

> ⚠️ 所有命令执行前，先激活虚拟环境：
> ```bash
> cd /Users/yangyuxiao/codes/job-market-analytics && source .venv/bin/activate
> ```

```bash
# 全链路 Mock 数据体验
python scripts/run_pipeline.py

# 真实采集（51job）
python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python --limit 60

# 多关键词 + 多城市
python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python Java 前端 --limit 200

# 只归一化
python scripts/normalize_raw_jobs.py --input data/raw/2026-06-05/job51.jsonl --output data/normalized/latest.jsonl

# 只入库
python scripts/build_database.py --csv data/normalized/latest.jsonl

# 查看数据
sqlite3 data/processed/jobs.db "SELECT source, COUNT(*) FROM jobs GROUP BY source;"

# 启动仪表盘
streamlit run app.py

# 数据库统计
sqlite3 data/processed/jobs.db "SELECT city, industry, COUNT(*) n FROM jobs GROUP BY city, industry ORDER BY n DESC LIMIT 10;"
```

---

## 7. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `zsh: command not found: streamlit` | 虚拟环境未激活 | `source .venv/bin/activate` |
| `zsh: command not found: python` | 虚拟环境未激活 | `source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'xxx'` | 依赖未安装或虚拟环境未激活 | `source .venv/bin/activate && pip install -r requirements.txt` |
| `xb eval failed` | 浏览器未运行 | 采集脚本会自动处理；手动确认 xbrowser status 正常 |
| `Permission denied` | 文件写入权限 | 确认 `data/` 目录可写 |
| `0 jobs collected` | API 返回空或 session 失效 | 重试，51job API 偶尔波动 |
| 仪表盘中文乱码 | 字体问题 | macOS 下 streamlit 默认支持中文，如需自定义见 `app.py` |
| `WAF/反爬拦截` | 请求过于频繁 | `rate_min` 和 `rate_max` 控制请求间隔 |

---

## 8. 扩展计划

- [ ] 企业官网 SPA 渲染支持（Playwright headful 模式）
- [ ] 多城市并行采集
- [ ] PostgreSQL 替代 SQLite（多并发写入）
- [ ] 定时任务 + Telegram/微信推送岗位摘要
- [ ] 岗位分类模型（NLP）
- [ ] 薪资趋势图（时间维度）

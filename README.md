# 📊 城市岗位大数据分析平台

> 多源岗位数据采集 → 智能分析 → 语义搜索 → 个性化推荐，一站式城市就业市场洞察平台。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red.svg)](https://streamlit.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://docker.com)

---

## 📌 当前状态

| 指标 | 数值 |
|------|------|
| 岗位总数 | **3,580** 条 |
| 覆盖城市 | **16** 个（成都 983、西安 361、武汉 317、重庆 311、南京 298、杭州 289、上海 213、深圳 172、北京 146、广州 137...） |
| Streamlit 标签页 | **17** 个 |
| FastAPI 端点 | **5** 个 REST API |
| ML 模型 | 薪资预测 (RandomForest)、语义搜索 (TF-IDF / Sentence-BERT) |
| 定时采集 | 51job 移动端 API 批量采集 |
| 部署 | Docker Compose (Streamlit + FastAPI + Nginx) |

---

## 🧩 功能矩阵

| # | 标签页 | 功能介绍 |
|---|--------|----------|
| 1 | 📈 概览 | KPI 卡片（岗位数/公司数/均薪/中位薪资）、热门岗位、薪资分布、技能云 |
| 2 | 🧠 观点 | 10 类行动级洞察：市场全貌、薪资三级跳、经验台阶、技能定价、行业地图、学历 ROI |
| 3 | 📊 趋势 | 薪资走势、技能热度变化、行业升温降温、市场综合信号 |
| 4 | 💰 薪资分析 | 经验-薪资/学历-薪资/规模-薪资 分组统计 + 箱线图 |
| 5 | 🌍 城市对比 | 多城市薪资对比表 + 柱状图，支持 16 城任意对比 |
| 6 | 📋 明细 | 可搜索/筛选/排序的岗位表格，支持 CSV 导出 |
| 7 | 📚 学习路线 | 基于高频技能的个性化学习路径推荐 |
| 8 | 🔗 技能网络 | 技能共现网络图，展示技能之间的关联关系 |
| 9 | 📈 薪资追踪 | 岗位薪资历史追踪，支持按城市/技能对比 |
| 10 | 🏢 雇主画像 | 公司维度分析：薪资竞争力、招聘规模、行业分布 |
| 11 | 🎯 智能推荐 | 技能匹配 + 薪资拟合 + 多维度加权推荐 |
| 12 | 🏅 竞争力 | 个人市场竞争力评估，薪资排位分析 |
| 13 | 🤖 LLM 增强 | JD 智能分析 Prompt 模板库 |
| 14 | 🧠 LLM 分析 | LLM 批量 JD 分析，NLP 增强洞察 |
| 15 | 🔮 薪资预测 | Machine Learning 薪资预测（RandomForest） |
| 16 | 🏙 成都vs全国 | 成都与全国市场对比分析 |
| 17 | 🎯 岗位推荐 | 成都+远程岗位智能推荐（4 维度评分：技能 40%/薪资 25%/成长 20%/公司 15%） |

---

## 🚀 快速开始

### 本地运行

```bash
# 1. 克隆项目
cd /path/to/job-market-analytics

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动仪表盘
streamlit run app.py
```

访问 `http://localhost:8501`

### Docker 一键部署

```bash
# 构建并启动所有服务
docker compose up -d

# 服务访问:
# Streamlit 仪表盘 → http://localhost:80
# FastAPI Swagger  → http://localhost:80/docs
# FastAPI API     → http://localhost:80/api/
# 健康检查        → http://localhost:80/health
```

---

## 🔍 数据采集

### 当前数据源

| 来源 | 数量 | 采集方式 |
|------|------|----------|
| 51job | 2,866 | xbrowser DOM 注入 + 移动端 API |
| job51 | 552 | 移动端 API 采集 |
| lagou | 74 | Mock / 历史数据 |
| boss | 46 | Mock / 历史数据 |
| liepin | 41 | Mock / 历史数据 |

### 采集命令

```bash
# 51job 移动端 API 采集
python scripts/run_spider.py --source mobile_51job --city 成都 --keywords Python --pages 10

# xbrowser 真实浏览器采集
python scripts/run_spider.py --source job51_xbrowser --city 成都 --keywords Python --limit 60

# 多城市并行
python scripts/run_chengdu_pipeline.py
```

> ⚠️ **注意**: Boss直聘、拉勾、猎聘均使用 WAF 保护，API 直接采集会返回 code=37
> "环境异常"。如需补充，建议通过 xbrowser skill 配合已登录浏览器采集。

---

## 📡 API 文档

启动 FastAPI 服务后，访问 `http://localhost:8502/docs` 查看 Swagger UI。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/benchmark` | POST | 岗位对标分析 |
| `/api/predict` | POST | 薪资预测 |
| `/api/search` | GET | 岗位语义搜索 |
| `/api/heatmap` | GET | 城市薪资热力图 |
| `/api/stats/chengdu` | GET | 成都市场概况 |

```bash
# 启动 FastAPI
uvicorn src.api.main:app --host 0.0.0.0 --port 8502

# 测试
curl http://localhost:8502/api/stats/chengdu
curl "http://localhost:8502/api/search?q=Python后端Docker&top=10"
```

---

## 🧠 语义搜索

支持自然语言查询，自动匹配技能语义相近的岗位：

```bash
# 语义搜索 CLI
python -m src.analytics.semantic_search --query "招Python后端，懂Docker和Kubernetes" --top 10

# 找相似岗位
python -m src.analytics.semantic_search --similar 1095 --top 5

# TF-IDF 备选方案
python -m src.analytics.tfidf_search --query "Python 后端 Docker" --top 10
```

> 语义搜索优先使用 `sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2)，
> 未安装时自动降级为 TF-IDF。

---

## 📋 周报生成

```bash
# 生成成都市场周报
python scripts/weekly_report.py --city 成都

# 发送邮件
python scripts/weekly_report.py --city 成都 --send-email your@email.com
```

---

## 📁 项目结构

```
job-market-analytics/
├── app.py                          # ★ Streamlit 仪表盘入口（17 标签页）
├── Dockerfile                      # Docker 镜像
├── docker-compose.yml              # 三服务编排 (Streamlit + FastAPI + Nginx)
├── nginx.conf                      # Nginx 反向代理配置
├── .dockerignore                   # Docker 构建排除
├── requirements.txt                # Python 依赖
├── README.md                       # ← 本文件
│
├── data/
│   ├── raw/                        # 原始采集数据（JSONL）
│   └── processed/
│       └── jobs.db                 # ★ SQLite 核心数据库
│
├── src/
│   ├── analytics/                  # 分析引擎
│   │   ├── recommender.py          # 技能匹配推荐引擎
│   │   ├── job_recommender.py      # ★ 成都+远程 4 维度推荐引擎
│   │   ├── semantic_search.py      # ★ 语义搜索 (Sentence-BERT + TF-IDF)
│   │   ├── tfidf_search.py         # TF-IDF 备选搜索
│   │   ├── salary_predictor.py     # ML 薪资预测
│   │   ├── salary_parser.py        # 薪资文本解析
│   │   ├── salary_tracker.py       # 薪资历史追踪
│   │   ├── competitiveness.py      # 竞争力评估
│   │   ├── companies.py            # 企业分析
│   │   ├── skill_network.py        # 技能网络
│   │   ├── skill_trend.py          # 技能趋势
│   │   ├── llm_analyzer.py         # LLM JD 分析
│   │   ├── llm_prompts.py          # LLM Prompt 模板
│   │   ├── jd_analyzer.py          # JD 结构化分析
│   │   └── position_benchmark.py   # 岗位对标
│   │
│   ├── api/                        # FastAPI 后端
│   │   ├── main.py                 # ★ API 入口（5 端点）
│   │   └── models.py               # Pydantic 数据模型
│   │
│   ├── ui/                         # Streamlit UI 组件
│   │   ├── overview.py             # 概览 + 筛选
│   │   ├── salary.py               # 薪资分析
│   │   ├── trends.py               # 趋势分析
│   │   ├── cities.py               # 城市对比
│   │   ├── skill_guide.py          # 学习路线
│   │   ├── skill_network.py        # 技能网络
│   │   ├── salary_trend.py         # 薪资追踪
│   │   ├── employers.py            # 雇主画像
│   │   ├── recommender.py          # 智能推荐
│   │   ├── job_recommender.py      # ★ 成都+远程推荐 UI
│   │   ├── competitiveness.py      # 竞争力
│   │   ├── llm_prompts.py          # LLM 增强
│   │   ├── llm_analysis.py         # LLM 分析
│   │   ├── salary_predictor.py     # 薪资预测
│   │   ├── chengdu_vs_national.py  # 成都vs全国
│   │   └── pdf_report.py           # PDF 报告导出
│   │
│   ├── scraping/                   # 采集框架
│   │   ├── base.py                 # RateLimiter / BaseCollector
│   │   ├── pipeline.py             # 归一化批处理
│   │   ├── quality.py              # 质量报告
│   │   ├── anti_crawl.py           # 反爬工具
│   │   └── sources/
│   │       ├── job51_xbrowser.py   # xbrowser DOM 注入采集
│   │       └── mobile_51job.py     # 移动端 API 采集
│   │
│   ├── database.py                 # SQLite 建表 + upsert
│   ├── cleaning.py                 # 薪资解析 + 技能抽取
│   ├── insights.py                 # 行动级观点引擎
│   ├── trends.py                   # 趋势分析
│   ├── nlp/                        # NLP 工具
│   └── skill_dict.py               # 技能关键词字典
│
├── scripts/
│   ├── run_spider.py               # 采集入口
│   ├── run_pipeline.py             # Mock 全链路
│   ├── weekly_report.py            # ★ 周报生成 + 邮件推送
│   ├── collect_boss.py             # Boss 直聘采集器
│   ├── collect_lagou.py            # 拉勾/猎聘采集器
│   ├── collect_near_zhonghe_v2.py  # 中和附近岗位
│   ├── diff_analysis.py            # 差异分析
│   ├── clean_salary_data.py        # 薪资数据清洗
│   ├── clean_publish_time.py       # 发布时间清洗
│   ├── dedup_sources.py            # 来源去重
│   ├── fix_salary_anomalies.py     # 薪资异常修复
│   ├── generate_report.py          # 全量报告生成
│   ├── doubao_auto.py              # 豆包自动分析
│   └── archived/                   # 归档脚本
│
├── reports/                        # 报告输出目录
├── tests/                          # 单元测试
├── docs/                           # 规划文档
└── logs/                           # 日志目录
```

---

## 🖼️ 仪表盘截图

<!-- 
  截图占位区 — 在 Streamlit 运行时截取
  建议包含以下页面:
  1. 概览标签页（KPI + 薪资分布）
  2. 成都vs全国（对比雷达图）
  3. 岗位推荐（评分列表 + 技能缺口）
  4. 智能推荐（技能匹配 + 薪资拟合）
  5. API Swagger 文档页
-->

| 功能 | 截图 |
|------|------|
| 📈 概览仪表盘 | ![概览](docs/screenshots/overview.png) |
| 🏙 成都vs全国 | ![成都vs全国](docs/screenshots/chengdu_vs_national.png) |
| 🎯 岗位推荐 | ![岗位推荐](docs/screenshots/job_recommender.png) |
| 🔍 语义搜索 | ![语义搜索](docs/screenshots/semantic_search.png) |
| 📡 API Swagger | ![API](docs/screenshots/api_swagger.png) |
| 📊 周报 | ![周报](docs/screenshots/weekly_report.png) |

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 采集 | xbrowser (Chrome CDP) / httpx / requests | 浏览器自动化 + HTTP 采集 |
| 处理 | pandas / numpy / jieba / scikit-learn | 数据清洗 + NLP + ML |
| 存储 | SQLite | 轻量级嵌入式数据库 |
| 后端 | FastAPI + Uvicorn | REST API 服务 |
| 前端 | Streamlit + Plotly | 交互式仪表盘 |
| 搜索 | Sentence-BERT / TF-IDF | 语义搜索 |
| 部署 | Docker + Docker Compose + Nginx | 容器化部署 |

---

## 🔧 扩展方向

- [x] 17 标签页仪表盘
- [x] 5 条 REST API
- [x] ML 薪资预测
- [x] 语义搜索
- [x] 成都+远程岗位推荐引擎
- [x] Docker + Nginx 部署
- [x] 周报自动生成
- [ ] PostgreSQL 替代 SQLite（多并发写入）
- [ ] 定时采集 + Cron 调度
- [ ] Telegram/微信 推送通知
- [ ] React/Vue 前端替代 Streamlit
- [ ] Boss/拉勾 xbrowser 登录态采集

---

## ⚖️ 合规说明

51job 采集基于 xbrowser 真实浏览器自动化——与非登录态的公开搜索页交互，不绕过登录、验证码或付费墙。接入其他招聘平台前，请确认目标网站的用户协议和 robots.txt。

---

*Made with ❤️ in Chengdu · Python 全栈工程师*

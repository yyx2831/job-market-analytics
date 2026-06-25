# 📊 城市岗位大数据分析平台 · TODO & Roadmap

> 最后更新: 2026-06-21 22:07
> 版本: v1.4 (15 标签页仪表盘 + ML 预测 + 实时采集)

---

## 📈 当前状态

| 指标 | 值 |
|------|-----|
| 总岗位数 | **3,529** 条 |
| 覆盖城市 | 10+ 个 |
| 数据来源 | 51job / Boss / 拉勾 / 猎聘 |
| 仪表盘 | **15 个标签页** |
| 测试覆盖 | 40/40 ✅ |
| 定时采集 | 每日 9:00 (mobile_51job × 10 词) |
| 数据质量 | salary_months 97%修复, publish_time 100%清洗, 0 条重复 |

---

## ✅ 本次已完成 (2026-06-21 19:49~22:07)

- [x] ① 薪资数据修复 — `salary_months` 822 条、`salary_avg` 818 条、`salary_unit` 1960 条
- [x] ② `publish_time` 清洗 — 1,965 条脏值回填 `crawl_time`
- [x] ③ 来源去重 — 删除 557 条重复 (同 source + 跨 source)
- [x] ④ 全量关键词采集 — 100 条新增 (mobile_51job × 10 词)
- [x] ⑤ 每日定时采集 — cron 每天 9:00 自动执行
- [x] ⑦⑧ 技能网络 / 薪资追踪 — 确认已集成 (tab 7,8)
- [x] ⑨ 薪资预测模型 — RandomForest R²=0.15 + Streamlit UI (tab 15)
- [x] ⑩ 全量数据报告 — `reports/full_report_20260621.md`

### 新增/修改文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `scripts/clean_salary_data.py` | 5.3KB | 薪资三修复脚本 |
| `scripts/clean_publish_time.py` | 2.9KB | publish_time 清洗脚本 |
| `scripts/dedup_sources.py` | 5.5KB | 来源去重脚本 |
| `scripts/generate_report.py` | 9.2KB | 全量 Markdown 报告生成器 |
| `src/analytics/salary_predictor.py` | 11.5KB | ML 薪资预测引擎 |
| `src/ui/salary_predictor.py` | 6.2KB | 预测 UI 标签页 |
| `src/ui/__init__.py` | — | 新增 render_salary_predictor |
| `app.py` | — | 新增第 15 个标签页 |
| `reports/full_report_20260621.md` | 10KB | 综合数据报告 |

---

## 🔜 待办 (优先级排序)

### 🔴 高优先级

- [ ] **⑭ README 更新** — 反映 15 标签页 + ML + 采集 cron 的新能力
- [ ] **数据质量 v2** — TOP 高薪异常值过滤 (¥550K 等明显错误)
- [ ] **采集稳健性** — 移动端 51job 反爬应对 (限速、重试、断点续传)

### 🟡 中优先级

- [ ] **⑪ 全球站点扩展** — LinkedIn / Indeed / Glassdoor (需评估可行性)
- [ ] **⑫ API 服务化** — FastAPI 封装预测 + 查询接口
- [ ] **⑬ 告警推送** — 薪资异动 / 新岗位推送 (Webhook/Email)
- [ ] **高级 ML** — skill embedding + job matching 语义搜索
- [ ] **采集扩展** — 猎聘 / Boss 直聘移动端采集

### 🟢 低优先级

- [ ] **⑭ ⑥ 低优先级数据源修复** — Boss/拉勾采集稳定化 (现仅有 46+74 条)
- [ ] **Nginx + Docker 部署** — 生产环境容器化
- [ ] **Grafana 监控面板** — 替代 Streamlit 的生产级方案

---

## 📂 关键文件索引

```
/Users/yangyuxiao/codes/job-market-analytics/
├── app.py                          # Streamlit 仪表盘入口 (15 标签页)
├── data/processed/jobs.db          # SQLite 主数据库 (3,529 条)
├── data/processed/salary_model.pkl # 薪资预测模型
├── src/
│   ├── analytics/
│   │   ├── salary_predictor.py     # ML 薪资预测
│   │   ├── llm_analyzer.py         # LLM 规则引擎
│   │   ├── jd_analyzer.py          # JD 深度 NLP
│   │   ├── skill_network.py        # 技能共现图分析
│   │   ├── competitiveness.py      # 竞争力五维评分
│   │   ├── salary_tracker.py       # 薪资历史追踪
│   │   └── purchasing_power.py     # 购买力分析
│   ├── ui/
│   │   ├── salary_predictor.py     # ★NEW 薪资预测 UI
│   │   ├── employers.py            # 雇主画像
│   │   ├── recommender.py          # 智能推荐
│   │   ├── competitiveness.py      # 竞争力计算
│   │   ├── llm_prompts.py          # LLM Prompt 生成
│   │   ├── llm_analysis.py         # LLM 分析结果
│   │   ├── skill_network.py        # 技能网络图
│   │   └── salary_trend.py         # 薪资趋势
│   ├── nlp/
│   │   ├── skill_extractor.py      # jieba + TF-IDF
│   │   └── job_classifier.py       # 7 类关键词分类
│   └── scraping/sources/
│       └── mobile_51job.py         # 移动端 51job 采集器
├── scripts/
│   ├── run_spider.py               # 采集入口
│   ├── clean_salary_data.py        # ★NEW
│   ├── clean_publish_time.py       # ★NEW
│   ├── dedup_sources.py            # ★NEW
│   └── generate_report.py          # ★NEW
├── reports/
│   └── full_report_20260621.md     # ★NEW
└── tests/                          # 40/40 ✅
```

---

## 🚀 快速命令

```bash
# 启动仪表盘
cd /Users/yangyuxiao/codes/job-market-analytics
source .venv/bin/activate
streamlit run app.py

# 手动采集 (mobile_51job × 10 词)
python3 scripts/run_spider.py --source job51_mobile --all-keywords --limit-per-kw 30

# 生成全量报告
python3 scripts/generate_report.py > reports/full_report_$(date +%Y%m%d).md

# 数据清洗
python3 scripts/clean_salary_data.py --apply
python3 scripts/clean_publish_time.py --apply
python3 scripts/dedup_sources.py --apply

# 运行测试
python3 -m pytest tests/ -v

# 查看 cron 状态
openclaw cron list
```

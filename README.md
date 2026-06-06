# 城市岗位大数据分析平台

一个面向城市就业市场的本地分析原型。当前版本以成都岗位样例数据为基础，支持 CSV 导入、薪资解析、技能抽取、去重、SQLite 入库和 Streamlit 网页仪表盘。

## 功能

- 生成成都岗位样例数据。
- 从 CSV 导入岗位数据到 SQLite。
- 解析 `10-15K`、`15-25K·13薪`、`8千-1.2万`、`200-300元/天` 等薪资文本。
- 抽取岗位描述和技能标签中的技能关键词。
- 展示城市概览、岗位分析、区域分析、技能分析和岗位明细。
- 支持城市、区域、行业、学历、经验和关键词筛选。

## 技术选型

- Python 3.9+
- Streamlit
- pandas
- Plotly
- SQLite

## 快速开始

```bash
cd /Users/yangyuxiao/codes/job-market-analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_data.py
python scripts/build_database.py
streamlit run app.py
```

启动后浏览器访问 Streamlit 输出的本地地址，通常是：

```text
http://localhost:8501
```

## 数据导入

默认样例数据位于：

```text
data/raw/chengdu_jobs_sample.csv
```

你也可以准备自己的 CSV，字段建议包含：

| 字段 | 说明 |
| --- | --- |
| source_job_id | 来源岗位 ID |
| title | 岗位名称 |
| company_name | 公司名称 |
| salary_text | 薪资文本 |
| city | 城市 |
| district | 区域 |
| experience | 经验 |
| education | 学历 |
| industry | 行业 |
| company_size | 公司规模 |
| financing_stage | 融资阶段 |
| skills | 技能，逗号分隔 |
| description | 岗位描述 |
| source | 数据来源 |
| source_url | 原始链接 |
| publish_time | 发布时间 |

导入命令：

```bash
python scripts/build_database.py --csv data/raw/chengdu_jobs_sample.csv
```

## 项目结构

```text
job-market-analytics/
  app.py
  requirements.txt
  README.md
  data/
    raw/
    processed/
  scripts/
    generate_sample_data.py
    build_database.py
  src/
    analytics.py
    cleaning.py
    database.py
    sample_data.py
    skill_dict.py
  tests/
    test_cleaning.py
```

## 后续扩展

- 接入授权招聘数据源或企业官网招聘页。
- 增加 FastAPI 后端，前端迁移到 React。
- 引入 PostgreSQL，支持多城市和定时采集。
- 增加岗位分类模型和更准确的技能实体识别。
- 增加时间趋势、技能共现网络和区域地图。

## 合规说明

当前项目不内置绕过登录、验证码、付费墙或反爬机制的采集代码。接入真实招聘平台前，请先确认目标网站的用户协议、robots.txt 和数据授权边界。

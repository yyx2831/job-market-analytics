"""生成 mock raw JSONL，模拟真实爬虫产出的原始数据格式。"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DISTRICTS = ["高新区", "武侯区", "锦江区", "青羊区", "成华区", "金牛区", "双流区", "天府新区"]
INDUSTRIES = ["互联网", "软件服务", "电子商务", "金融科技", "教育培训", "智能制造", "企业服务"]
EDUCATIONS = ["不限", "大专", "本科", "硕士"]
EXPERIENCES = ["不限", "1-3年", "3-5年", "5-10年"]
COMPANY_SIZES = ["20-99人", "100-499人", "500-999人", "1000-9999人"]
FINANCING = ["未融资", "天使轮", "A轮", "B轮", "C轮及以上", "上市公司"]
SOURCES = ["boss", "lagou", "51job", "liepin"]

JOB_TEMPLATES = [
    ("Python 后端工程师", ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"], "负责业务后端服务开发，参与系统架构设计，使用 Python、FastAPI、PostgreSQL、Redis、Docker 构建稳定高效的微服务接口。", (12, 24)),
    ("Java 开发工程师", ["Java", "Spring Boot", "MySQL", "Redis", "Linux"], "负责 Java 后端系统开发与维护，熟悉 Spring Boot、MySQL、Redis 和 Linux 环境部署，有分布式项目经验优先。", (10, 22)),
    ("前端开发工程师", ["JavaScript", "TypeScript", "React", "Vue"], "负责 Web 前端开发，参与组件库建设和性能优化，熟悉 React/Vue 技术栈，有 TypeScript 项目经验。", (9, 20)),
    ("数据分析师", ["SQL", "Python", "Excel", "Tableau", "数据分析", "数据可视化"], "负责业务数据分析、指标体系建设和数据看板搭建，熟练 SQL、Excel 和 Python，能独立完成分析报告。", (8, 18)),
    ("产品经理", ["需求分析", "原型设计", "项目管理", "Figma"], "负责需求分析、产品规划和项目推进，熟悉原型设计工具和敏捷开发流程，具备跨团队沟通协调能力。", (10, 22)),
    ("测试工程师", ["Python", "SQL", "Linux"], "负责接口测试、自动化测试用例编写和质量保障，熟悉 Python 脚本和 SQL 查询，有 CI/CD 集成经验优先。", (7, 15)),
    ("运维工程师", ["Linux", "Docker", "Kubernetes", "Redis", "MySQL"], "负责系统部署上线、监控告警和故障排查，熟悉 Linux、Docker 和 Kubernetes 容器编排。", (9, 18)),
    ("电商运营", ["电商运营", "Excel", "数据分析", "用户增长"], "负责店铺运营、活动策划和数据复盘，具备天猫/京东等电商平台运营经验，善于数据驱动增长。", (6, 14)),
    ("UI 设计师", ["Figma", "Photoshop", "原型设计"], "负责产品界面设计、设计规范制定和交互细节优化，熟悉 Figma 和 PS，对用户体验有较高追求。", (7, 16)),
    ("销售经理", ["销售", "客户沟通", "渠道拓展"], "负责客户开发、商务谈判和渠道拓展，制定销售策略并完成业绩指标，具备较强的客户沟通能力。", (6, 20)),
    ("算法工程师", ["Python", "机器学习", "深度学习", "C++"], "负责推荐/搜索/广告等算法模型开发与优化，熟悉主流深度学习框架，有实际业务落地经验。", (18, 35)),
    ("数据开发工程师", ["SQL", "Python", "Spark", "Hadoop", "数据仓库"], "负责数据仓库建设和 ETL 流程开发，熟悉 Spark/Hive/Hadoop 生态，有海量数据处理经验优先。", (12, 25)),
]


def _random_company(index: int) -> str:
    prefixes = ["云智", "星河", "锦城", "天府", "蓉创", "鼎新", "博思", "宏图"]
    suffixes = ["科技", "信息", "数据", "软件"]
    return f"成都{random.choice(prefixes)}{random.choice(suffixes)}有限公司"


def _build_salary_text(low: int, high: int) -> str:
    months = random.choice([12, 12, 12, 13, 14])
    base = f"{low}-{high}K"
    return base if months == 12 else f"{base}·{months}薪"


def generate_mock_jsonl(path: Path, rows: int = 360) -> None:
    """生成 mock raw JSONL 文件，模拟多个数据源爬虫产出的原始数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    random.seed(42)
    today = datetime.now().date()
    crawl_base = datetime.now().replace(microsecond=0)

    with path.open("w", encoding="utf-8") as f:
        for index in range(rows):
            title, skills, desc, salary_range = random.choice(JOB_TEMPLATES)
            low = max(4, salary_range[0] + random.randint(-2, 2))
            high = max(low + 2, salary_range[1] + random.randint(-3, 4))
            source = random.choice(SOURCES)
            district = random.choice(DISTRICTS)
            publish_time = today - timedelta(days=random.randint(0, 89))
            crawl_time = crawl_base - timedelta(hours=random.randint(0, 72))

            # 模拟不同数据源的原始字段风格差异
            record = {
                "source": source,
                "source_job_id": f"{source}-{index + 1:05d}",
                "raw_title": title,
                "raw_company": _random_company(index),
                "raw_salary": _build_salary_text(low, high),
                "raw_location": f"成都·{district}",
                "raw_experience": random.choice(EXPERIENCES),
                "raw_education": random.choice(EDUCATIONS),
                "raw_industry": random.choice(INDUSTRIES),
                "raw_company_size": random.choice(COMPANY_SIZES),
                "raw_financing": random.choice(FINANCING),
                "raw_skills": skills,
                "raw_description": desc,
                "raw_url": f"https://{source}.example.invalid/jobs/{index + 1}",
                "raw_publish_time": publish_time.isoformat(),
                "crawl_time": crawl_time.isoformat(sep=" "),
                "page": random.randint(1, 5),
                "rank": random.randint(1, 20),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "data" / "raw" / "mock_jobs.jsonl"
    generate_mock_jsonl(output, rows=500)
    print(f"Generated {500} mock JSONL records → {output}")

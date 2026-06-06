from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


DISTRICTS = ["高新区", "武侯区", "锦江区", "青羊区", "成华区", "金牛区", "双流区", "天府新区"]
INDUSTRIES = ["互联网", "软件服务", "电子商务", "金融科技", "教育培训", "智能制造", "企业服务"]
EDUCATIONS = ["不限", "大专", "本科", "硕士"]
EXPERIENCES = ["不限", "1-3年", "3-5年", "5-10年"]
COMPANY_SIZES = ["20-99人", "100-499人", "500-999人", "1000-9999人"]
FINANCING = ["未融资", "天使轮", "A轮", "B轮", "C轮及以上", "上市公司"]

JOB_TEMPLATES = [
    ("Python 后端工程师", "Python,FastAPI,PostgreSQL,Redis,Docker", "负责业务后端服务开发，使用 Python、FastAPI、SQL、Redis 构建稳定接口。", (12, 24)),
    ("Java 开发工程师", "Java,Spring Boot,MySQL,Redis,Linux", "负责 Java 后端系统开发，熟悉 Spring Boot、MySQL、Redis 和 Linux。", (10, 22)),
    ("前端开发工程师", "JavaScript,TypeScript,React,Vue", "负责 Web 前端开发，熟悉 React 或 Vue，有 TypeScript 项目经验。", (9, 20)),
    ("数据分析师", "SQL,Python,Excel,Tableau,数据分析,数据可视化", "负责业务数据分析、指标体系建设和数据可视化，熟练 SQL、Excel 和 Python。", (8, 18)),
    ("产品经理", "需求分析,原型设计,项目管理,Figma", "负责需求分析、产品规划和项目推进，熟悉原型设计和跨团队沟通。", (10, 22)),
    ("测试工程师", "Python,SQL,Linux", "负责接口测试、自动化测试和质量保障，熟悉 Python 脚本和 SQL。", (7, 15)),
    ("运维工程师", "Linux,Docker,Kubernetes,Redis,MySQL", "负责系统部署、监控和故障处理，熟悉 Linux、Docker 和 Kubernetes。", (9, 18)),
    ("电商运营", "电商运营,Excel,数据分析,用户增长", "负责店铺运营、活动策划和数据复盘，具备电商平台运营经验。", (6, 14)),
    ("UI 设计师", "Figma,Photoshop,原型设计", "负责产品界面设计、设计规范维护和交互细节优化，熟悉 Figma。", (7, 16)),
    ("销售经理", "销售,客户沟通,渠道拓展", "负责客户开发、商务谈判和渠道拓展，具备较强客户沟通能力。", (6, 20)),
]


def generate_sample_csv(path: Path, rows: int = 360) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    random.seed(42)
    today = datetime.now().date()

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "source_job_id",
                "title",
                "company_name",
                "salary_text",
                "city",
                "district",
                "experience",
                "education",
                "industry",
                "company_size",
                "financing_stage",
                "skills",
                "description",
                "source",
                "source_url",
                "publish_time",
            ],
        )
        writer.writeheader()
        for index in range(rows):
            title, skills, description, salary_range = random.choice(JOB_TEMPLATES)
            low = max(4, salary_range[0] + random.randint(-2, 2))
            high = max(low + 2, salary_range[1] + random.randint(-3, 4))
            months = random.choice([12, 12, 13, 14])
            salary_text = f"{low}-{high}K" if months == 12 else f"{low}-{high}K·{months}薪"
            publish_time = today - timedelta(days=random.randint(0, 89))
            district = random.choice(DISTRICTS)
            company_no = random.randint(1, 80)
            writer.writerow(
                {
                    "source_job_id": f"sample-{index + 1:04d}",
                    "title": title,
                    "company_name": f"成都{random.choice(['云智', '星河', '锦城', '天府', '蓉创'])}科技有限公司{company_no}",
                    "salary_text": salary_text,
                    "city": "成都",
                    "district": district,
                    "experience": random.choice(EXPERIENCES),
                    "education": random.choice(EDUCATIONS),
                    "industry": random.choice(INDUSTRIES),
                    "company_size": random.choice(COMPANY_SIZES),
                    "financing_stage": random.choice(FINANCING),
                    "skills": skills,
                    "description": description,
                    "source": "sample",
                    "source_url": f"https://example.invalid/jobs/{index + 1}",
                    "publish_time": publish_time.isoformat(),
                }
            )


"""insights.py 测试：观点生成引擎。"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.insights import Insight, generate_insights, compare_cities


def _make_jobs() -> pd.DataFrame:
    """构造测试用 DataFrame，模拟真实数据库字段。"""
    return pd.DataFrame([
        {
            "title": "Python 后端工程师",
            "company_name": "Tech A",
            "city": "成都",
            "salary_avg": 15000,
            "salary_text": "10-20K",
            "experience": "3-5年",
            "education": "本科",
            "industry": "互联网",
            "company_size": "100-499人",
            "skills": "Python,FastAPI,PostgreSQL,Redis,Docker",
            "source": "51job",
        },
        {
            "title": "Java 开发工程师",
            "company_name": "Tech A",
            "city": "成都",
            "salary_avg": 18000,
            "salary_text": "15-20K",
            "experience": "3-5年",
            "education": "本科",
            "industry": "互联网",
            "company_size": "100-499人",
            "skills": "Java,Spring Boot,MySQL,Redis,Linux",
            "source": "51job",
        },
        {
            "title": "前端工程师",
            "company_name": "Tech B",
            "city": "成都",
            "salary_avg": 12000,
            "salary_text": "8-15K",
            "experience": "1-3年",
            "education": "大专",
            "industry": "软件服务",
            "company_size": "20-99人",
            "skills": "JavaScript,React,Vue,TypeScript",
            "source": "51job",
        },
        {
            "title": "数据分析师",
            "company_name": "Tech C",
            "city": "成都",
            "salary_avg": 13000,
            "salary_text": "10-15K",
            "experience": "1-3年",
            "education": "本科",
            "industry": "互联网",
            "company_size": "100-499人",
            "skills": "Python,SQL,Excel,数据分析,数据可视化",
            "source": "51job",
        },
        {
            "title": "资深架构师",
            "company_name": "Tech D",
            "city": "成都",
            "salary_avg": 35000,
            "salary_text": "25-40K",
            "experience": "5-10年",
            "education": "硕士",
            "industry": "互联网",
            "company_size": "1000-9999人",
            "skills": "Java,Go,Kubernetes,Docker,Linux,Spring Boot",
            "source": "51job",
        },
    ])


class TestGenerateInsights:
    """测试观点生成。"""

    def test_non_empty_result(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        assert len(insights) > 0

    def test_insight_structure(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        for ins in insights:
            assert isinstance(ins, Insight)
            assert ins.title != ""
            assert ins.body != ""
            assert ins.level in ("highlight", "warning", "info")

    def test_market_overview_exists(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        titles = [i.title for i in insights]
        assert any("市场全貌" in t for t in titles)

    def test_salary_tiers_exists(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        titles = [i.title for i in insights]
        assert any("薪资三级跳" in t for t in titles)

    def test_action_items_exists(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        titles = [i.title for i in insights]
        assert any("行动清单" in t for t in titles)

    def test_skill_pricing(self) -> None:
        jobs = _make_jobs()
        insights = generate_insights(jobs)
        skill_titles = [i.title for i in insights if "技能" in i.title]
        assert len(skill_titles) >= 1  # should have skill-related insights

    def test_empty_data_returns_warning(self) -> None:
        empty = pd.DataFrame(columns=["title", "company_name", "salary_avg"])
        insights = generate_insights(empty)
        assert len(insights) == 1
        assert insights[0].level == "warning"

    def test_no_salary_data_returns_warning(self) -> None:
        no_salary = pd.DataFrame([{
            "title": "X", "company_name": "Y", "city": "成都",
            "salary_avg": None, "salary_text": "面议",
        }])
        insights = generate_insights(no_salary)
        assert len(insights) == 1
        assert insights[0].level == "warning"


class TestCompareCities:
    """测试城市对比分析。"""

    def test_multi_city_comparison(self) -> None:
        jobs = pd.DataFrame([
            {"city": "成都", "salary_avg": 15000, "title": "job1", "company_name": "A"},
            {"city": "成都", "salary_avg": 18000, "title": "job2", "company_name": "B"},
            {"city": "成都", "salary_avg": 12000, "title": "job3", "company_name": "C"},
            {"city": "成都", "salary_avg": 16000, "title": "job4", "company_name": "D"},
            {"city": "成都", "salary_avg": 20000, "title": "job5", "company_name": "E"},
            {"city": "成都", "salary_avg": 14000, "title": "job6", "company_name": "F"},
            {"city": "成都", "salary_avg": 17000, "title": "job7", "company_name": "G"},
            {"city": "成都", "salary_avg": 19000, "title": "job8", "company_name": "H"},
            {"city": "成都", "salary_avg": 13000, "title": "job9", "company_name": "I"},
            {"city": "成都", "salary_avg": 15000, "title": "job10", "company_name": "J"},
            {"city": "北京", "salary_avg": 25000, "title": "bj1", "company_name": "X"},
            {"city": "北京", "salary_avg": 28000, "title": "bj2", "company_name": "Y"},
            {"city": "北京", "salary_avg": 22000, "title": "bj3", "company_name": "Z"},
            {"city": "北京", "salary_avg": 30000, "title": "bj4", "company_name": "W"},
            {"city": "北京", "salary_avg": 26000, "title": "bj5", "company_name": "V"},
            {"city": "北京", "salary_avg": 24000, "title": "bj6", "company_name": "U"},
            {"city": "北京", "salary_avg": 27000, "title": "bj7", "company_name": "T"},
            {"city": "北京", "salary_avg": 29000, "title": "bj8", "company_name": "S"},
            {"city": "北京", "salary_avg": 23000, "title": "bj9", "company_name": "R"},
            {"city": "北京", "salary_avg": 21000, "title": "bj10", "company_name": "Q"},
        ])
        results = compare_cities(jobs, ["成都", "北京"])
        assert len(results) > 0
        assert any("平均薪资" in r.title for r in results)

    def test_insufficient_data(self) -> None:
        jobs = pd.DataFrame([
            {"city": "成都", "salary_avg": 15000, "title": "job1", "company_name": "A"},
            {"city": "北京", "salary_avg": 20000, "title": "bj1", "company_name": "B"},
        ])
        results = compare_cities(jobs, ["成都", "北京"])
        assert len(results) == 1
        assert results[0].level == "warning"

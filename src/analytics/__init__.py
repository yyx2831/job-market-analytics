"""仪表盘数据层：从 SQLite 加载岗位/技能数据，提供筛选与 KPI 计算。

被 app.py (Streamlit 仪表盘) 调用，负责：
- 从 jobs.db 加载岗位和技能关联数据
- 多维度筛选（城市/区域/行业/学历/经验/关键词）
- 计算 KPI 指标（岗位数/公司数/均薪/中位薪资）
"""

from __future__ import annotations

import sqlite3

import pandas as pd


def load_jobs(conn: sqlite3.Connection) -> pd.DataFrame:
    """从 SQLite 加载全部岗位，按 publish_time 倒序。"""
    return pd.read_sql_query("SELECT * FROM jobs ORDER BY publish_time DESC", conn)


def load_skills(conn: sqlite3.Connection) -> pd.DataFrame:
    """加载岗位-技能关联数据（job_skills JOIN jobs）。"""
    return pd.read_sql_query(
        """
        SELECT js.skill, j.id AS job_id, j.salary_avg, j.title, j.district, j.industry, j.publish_time
        FROM job_skills js
        JOIN jobs j ON j.id = js.job_id
        """,
        conn,
    )


def filter_jobs(
    jobs: pd.DataFrame,
    city: str | None = None,
    districts: list[str] | None = None,
    industries: list[str] | None = None,
    educations: list[str] | None = None,
    experiences: list[str] | None = None,
    keyword: str | None = None,
) -> pd.DataFrame:
    """按城市/区域/行业/学历/经验/关键词筛选岗位 DataFrame。

    注意：此函数已不再被 app.py 使用（app.py 内置了自己的 apply_filters），
    保留以供外部调用或测试。
    """
    result = jobs.copy()
    if city and city != "全部":
        result = result[result["city"] == city]
    if districts:
        result = result[result["district"].isin(districts)]
    if industries:
        result = result[result["industry"].isin(industries)]
    if educations:
        result = result[result["education"].isin(educations)]
    if experiences:
        result = result[result["experience"].isin(experiences)]
    if keyword:
        pattern = keyword.strip()
        if pattern:
            mask = (
                result["title"].str.contains(pattern, case=False, na=False)
                | result["company_name"].str.contains(pattern, case=False, na=False)
                | result["description"].str.contains(pattern, case=False, na=False)
                | result["skills"].str.contains(pattern, case=False, na=False, regex=False)
            )
            result = result[mask]
    return result


from .position_benchmark import PositionBenchmark, BenchmarkResult, load_jobs as load_benchmark_jobs


def overview_metrics(jobs: pd.DataFrame) -> dict[str, float | int]:
    """计算仪表盘 KPI：岗位总数、均薪、中位薪资、公司数。"""
    salary = jobs["salary_avg"].dropna()
    return {
        "total_jobs": int(len(jobs)),
        "avg_salary": float(salary.mean()) if not salary.empty else 0.0,
        "median_salary": float(salary.median()) if not salary.empty else 0.0,
        "company_count": int(jobs["company_name"].nunique()) if not jobs.empty else 0,
    }

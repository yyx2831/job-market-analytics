from __future__ import annotations

import sqlite3

import pandas as pd


def load_jobs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM jobs ORDER BY publish_time DESC", conn)


def load_skills(conn: sqlite3.Connection) -> pd.DataFrame:
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
                | result["skills"].str.contains(pattern, case=False, na=False)
            )
            result = result[mask]
    return result


def overview_metrics(jobs: pd.DataFrame) -> dict[str, float | int]:
    salary = jobs["salary_avg"].dropna()
    return {
        "total_jobs": int(len(jobs)),
        "avg_salary": float(salary.mean()) if not salary.empty else 0.0,
        "median_salary": float(salary.median()) if not salary.empty else 0.0,
        "company_count": int(jobs["company_name"].nunique()) if not jobs.empty else 0,
    }

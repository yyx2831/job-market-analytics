"""公司画像分析 — 雇主维度：规模分布、融资阶段、热门雇主排名。"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd


def company_stats(jobs: pd.DataFrame) -> pd.DataFrame:
    """按公司汇总关键指标。

    Returns:
        DataFrame: company, 岗位数, 平均薪资, 行业, 规模, 融资阶段
    """
    if "company_name" not in jobs.columns:
        return pd.DataFrame()

    agg_dict = {"id": "count"}
    if "salary_avg" in jobs.columns:
        agg_dict["salary_avg"] = "mean"
    if "industry" in jobs.columns:
        agg_dict["industry"] = "first"
    if "company_size" in jobs.columns:
        agg_dict["company_size"] = "first"
    if "financing_stage" in jobs.columns:
        agg_dict["financing_stage"] = "first"

    stats = jobs.groupby("company_name").agg(**{
        "岗位数": ("id", "count"),
        "平均薪资": ("salary_avg", "mean") if "salary_avg" in jobs.columns else ("id", "count"),
        "行业": ("industry", "first") if "industry" in jobs.columns else ("company_name", "first"),
        "规模": ("company_size", "first") if "company_size" in jobs.columns else ("company_name", "first"),
        "融资": ("financing_stage", "first") if "financing_stage" in jobs.columns else ("company_name", "first"),
    }).reset_index()

    if "平均薪资" in stats.columns:
        stats["平均薪资"] = stats["平均薪资"].round(1)
    stats = stats.sort_values("岗位数", ascending=False)

    # 清理第一列名
    return stats.rename(columns={"company_name": "公司"})


def size_distribution(jobs: pd.DataFrame) -> pd.DataFrame:
    """公司规模分布统计。

    Returns:
        DataFrame: 规模, 岗位数, 公司数, 平均薪资
    """
    if "company_size" not in jobs.columns:
        return pd.DataFrame()

    size_stats = jobs.groupby("company_size").agg(
        岗位数=("id", "count"),
        公司数=("company_name", "nunique"),
        平均薪资=("salary_avg", "mean"),
    ).reset_index()
    if "平均薪资" in size_stats.columns:
        size_stats["平均薪资"] = size_stats["平均薪资"].round(1)

    # 按规模排序
    size_order = ["少于50人", "50-150人", "150-500人", "500-1000人", "1000-5000人", "5000-10000人", "10000人以上"]
    size_stats["_order"] = size_stats["company_size"].apply(
        lambda x: size_order.index(x) if x in size_order else 99
    )
    return size_stats.sort_values("_order").drop(columns=["_order"])


def financing_distribution(jobs: pd.DataFrame) -> pd.DataFrame:
    """融资阶段分布统计。

    Returns:
        DataFrame: 融资阶段, 岗位数, 公司数
    """
    if "financing_stage" not in jobs.columns:
        return pd.DataFrame()

    fin_stats = jobs.groupby("financing_stage").agg(
        岗位数=("id", "count"),
        公司数=("company_name", "nunique"),
    ).reset_index()

    stage_order = ["未融资", "天使轮", "A轮", "B轮", "C轮", "D轮及以上", "已上市", "不需要融资"]
    fin_stats["_order"] = fin_stats["financing_stage"].apply(
        lambda x: stage_order.index(x) if x in stage_order else 99
    )
    return fin_stats.sort_values("_order").drop(columns=["_order"])


def top_employers(jobs: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """热门雇主排名（按岗位数）。

    Returns:
        DataFrame: 公司, 岗位数, 平均薪资, 技能需求
    """
    import json
    from collections import Counter

    if "company_name" not in jobs.columns:
        return pd.DataFrame()

    stats = jobs.groupby("company_name").agg(
        岗位数=("id", "count"),
        平均薪资=("salary_avg", "mean"),
        行业=("industry", "first"),
    ).reset_index()

    if "平均薪资" in stats.columns:
        stats["平均薪资"] = stats["平均薪资"].round(1)

    # 提取各公司 Top3 技能
    company_skills = {}
    for company in stats["company_name"]:
        company_jobs = jobs[jobs["company_name"] == company]
        skill_counter: Counter = Counter()
        for val in company_jobs["skills"].dropna():
            try:
                items = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                items = [s.strip() for s in str(val).split(",") if s.strip()]
            for s in items:
                skill_counter[str(s).strip()] += 1
        top3 = [s for s, _ in skill_counter.most_common(3)]
        company_skills[company] = ", ".join(top3) if top3 else "-"

    stats = stats.sort_values("岗位数", ascending=False).head(top_n)
    stats["核心技能"] = stats["company_name"].map(company_skills)
    stats["核心技能"] = stats["核心技能"].fillna("-")

    return stats.rename(columns={"company_name": "公司"})


def employer_insights(jobs: pd.DataFrame) -> List[dict]:
    """生成雇主维度洞察。

    Returns:
        洞察列表
    """
    insights = []

    if "company_name" in jobs.columns:
        top_company = jobs["company_name"].value_counts().index[0]
        top_count = jobs["company_name"].value_counts().iloc[0]
        insights.append({
            "title": "岗位最多的雇主",
            "detail": f"{top_company} 以 {top_count} 个岗位居首",
            "level": "info",
        })

    if "company_size" in jobs.columns and "salary_avg" in jobs.columns:
        size_sal = jobs.groupby("company_size")["salary_avg"].mean().sort_values(ascending=False)
        if not size_sal.empty:
            top_size = size_sal.index[0]
            insights.append({
                "title": "薪资最高的企业规模",
                "detail": f"{top_size} 平均薪资 {size_sal.iloc[0]:.1f}K",
                "level": "info",
            })

    if "financing_stage" in jobs.columns and "salary_avg" in jobs.columns:
        fin_sal = jobs.groupby("financing_stage")["salary_avg"].mean().sort_values(ascending=False)
        if not fin_sal.empty:
            top_fin = fin_sal.index[0]
            insights.append({
                "title": "薪资最高的融资阶段",
                "detail": f"{top_fin} 平均薪资 {fin_sal.iloc[0]:.1f}K",
                "level": "info",
            })

    return insights

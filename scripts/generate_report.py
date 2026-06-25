#!/usr/bin/env python3
"""
全量数据综合报告 — Markdown 格式，覆盖所有 15 个标签页的核心输出。

用法:
  python scripts/generate_report.py > reports/full_report_$(date +%Y%m%d).md
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd
import numpy as np

DB_PATH = Path(__file__).parent.parent / "data" / "processed" / "jobs.db"


def banner(text: str, char: str = "=", width: int = 70) -> str:
    return f"\n{char*width}\n{text}\n{char*width}\n"


def section(text: str) -> str:
    return f"\n## {text}\n"


def subsec(text: str) -> str:
    return f"\n### {text}\n"


def header() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# 📊 城市岗位大数据分析 — 全量报告

> 生成时间: {now}
> 数据来源: 51job / Boss / 拉勾 / 猎聘真实采集
"""


def data_overview(df: pd.DataFrame) -> str:
    out = section("1. 📈 数据概览")
    total = len(df)
    cities = df["city"].value_counts()
    sources = df["source"].value_counts()
    categories = df.get("category", pd.Series(dtype=str)).value_counts()

    out += f"""| 指标 | 值 |
|------|-----|
| 总岗位数 | **{total:,}** |
| 城市数 | {cities.nunique()} |
| 数据来源 | {len(sources)} 个 |
| 有薪资数据 | {df['salary_avg'].notna().sum():,} 条 |
| 有详细描述 | {df['description'].notna().sum():,} 条 |
| 有技能标签 | {df['skills'].notna().sum():,} 条 |
| 发布时间跨度 | {df['publish_time'].dropna().min()[:10] if len(df) else 'N/A'} ~ {df['publish_time'].dropna().max()[:10] if len(df) else 'N/A'} |
"""

    out += subsec("城市分布 (TOP 15)")
    out += "\n| 排名 | 城市 | 岗位数 | 占比 |\n|------|------|--------|------|\n"
    for i, (city, cnt) in enumerate(cities.head(15).items(), 1):
        out += f"| {i} | {city} | {cnt:,} | {cnt/total*100:.1f}% |\n"

    out += subsec("来源分布")
    out += "\n| 来源 | 岗位数 | 占比 |\n|------|--------|------|\n"
    for src, cnt in sources.items():
        out += f"| {src} | {cnt:,} | {cnt/total*100:.1f}% |\n"

    if len(categories) > 0:
        out += subsec("岗位类别分布")
        out += "\n| 类别 | 岗位数 | 占比 |\n|------|--------|------|\n"
        for cat, cnt in categories.head(10).items():
            out += f"| {cat} | {cnt:,} | {cnt/total*100:.1f}% |\n"
    return out


def salary_analysis(df: pd.DataFrame) -> str:
    out = section("2. 💰 薪资分析")

    df_sal = df[df["salary_avg"].notna() & (df["salary_avg"] > 0)].copy()
    if df_sal.empty:
        return out + "无薪资数据。\n"

    avg = df_sal["salary_avg"].mean()
    med = df_sal["salary_avg"].median()
    p25 = df_sal["salary_avg"].quantile(0.25)
    p75 = df_sal["salary_avg"].quantile(0.75)
    p90 = df_sal["salary_avg"].quantile(0.90)

    out += f"""| 指标 | 月薪 | 年薪(12薪) |
|------|------|-----------|
| 平均 | ¥{avg/1000:.1f}K | ¥{avg*12/10000:.1f}万 |
| 中位数 | ¥{med/1000:.1f}K | ¥{med*12/10000:.1f}万 |
| P25 | ¥{p25/1000:.1f}K | ¥{p25*12/10000:.1f}万 |
| P75 | ¥{p75/1000:.1f}K | ¥{p75*12/10000:.1f}万 |
| P90 | ¥{p90/1000:.1f}K | ¥{p90*12/10000:.1f}万 |
"""

    # By city
    out += subsec("各城市薪资 TOP 10")
    city_sal = df_sal.groupby("city")["salary_avg"].agg(["mean", "median", "count"])
    city_sal = city_sal[city_sal["count"] >= 10].sort_values("mean", ascending=False).head(10)

    out += "\n| 排名 | 城市 | 均薪 | 中位数 | 样本数 |\n|------|------|------|--------|--------|\n"
    for i, (city, r) in enumerate(city_sal.iterrows(), 1):
        out += f"| {i} | {city} | ¥{r['mean']/1000:.1f}K | ¥{r['median']/1000:.1f}K | {int(r['count'])} |\n"

    # By category
    out += subsec("各类别薪资")
    cat_sal = df_sal.dropna(subset=["category"]) if "category" in df_sal.columns else pd.DataFrame()
    if not cat_sal.empty:
        cat_agg = cat_sal.groupby("category")["salary_avg"].agg(["mean", "count"])
        cat_agg = cat_agg[cat_agg["count"] >= 5].sort_values("mean", ascending=False)
        out += "\n| 排名 | 类别 | 均薪 | 样本 |\n|------|------|------|------|\n"
        for cat, r in cat_agg.iterrows():
            out += f"| - | {cat} | ¥{r['mean']/1000:.1f}K | {int(r['count'])} |\n"

    # By experience
    out += subsec("各经验级别薪资")
    exp_sal = df_sal.dropna(subset=["experience"]).groupby("experience")["salary_avg"].agg(["mean", "count"])
    exp_sal = exp_sal[exp_sal["count"] >= 3].sort_values("mean", ascending=False)
    out += "\n| 经验 | 均薪 | 样本 |\n|------|------|------|\n"
    for exp, r in exp_sal.head(15).iterrows():
        out += f"| {exp} | ¥{r['mean']/1000:.1f}K | {int(r['count'])} |\n"

    return out


def skills_analysis(df: pd.DataFrame) -> str:
    out = section("3. 🔗 技能分析")
    skills_series = df["skills"].dropna()

    # Collect all skills
    all_skills: Counter = Counter()
    for s in skills_series:
        for skill in str(s).split(","):
            sk = skill.strip()
            if sk and len(sk) > 1:
                all_skills[sk] += 1

    out += subsec("TOP 30 热门技能")
    out += "\n| 排名 | 技能 | 出现次数 | 出现率 | 均薪 |\n|------|------|----------|--------|------|\n"

    # Salary per skill
    skill_salary: dict[str, list[float]] = defaultdict(list)
    for _, row in df.iterrows():
        if pd.notna(row.get("skills")) and pd.notna(row.get("salary_avg")):
            for sk in str(row["skills"]).split(","):
                sk = sk.strip()
                if sk:
                    skill_salary[sk].append(row["salary_avg"])

    for i, (sk, cnt) in enumerate(all_skills.most_common(30), 1):
        avg_sal = np.mean(skill_salary.get(sk, [0]))
        rate = cnt / len(df) * 100
        out += f"| {i} | {sk} | {cnt:,} | {rate:.1f}% | ¥{avg_sal/1000:.1f}K |\n"

    return out


def top_jobs(df: pd.DataFrame) -> str:
    out = section("4. 🏆 高薪岗位 TOP 20")
    df_sal = df[df["salary_avg"].notna()].copy()
    df_sal = df_sal.sort_values("salary_avg", ascending=False).head(20)

    out += "\n| 排名 | 岗位 | 公司 | 城市 | 薪资 | 经验 | 学历 |\n|------|------|------|------|------|------|------|\n"
    for i, (_, r) in enumerate(df_sal.iterrows(), 1):
        title = str(r.get("title", ""))[:25]
        comp = str(r.get("company_name", ""))[:20]
        city = r.get("city", "")
        sal = f"¥{r['salary_avg']/1000:.1f}K"
        exp = str(r.get("experience", ""))[:10]
        edu = str(r.get("education", ""))[:8]
        out += f"| {i} | {title} | {comp} | {city} | {sal} | {exp} | {edu} |\n"

    return out


def city_focus(df: pd.DataFrame) -> str:
    """成都专项分析"""
    out = section("5. 🌆 成都专场分析")
    chengdu = df[df["city"] == "成都"]
    if chengdu.empty:
        return out + "无成都数据。\n"

    total = len(chengdu)
    out += f"成都岗位总数: **{total:,}** 条\n\n"

    # Salary
    chengdu_sal = chengdu[chengdu["salary_avg"].notna() & (chengdu["salary_avg"] > 0)]
    if not chengdu_sal.empty:
        avg = chengdu_sal["salary_avg"].mean()
        med = chengdu_sal["salary_avg"].median()
        out += f"""| 指标 | 值 |
|------|----|
| 均薪 | ¥{avg/1000:.1f}K/月 |
| 中位数 | ¥{med/1000:.1f}K/月 |
| 高薪(>¥20K) | {len(chengdu_sal[chengdu_sal['salary_avg'] > 20000]):,} 条 |
"""

    # Top categories in Chengdu
    if "category" in chengdu.columns:
        out += subsec("成都热门岗位类别")
        cats = chengdu["category"].value_counts().head(10)
        out += "\n| 类别 | 岗位数 |\n|------|--------|\n"
        for c, cnt in cats.items():
            out += f"| {c} | {cnt} |\n"

    # Top companies
    out += subsec("成都活跃雇主 TOP 10")
    companies = chengdu["company_name"].value_counts().head(10)
    out += "\n| 公司 | 岗位数 |\n|------|--------|\n"
    for comp, cnt in companies.items():
        comp_str = str(comp)[:30]
        out += f"| {comp_str} | {cnt} |\n"

    return out


def data_quality(df: pd.DataFrame) -> str:
    out = section("6. 📊 数据质量")
    total = len(df)

    completeness = {
        "岗位标题": df["title"].notna().sum(),
        "公司名": df["company_name"].notna().sum(),
        "城市": df["city"].notna().sum(),
        "薪资": df["salary_avg"].notna().sum(),
        "经验要求": df["experience"].notna().sum(),
        "学历要求": df["education"].notna().sum(),
        "技能标签": df["skills"].notna().sum(),
        "详细描述": df["description"].notna().sum(),
        "行业": df.get("industry", pd.Series()).notna().sum(),
        "公司规模": df.get("company_size", pd.Series()).notna().sum(),
        "发布日期": df["publish_time"].notna().sum(),
    }

    out += "\n| 字段 | 完整数 | 完整率 |\n|------|--------|--------|\n"
    for field, cnt in completeness.items():
        out += f"| {field} | {cnt:,} | {cnt/total*100:.1f}% |\n"

    # Month trend
    out += subsec("发布按月分布")
    pubs = df["publish_time"].dropna().apply(lambda x: x[:7] if len(str(x)) >= 7 else x)
    pub_counts = pubs.value_counts().sort_index()
    out += "\n| 月份 | 数量 |\n|------|------|\n"
    for month, cnt in pub_counts.items():
        out += f"| {month} | {cnt:,} |\n"

    return out


def main(db_path: str = None) -> str:
    db_path = db_path or str(DB_PATH)
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM jobs", conn)
    conn.close()

    parts = [
        header(),
        data_overview(df),
        salary_analysis(df),
        skills_analysis(df),
        top_jobs(df),
        city_focus(df),
        data_quality(df),
        banner("报告结束", "="),
    ]

    return "\n".join(parts)


if __name__ == "__main__":
    report = main()
    print(report)

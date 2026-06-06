from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.analytics import filter_jobs, load_jobs, load_skills, overview_metrics
from src.database import connect, import_csv, init_db
from src.sample_data import generate_sample_csv


DB_PATH = ROOT / "data" / "processed" / "jobs.db"
SAMPLE_CSV = ROOT / "data" / "raw" / "chengdu_jobs_sample.csv"


def ensure_data() -> None:
    if not SAMPLE_CSV.exists():
        generate_sample_csv(SAMPLE_CSV)
    conn = connect(DB_PATH)
    init_db(conn)
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if count == 0:
        import_csv(conn, SAMPLE_CSV)
    conn.close()


@st.cache_data(show_spinner=False)
def read_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = sqlite3.connect(DB_PATH)
    jobs = load_jobs(conn)
    skills = load_skills(conn)
    conn.close()
    if not jobs.empty:
        jobs["publish_time"] = pd.to_datetime(jobs["publish_time"], errors="coerce")
    if not skills.empty:
        skills["publish_time"] = pd.to_datetime(skills["publish_time"], errors="coerce")
    return jobs, skills


def sidebar_filters(jobs: pd.DataFrame) -> dict:
    st.sidebar.header("筛选")
    cities = ["全部"] + sorted(jobs["city"].dropna().unique().tolist())
    city = st.sidebar.selectbox("城市", cities, index=1 if "成都" in cities else 0)
    districts = st.sidebar.multiselect("区域", sorted(jobs["district"].dropna().unique().tolist()))
    industries = st.sidebar.multiselect("行业", sorted(jobs["industry"].dropna().unique().tolist()))
    educations = st.sidebar.multiselect("学历", sorted(jobs["education"].dropna().unique().tolist()))
    experiences = st.sidebar.multiselect("经验", sorted(jobs["experience"].dropna().unique().tolist()))
    keyword = st.sidebar.text_input("关键词", placeholder="例如 Python、前端、销售")
    return {
        "city": city,
        "districts": districts,
        "industries": industries,
        "educations": educations,
        "experiences": experiences,
        "keyword": keyword,
    }


def render_overview(jobs: pd.DataFrame, skills: pd.DataFrame) -> None:
    metrics = overview_metrics(jobs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("岗位数", f"{metrics['total_jobs']:,}")
    col2.metric("平均薪资", f"{metrics['avg_salary'] / 1000:.1f}K")
    col3.metric("中位数薪资", f"{metrics['median_salary'] / 1000:.1f}K")
    col4.metric("公司数", f"{metrics['company_count']:,}")

    left, right = st.columns(2)
    with left:
        title_counts = jobs["title"].value_counts().head(12).reset_index()
        title_counts.columns = ["岗位", "数量"]
        st.plotly_chart(px.bar(title_counts, x="数量", y="岗位", orientation="h", title="热门岗位"), use_container_width=True)
    with right:
        industry_counts = jobs["industry"].value_counts().head(12).reset_index()
        industry_counts.columns = ["行业", "数量"]
        st.plotly_chart(px.pie(industry_counts, values="数量", names="行业", title="行业占比"), use_container_width=True)

    left, right = st.columns(2)
    with left:
        district = jobs.groupby("district", as_index=False).agg(岗位数=("id", "count"), 平均薪资=("salary_avg", "mean"))
        st.plotly_chart(px.bar(district, x="district", y="岗位数", color="平均薪资", title="区域岗位分布"), use_container_width=True)
    with right:
        skill_counts = skills[skills["job_id"].isin(jobs["id"])]["skill"].value_counts().head(20).reset_index()
        skill_counts.columns = ["技能", "数量"]
        st.plotly_chart(px.bar(skill_counts, x="数量", y="技能", orientation="h", title="热门技能"), use_container_width=True)


def render_job_analysis(jobs: pd.DataFrame) -> None:
    st.subheader("岗位分析")
    salary_jobs = jobs.dropna(subset=["salary_avg"]).copy()
    if salary_jobs.empty:
        st.info("当前筛选条件下没有可分析薪资的岗位。")
        return

    left, right = st.columns(2)
    with left:
        st.plotly_chart(px.box(salary_jobs, x="title", y="salary_avg", title="岗位薪资分布"), use_container_width=True)
    with right:
        salary_by_exp = salary_jobs.groupby("experience", as_index=False)["salary_avg"].mean()
        st.plotly_chart(px.bar(salary_by_exp, x="experience", y="salary_avg", title="不同经验平均薪资"), use_container_width=True)

    trend = jobs.dropna(subset=["publish_time"]).copy()
    if not trend.empty:
        trend["week"] = trend["publish_time"].dt.to_period("W").astype(str)
        weekly = trend.groupby("week", as_index=False).agg(岗位数=("id", "count"), 平均薪资=("salary_avg", "mean"))
        st.plotly_chart(px.line(weekly, x="week", y=["岗位数", "平均薪资"], title="周度趋势"), use_container_width=True)


def render_region_analysis(jobs: pd.DataFrame) -> None:
    st.subheader("区域分析")
    region = jobs.groupby("district", as_index=False).agg(
        岗位数=("id", "count"),
        平均薪资=("salary_avg", "mean"),
        公司数=("company_name", "nunique"),
    )
    st.dataframe(region.sort_values("岗位数", ascending=False), use_container_width=True, hide_index=True)
    st.plotly_chart(px.scatter(region, x="岗位数", y="平均薪资", size="公司数", text="district", title="区域岗位数与薪资关系"), use_container_width=True)


def render_skill_analysis(jobs: pd.DataFrame, skills: pd.DataFrame) -> None:
    st.subheader("技能分析")
    filtered_skills = skills[skills["job_id"].isin(jobs["id"])]
    if filtered_skills.empty:
        st.info("当前筛选条件下没有技能数据。")
        return
    skill_stats = filtered_skills.groupby("skill", as_index=False).agg(
        出现次数=("skill", "count"),
        平均薪资=("salary_avg", "mean"),
    )
    top = skill_stats.sort_values("出现次数", ascending=False).head(20)
    st.plotly_chart(px.scatter(top, x="出现次数", y="平均薪资", text="skill", size="出现次数", title="技能热度与薪资"), use_container_width=True)
    st.dataframe(top, use_container_width=True, hide_index=True)


def render_job_table(jobs: pd.DataFrame) -> None:
    st.subheader("岗位明细")
    columns = [
        "title",
        "company_name",
        "salary_text",
        "district",
        "experience",
        "education",
        "industry",
        "skills",
        "publish_time",
        "source",
    ]
    st.dataframe(jobs[columns], use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="城市岗位大数据分析平台", layout="wide")
    ensure_data()
    jobs, skills = read_data()

    st.title("城市岗位大数据分析平台")
    st.caption("当前版本使用样例数据和 CSV 导入流程，后续可接入合规授权数据源。")

    filters = sidebar_filters(jobs)
    filtered_jobs = filter_jobs(jobs, **filters)

    if filtered_jobs.empty:
        st.warning("当前筛选条件下没有岗位数据。")
        return

    tabs = st.tabs(["城市概览", "岗位分析", "区域分析", "技能分析", "岗位明细"])
    with tabs[0]:
        render_overview(filtered_jobs, skills)
    with tabs[1]:
        render_job_analysis(filtered_jobs)
    with tabs[2]:
        render_region_analysis(filtered_jobs)
    with tabs[3]:
        render_skill_analysis(filtered_jobs, skills)
    with tabs[4]:
        render_job_table(filtered_jobs)


if __name__ == "__main__":
    main()

"""概览标签页 — KPI 卡片、类别分布、薪资分布、热门技能。"""

from typing import Dict

import pandas as pd
import plotly.express as px
import streamlit as st


def load_data(conn) -> pd.DataFrame:
    """从数据库加载岗位数据全量。"""
    cols = [
        "id", "source", "title", "company_name", "city", "district",
        "salary_text", "salary_min", "salary_max", "salary_avg", "salary_months",
        "experience", "education", "industry", "company_size", "financing_stage",
        "source_url", "publish_time", "crawl_time", "skills",
        "collection_batch", "is_active"
    ]
    q = f"SELECT {','.join(c for c in cols)} FROM jobs"
    return pd.read_sql(q, conn)


def _extract_skills(series: pd.Series) -> Dict[str, int]:
    """从 skills 列（JSON 数组或逗号分隔）提取技能计数。"""
    counts: Dict[str, int] = {}
    for val in series.dropna():
        try:
            import json
            items = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(val).split(",") if s.strip()]
        for s in items:
            s = str(s).strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
    return counts


def apply_filters(jobs: pd.DataFrame, keyword: str,
                  real_only: bool, skills_filter: 'str | None') -> pd.DataFrame:
    """应用侧边栏筛选到 DataFrame。"""
    result = jobs.copy()

    if "city" in result.columns:
        result = result[result["city"].notna()]

    if real_only:
        mock_sources = {"boss", "lagou", "liepin"}
        if "source" in result.columns:
            result = result[~result["source"].str.lower().isin(mock_sources)]

    if keyword:
        mask = pd.Series(False, index=result.index)
        for col in ["title", "company_name", "industry", "skills"]:
            if col in result.columns:
                mask |= result[col].astype(str).str.contains(keyword, case=False, na=False)
        result = result[mask]

    if skills_filter:
        result = result[
            result["skills"].astype(str).str.contains(skills_filter, case=False, na=False, regex=False)
        ]

    return result


def render_sidebar(jobs: pd.DataFrame) -> dict:
    """渲染侧边栏筛选器，返回筛选参数字典。"""
    st.sidebar.title("🔍 筛选条件")

    if "city" in jobs.columns:
        city_list = sorted(jobs["city"].dropna().unique())
        selected_cities = st.sidebar.multiselect("城市", city_list, default=city_list)
    else:
        selected_cities = []

    keyword = st.sidebar.text_input("关键词搜索", placeholder="输入公司/岗位/技能...")

    # 岗位分类筛选
    category_list: list[str] = []
    if "category" in jobs.columns:
        category_list = sorted(jobs["category"].dropna().unique())
    selected_categories = st.sidebar.multiselect(
        "岗位类别", category_list, default=category_list
    ) if category_list else []

    real_only = st.sidebar.checkbox("仅真实数据", value=True,
                                    help="仅显示 51job 来源数据，排除 mock 数据")

    # 技能标签快捷筛选（增强提取）
    skills_list: list[str] = []
    try:
        from src.nlp.skill_extractor import extract_skills_enhanced
        all_skills = extract_skills_enhanced(jobs)
        skills_list = sorted(all_skills.keys())
    except Exception:
        try:
            all_skills = _extract_skills(jobs["skills"])
            skills_list = sorted(all_skills.keys())
        except Exception:
            pass

    skills_filter = st.sidebar.selectbox("技能标签", ["全部"] + skills_list) if skills_list else "全部"
    if skills_filter == "全部":
        skills_filter = None

    st.sidebar.markdown(
        f"<small>已加载 {len(jobs)} 条数据，{len(selected_cities)} 个城市</small>",
        unsafe_allow_html=True,
    )

    return {
        "selected_cities": selected_cities,
        "selected_categories": selected_categories,
        "keyword": keyword,
        "real_only": real_only,
        "skills_filter": skills_filter,
    }


def render_overview(jobs: pd.DataFrame, city_list: list[str]) -> None:
    """渲染概览标签页 — KPI 卡片、类别分布、热门技能。
    
    单城：综合 KPI + 饼图/直方图/技能排行。
    多城：按城市拆分的对比图表。
    """
    from src.analytics import overview_metrics

    st.subheader("📊 数据概览")
    city_str = f"{city_list[0]}" if len(city_list) == 1 else f"{len(city_list)} 个城市"
    st.caption(f"范围：{city_str} · 共 {len(jobs)} 个岗位")

    multi_city = len(city_list) > 1

    kpis = overview_metrics(jobs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("岗位数", f"{kpis['total_jobs']} 个")
    col2.metric("公司数", f"{kpis['company_count']} 家")
    col3.metric("薪资中位", f"{kpis['median_salary']:.1f}K/月")
    col4.metric("平均薪资", f"{kpis['avg_salary']:.1f}K/月")

    # ── 多城对比：城市级 KPI 表 ──
    if multi_city and "city" in jobs.columns:
        with st.expander("📋 各城市关键指标", expanded=True):
            city_stats = jobs.groupby("city").agg(
                岗位数=("id", "count"),
                公司数=("company_name", "nunique"),
                平均薪资=("salary_avg", "mean"),
                薪资中位=("salary_avg", "median"),
            ).reset_index()
            city_stats["平均薪资"] = city_stats["平均薪资"].round(1)
            city_stats["薪资中位"] = city_stats["薪资中位"].round(1)
            city_stats = city_stats.sort_values("岗位数", ascending=False)
            st.dataframe(city_stats, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 三列：类别分布 + 薪资分布 + 热门技能（多城时追加城市对比）
    if "category" in jobs.columns:
        cat_counts = jobs["category"].value_counts().reset_index()
        cat_counts.columns = ["类别", "数量"]
        col1, col2, col3 = st.columns(3)
        with col1:
            fig_cat = px.pie(cat_counts, values="数量", names="类别",
                             title="📂 岗位类别分布", hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_cat.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=350)
            st.plotly_chart(fig_cat, use_container_width=True)
        with col2:
            real = jobs[jobs["salary_avg"].notna()]
            if not real.empty:
                if multi_city and "city" in real.columns:
                    fig = px.histogram(real, x="salary_avg", nbins=25, title="💰 各城薪资分布",
                                       color="city", barmode="overlay", opacity=0.65,
                                       labels={"salary_avg": "月薪(K/月)", "count": "岗位数"},
                                       color_discrete_sequence=px.colors.qualitative.Set2)
                else:
                    fig = px.histogram(real["salary_avg"], nbins=25, title="💰 薪资分布",
                                       labels={"salary_avg": "月薪(K/月)", "count": "岗位数"},
                                       color_discrete_sequence=["#00b4d8"])
                fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无有效薪资数据")
        with col3:
            try:
                from src.nlp.skill_extractor import extract_skills_enhanced
                skills = extract_skills_enhanced(jobs)
            except Exception:
                skills = _extract_skills(jobs["skills"])
            if skills:
                top = sorted(skills.items(), key=lambda x: x[1], reverse=True)[:15]
                df_skills = pd.DataFrame(top, columns=["技能", "需求次数"])
                fig2 = px.bar(df_skills, x="需求次数", y="技能", orientation="h",
                              title="🔥 Top15 热门技能 (NLP增强)",
                              color="需求次数", color_continuous_scale="viridis")
                fig2.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    margin=dict(t=40, b=0, l=0, r=0), height=350,
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("暂未提取到技能")

        # ── 多城对比：各类别岗位数对比 ──
        if multi_city and "city" in jobs.columns and "category" in jobs.columns:
            with st.expander("📊 各城市 × 各类别热力图", expanded=False):
                city_cat = jobs.groupby(["city", "category"]).size().reset_index(name="cnt")
                city_cat_pivot = city_cat.pivot(index="city", columns="category", values="cnt").fillna(0).astype(int)
                fig_heat = px.imshow(
                    city_cat_pivot, text_auto=True, aspect="auto",
                    title="🏙️ 城市 × 类别 岗位热力图",
                    color_continuous_scale="Blues",
                )
                fig_heat.update_layout(height=400)
                st.plotly_chart(fig_heat, use_container_width=True)
    else:
        # 无类别回退
        real = jobs[jobs["salary_avg"].notna()]
        if not real.empty:
            col1, col2 = st.columns(2)
            with col1:
                fig = px.histogram(real["salary_avg"], nbins=25, title="💰 薪资分布",
                                   labels={"salary_avg": "月薪(K/月)", "count": "岗位数"},
                                   color_discrete_sequence=["#00b4d8"])
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                skills = _extract_skills(real["skills"])
                if skills:
                    top = sorted(skills.items(), key=lambda x: x[1], reverse=True)[:15]
                    df_skills = pd.DataFrame(top, columns=["技能", "需求次数"])
                    fig2 = px.bar(df_skills, x="需求次数", y="技能", orientation="h",
                                  title="🔥 Top15 热门技能", color="需求次数",
                                  color_continuous_scale="viridis")
                    fig2.update_layout(yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("暂无有效薪资数据。")

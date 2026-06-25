"""岗位智能推荐标签页 — 技能匹配 + 薪资拟合 + 多维度加权。"""

import pandas as pd
import streamlit as st

# 预设技能池
PRESET_SKILLS = [
    "Python", "Java", "Go", "C++", "Rust", "TypeScript", "JavaScript",
    "React", "Vue", "Django", "Spring", "FastAPI", "Flask",
    "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch",
    "Docker", "Kubernetes", "AWS", "Linux", "Git",
    "Spark", "Hadoop", "Flink", "Kafka",
    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
    "Selenium", "JMeter", "CI/CD", "Jenkins",
    "Figma", "产品设计", "用户研究", "数据分析",
]

SKILL_TO_CN = {
    "Python": "Python", "Java": "Java", "Go": "Go", "C++": "C++", "Rust": "Rust",
    "TypeScript": "TypeScript", "JavaScript": "JavaScript",
    "React": "React", "Vue": "Vue", "Django": "Django", "Spring": "Spring",
    "FastAPI": "FastAPI", "Flask": "Flask",
    "MySQL": "MySQL", "PostgreSQL": "PostgreSQL", "Redis": "Redis",
    "MongoDB": "MongoDB", "Elasticsearch": "ES",
    "Docker": "Docker", "Kubernetes": "K8s", "AWS": "AWS", "Linux": "Linux",
    "Git": "Git", "Spark": "Spark", "Hadoop": "Hadoop", "Flink": "Flink",
    "Kafka": "Kafka", "TensorFlow": "TF", "PyTorch": "PyTorch",
    "Scikit-learn": "sklearn", "Pandas": "Pandas", "NumPy": "NumPy",
    "Selenium": "Selenium", "JMeter": "JMeter", "CI/CD": "CI/CD",
    "Jenkins": "Jenkins", "Figma": "Figma", "产品设计": "产品设计",
    "用户研究": "用研", "数据分析": "数据分析",
}


def render_recommender(jobs_all: pd.DataFrame) -> None:
    """渲染岗位推荐标签页。"""
    from src.analytics.recommender import (
        JobRecommender, JobSeeker, skill_gap_analysis, competitor_analysis,
    )

    st.subheader("🎯 岗位智能推荐")

    if "skills" not in jobs_all.columns or "salary_avg" not in jobs_all.columns:
        st.info("数据不完整，无法推荐。")
        return

    # ── 侧边栏：求职者画像 ──
    st.markdown("### 🧑‍💻 你的画像")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        target_skills = st.multiselect(
            "🔧 你的技能",
            PRESET_SKILLS,
            default=["Python", "MySQL", "Linux"],
            help="选择你掌握的技能（可多选）",
        )

    with col2:
        all_cities = sorted(jobs_all["city"].dropna().unique())
        default_cities = ["成都"] if "成都" in all_cities else all_cities[:1]
        preferred_cities = st.multiselect(
            "📍 目标城市",
            all_cities,
            default=default_cities,
            help="偏好城市（可多选）",
        )

    with col3:
        target_salary = st.number_input(
            "💰 期望月薪(元)",
            min_value=0, value=15000, step=1000,
            format="%d",
            help="你的期望税前月薪",
        )

    with col4:
        experience_options = [
            "不限", "无需经验", "1年及以上", "2年及以上",
            "3年及以上", "5年及以上",
        ]
        experience = st.selectbox("📅 经验等级", experience_options, index=0)

    # 高级选项
    with st.expander("⚙️ 高级权重", expanded=False):
        w1 = st.slider("技能匹配权重", 0.0, 1.0, 0.55, 0.05)
        w2 = st.slider("薪资拟合权重", 0.0, 1.0, 0.25, 0.05)
        w3 = st.slider("相关性权重", 0.0, 1.0, 0.20, 0.05)

        preferred_industries = st.multiselect(
            "🏭 行业偏好",
            sorted(jobs_all["industry"].dropna().unique())[:30],
        )

    st.markdown("---")

    if not target_skills:
        st.warning("👆 请至少选择 1 项技能")
        return

    # ── 构建 seeker ──
    seeker = JobSeeker(
        target_skills=target_skills,
        preferred_cities=preferred_cities,
        target_salary=target_salary if target_salary > 0 else None,
        experience_level=experience if experience != "不限" else None,
        preferred_industries=list(preferred_industries),
        weights={"skills": w1, "salary_fit": w2, "relevance": w3},
    )

    # ── 推荐 ──
    with st.spinner("🔍 正在分析岗位池..."):
        recommender = JobRecommender(jobs_all)
        results = recommender.recommend(seeker, top_k=20)

    if results.empty:
        st.warning("未找到匹配岗位，尝试放宽条件。")
        return

    # ── 推荐卡片 ──
    st.markdown("### 🏆 推荐岗位 TOP20")
    st.caption(f"综合评分 = 技能匹配({w1:.0%}) + 薪资拟合({w2:.0%}) + 相关性({w3:.0%})")

    # 展示列
    display_cols = {
        "title": "岗位",
        "company_name": "公司",
        "city": "城市",
        "salary_avg": "月薪",
        "salary_months": "年薪月数",
        "experience": "经验",
        "industry": "行业",
        "score": "综合分",
        "skills_sim": "技能",
        "salary_fit": "薪资",
    }
    available = [k for k in display_cols if k in results.columns]

    # 颜色编码
    def score_color(val):
        if val >= 0.8:
            return "background-color: #27ae60; color: white"
        elif val >= 0.6:
            return "background-color: #f39c12; color: white"
        elif val >= 0.4:
            return "background-color: #e67e22; color: white"
        return ""

    styled = results[available].rename(columns={
        "title": "岗位", "company_name": "公司", "city": "城市",
        "salary_avg": "月薪", "salary_months": "薪", "experience": "经验",
        "industry": "行业", "score": "综合分", "skills_sim": "技能分",
        "salary_fit": "薪资分",
    })

    st.dataframe(
        styled.style.format({
            "月薪": "{:,.0f}",
            "综合分": "{:.3f}",
            "技能分": "{:.3f}",
            "薪资分": "{:.3f}",
        }).map(score_color, subset=["综合分"]),
        use_container_width=True, hide_index=True,
        height=600,
    )

    st.markdown("---")

    # ── 技能缺口 ──
    col_gap, col_comp = st.columns(2)

    with col_gap:
        st.markdown("### 🔍 技能缺口分析")
        gaps = skill_gap_analysis(seeker, results.head(10))
        if gaps:
            for g in gaps:
                icon = {"critical": "🔴", "moderate": "🟡", "nice-to-have": "🟢"}[g["gap_level"]]
                label = {"critical": "关键缺口", "moderate": "建议补充", "nice-to-have": "加分项"}[g["gap_level"]]
                st.markdown(
                    f"{icon} **{g['skill']}** — {label} "
                    f"(出现 {g['demand_count']} 次, 涉及均薪 ¥{g['avg_salary']:,.0f})"
                )
        else:
            st.success("✅ 你的技能已覆盖所有高频需求")

    with col_comp:
        st.markdown("### 📊 市场竞品分析")
        comp = competitor_analysis(seeker, results)
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.metric("竞争烈度", comp["competition_level"])
        with col_c2:
            st.metric("同类岗位", f"{comp['demand_scale']} 个")
        with col_c3:
            if comp["salary_percentile"] is not None:
                st.metric("薪资排名", f"Top {100-comp['salary_percentile']:.0f}%")
            else:
                st.metric("同类均薪", f"¥{comp['avg_competitor_salary']:,.0f}")

        # 薪资分布参考
        rec_salaries = results["salary_avg"].dropna()
        if len(rec_salaries) > 5:
            import plotly.express as px
            fig_comp = px.histogram(
                rec_salaries, nbins=15,
                title="推荐岗位薪资分布",
                labels={"value": "月薪(元)", "count": "岗位数"},
                color_discrete_sequence=["#00b4d8"],
            )
            fig_comp.add_vline(
                x=seeker.target_salary, line_dash="dash", line_color="red",
                annotation_text=f"期望: ¥{seeker.target_salary:,}",
            )
            fig_comp.update_layout(height=250, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_comp, use_container_width=True)

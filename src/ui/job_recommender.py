"""🎯 岗位推荐 标签页 — 成都+远程 智能推荐引擎。

流式仪表盘：
  左侧：目标薪资滑块 + 远程开关 + 经验偏好
  右侧：TOP 30 推荐列表
"""

import pandas as pd
import streamlit as st


def render_chengdu_recommender(jobs_all: pd.DataFrame) -> None:
    """渲染成都+远程岗位智能推荐标签页。"""
    from src.analytics.job_recommender import JobRecommenderV2, JobSeekerProfile

    st.subheader("🎯 岗位推荐（成都 · 远程）")

    if "skills" not in jobs_all.columns or "salary_avg" not in jobs_all.columns:
        st.info("数据不完整，无法推荐。")
        return

    # ── 个人画像展示 ──
    st.markdown("### 🧑‍💻 Python 全栈工程师 · 成都 · 15K-25K")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("核心技能", "Python · Docker · MySQL · Redis")
    with col_b:
        st.metric("目标城市", "成都 + 远程")
    with col_c:
        st.metric("目标月薪", "15,000 - 25,000 元")

    st.markdown("---")

    # ── 左侧筛选 + 右侧推荐 ──
    left, right = st.columns([1, 2])

    with left:
        st.markdown("#### ⚙️ 筛选条件")

        # 目标薪资范围滑块
        salary_range = st.slider(
            "💰 目标月薪范围(元)",
            min_value=0, max_value=60000,
            value=(15000, 25000),
            step=1000,
            format="%d",
        )

        # 远程开关
        include_remote = st.toggle(
            "🌐 包含远程岗位",
            value=True,
            help="开启后同时推荐标注为远程/线上/全国的岗位",
        )

        # 经验偏好
        experience_filter = st.selectbox(
            "📅 经验偏好",
            ["不限", "无需经验", "1-3年", "3-5年", "5-10年", "10年以上"],
            index=0,
        )

        # 展示评分维度
        st.markdown("#### 📊 评分维度")
        st.caption("技能匹配 40% | 薪资匹配 25% | 成长潜力 20% | 公司质量 15%")

        # 高级权重调整
        w_skills = 0.40
        w_salary = 0.25
        w_growth = 0.20
        w_company = 0.15
        with st.expander("⚖️ 调整权重", expanded=False):
            w_skills = st.slider("技能匹配", 0.1, 0.6, 0.40, 0.05)
            w_salary = st.slider("薪资匹配", 0.1, 0.4, 0.25, 0.05)
            w_growth = st.slider("成长潜力", 0.1, 0.4, 0.20, 0.05)
            w_company = st.slider("公司质量", 0.1, 0.3, 0.15, 0.05)
            # 归一化
            total_w = w_skills + w_salary + w_growth + w_company
            w_skills /= total_w
            w_salary /= total_w
            w_growth /= total_w
            w_company /= total_w
            st.caption(f"归一化后: 技能 {w_skills:.0%} | 薪资 {w_salary:.0%} | 成长 {w_growth:.0%} | 公司 {w_company:.0%}")

    with right:
        st.markdown("#### 🏆 推荐岗位 TOP 30")

        # 构建 seeker profile
        profile = JobSeekerProfile(
            salary_min=float(salary_range[0]),
            salary_max=float(salary_range[1]),
            remote_ok=include_remote,
            experience=experience_filter if experience_filter != "不限" else "",
            weights={"skills": w_skills, "salary": w_salary, "growth": w_growth, "company": w_company},
        )

        with st.spinner("🔍 正在分析岗位池..."):
            engine = JobRecommenderV2(jobs_all)
            results = engine.recommend(profile, top_k=30)

        if results.empty:
            st.warning("未找到匹配岗位，尝试放宽薪资范围或开启远程筛选。")
            return

        # 统计概览
        chengdu_count = (results["location_type"] == "🏙 成都").sum()
        remote_count = (results["location_type"] == "🌐 远程").sum()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("推荐总数", len(results))
        with col2:
            st.metric("成都岗位", chengdu_count)
        with col3:
            st.metric("远程岗位", remote_count)
        with col4:
            avg_score = results["final_score"].mean()
            st.metric("平均评分", f"{avg_score:.3f}")

        # ── 推荐列表 ──
        display_cols = {
            "title": "岗位名称",
            "company_name": "公司",
            "city": "城市",
            "salary_avg": "月薪(元)",
            "experience": "经验",
            "industry": "行业",
            "final_score": "综合评分",
            "skill_score": "技能分",
            "salary_score": "薪资分",
            "growth_score": "成长分",
            "company_score": "公司分",
            "location_type": "类型",
        }
        available = {k: v for k, v in display_cols.items() if k in results.columns}

        # 颜色映射
        def score_color(val):
            if val >= 0.7:
                return "background-color: #27ae60; color: white"
            elif val >= 0.5:
                return "background-color: #2980b9; color: white"
            elif val >= 0.3:
                return "background-color: #f39c12; color: white"
            return "background-color: #95a5a6; color: white"

        styled = results[list(available.keys())].rename(columns=available)

        score_cols = ["综合评分", "技能分", "薪资分", "成长分", "公司分"]
        existing_score_cols = [c for c in score_cols if c in styled.columns]

        fmt_dict = {}
        for col_name in existing_score_cols:
            fmt_dict[col_name] = "{:.3f}"
        if "月薪(元)" in styled.columns:
            fmt_dict["月薪(元)"] = "{:,.0f}"

        styled_view = styled.style.format(fmt_dict)
        for col_name in existing_score_cols:
            styled_view = styled_view.map(score_color, subset=[col_name])

        st.dataframe(
            styled_view,
            use_container_width=True,
            hide_index=True,
            height=700,
        )

        # ── CSV 导出按钮 ──
        csv = results[list(available.keys())].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 导出推荐结果 (CSV)",
            data=csv,
            file_name="job_recommendations.csv",
            mime="text/csv",
        )

    st.markdown("---")

    # ── 技能缺口分析 ──
    col_gap, col_dist = st.columns(2)

    with col_gap:
        st.markdown("### 🔍 技能缺口分析")
        st.caption("TOP 30 推荐岗位中，你尚未掌握的技能")

        gaps = engine.skill_gap_analysis(results)

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

    with col_dist:
        st.markdown("### 📊 评分分布")

        import plotly.graph_objects as go

        dims = ["技能匹配", "薪资匹配", "成长潜力", "公司质量"]
        dim_keys = ["skill_score", "salary_score", "growth_score", "company_score"]
        avg_dims = [results[dk].mean() for dk in dim_keys]

        fig = go.Figure(data=[
            go.Bar(
                x=dims, y=avg_dims,
                marker_color=["#3498db", "#2ecc71", "#e74c3c", "#f39c12"],
                text=[f"{v:.3f}" for v in avg_dims],
                textposition="outside",
            )
        ])
        fig.update_layout(
            title="各维度平均得分",
            yaxis=dict(range=[0, 1], title="得分"),
            height=300,
            margin=dict(t=40, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

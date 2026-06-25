"""竞争力指数标签页 — 输入画像 → 多维评分 → 城市排名。"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_competitiveness(jobs: pd.DataFrame) -> None:
    """渲染求职竞争力指数。"""
    from src.analytics.competitiveness import (
        CompetitivenessAnalyzer, CompetitorProfile, DEFAULT_WEIGHTS,
    )

    st.subheader("🏅 求职竞争力指数")
    st.caption("基于你的技能、薪资期望、目标城市，计算市场竞争力分数")

    # ── 画像输入 ──
    with st.form("competitor_form"):
        col_a, col_b = st.columns([2, 1])

        with col_a:
            # 技能输入
            all_skills = _extract_all_skills(jobs)
            my_skills = st.multiselect(
                "你的技能栈",
                options=all_skills,
                default=["Python"] if "Python" in all_skills else [],
                help="选择你掌握的技术",
            )
            # 自由输入
            extra = st.text_input("补充技能（逗号分隔）", placeholder="例如：Kubernetes, Kafka")
            if extra:
                my_skills = list(set(my_skills + [s.strip() for s in extra.split(",") if s.strip()]))

        with col_b:
            target_city = st.selectbox(
                "目标城市",
                sorted(jobs["city"].dropna().unique().tolist()),
                index=0,
            )
            target_salary = st.number_input(
                "期望月薪 (元)", min_value=3000, value=15000, step=1000,
                help="税前月薪",
            )
            experience = st.selectbox(
                "工作年限",
                ["应届生", "1年以下", "1-3年", "3-4年", "5-7年", "8-9年", "10年以上"],
                index=2,
            )
            education = st.selectbox(
                "学历",
                ["大专", "本科", "硕士", "博士"],
                index=1,
            )

        submitted = st.form_submit_button("🔍 计算竞争力", use_container_width=True)

    if not submitted:
        st.info("👆 填写画像后点击计算")
        return

    if not my_skills:
        st.warning("请至少选择一个技能。")
        return

    # ── 分析 ──
    profile = CompetitorProfile(
        skills=my_skills,
        target_city=target_city,
        target_salary=target_salary,
        experience=experience,
        education=education,
    )

    analyzer = CompetitivenessAnalyzer(jobs)
    result = analyzer.analyze(profile)

    if result.total == 0:
        st.warning("目标城市暂无足够数据，无法评估。")
        return

    # ── 总分卡片 ──
    _render_score_card(result, profile)

    # ── 雷达图 ──
    _render_radar(result)

    # ── 洞察 ──
    st.markdown("---")
    st.markdown("### 📝 竞争力洞察")
    for insight in result.insights:
        st.markdown(f"- {insight}")

    # ── 技能缺口 ──
    if result.top_missing_skills:
        st.markdown("---")
        st.markdown("### 🔑 技能缺口分析")
        st.caption("市场高频但你没有的技能 → 优先学习候选")
        gap_df = pd.DataFrame({
            "推荐学习": result.top_missing_skills[:8],
        })
        st.dataframe(gap_df, hide_index=True, use_container_width=True)

    # ── 薪资定位细节 ──
    st.markdown("---")
    st.markdown("### 📈 薪资定位详情")
    market = jobs[jobs["city"] == profile.target_city]
    salaries = market["salary_avg"].dropna()
    if not salaries.empty:
        _render_salary_distribution(salaries, target_salary)

    # ── 权重调节 ──
    with st.expander("⚙️ 评分权重调节"):
        new_weights = {}
        for dim, w in DEFAULT_WEIGHTS.items():
            label = {
                "skill_match": "技能匹配度",
                "salary_position": "薪资定位",
                "skill_rarity": "技能稀缺性",
                "market_heat": "市场热度",
                "exp_edu_align": "经验学历",
            }.get(dim, dim)
            new_weights[dim] = st.slider(
                label, 0.0, 1.0, w, 0.05,
                help=f"当前权重 {w:.0%}"
            )
        if abs(sum(new_weights.values()) - 1.0) > 0.01:
            st.warning(f"⚠️ 权重合计 {sum(new_weights.values()):.0%}，已自动归一化")
            total_w = sum(new_weights.values())
            new_weights = {k: v / total_w for k, v in new_weights.items()}

        profile.weights = new_weights
        result2 = analyzer.analyze(profile)
        st.metric("调整后竞争力总分", f"{result2.total} 分", f"{result2.total - result.total:+.1f}")


# ── 辅助渲染函数 ──

def _extract_all_skills(jobs: pd.DataFrame) -> list:
    skills_set = set()
    for v in jobs["skills"].dropna():
        for s in v.split(","):
            s = s.strip()
            if s and len(s) >= 2:
                skills_set.add(s)
    return sorted(skills_set, key=lambda x: x.lower())


def _render_score_card(result, profile):
    """大号 KPI 卡片。"""
    col_a, col_b, col_c, col_d, col_e = st.columns(5)

    # 总分颜色
    if result.total >= 80:
        color = "#00b4d8"
        emoji = "🚀"
    elif result.total >= 60:
        color = "#90be6d"
        emoji = "✅"
    elif result.total >= 40:
        color = "#f9c74f"
        emoji = "⚡"
    else:
        color = "#f94144"
        emoji = "🔧"

    with col_a:
        st.markdown(
            f"<h1 style='text-align:center;color:{color};font-size:48px;margin:0'>{emoji}</h1>"
            f"<h2 style='text-align:center;color:{color};font-size:36px;margin:0'>{result.total}</h2>"
            f"<p style='text-align:center;color:gray;margin:0'>竞争力总分</p>",
            unsafe_allow_html=True,
        )

    with col_b:
        st.metric("技能匹配度", f"{result.skill_match:.0f} 分")
    with col_c:
        st.metric("薪资定位", result.salary_rank)
    with col_d:
        st.metric("市场热度", f"{result.market_heat:.0f} 分",
                  f"{result.total_matched_jobs} 岗位")
    with col_e:
        st.metric("同城排名", f"前 {100 - result.percentile:.0f}%",
                  f"超过 {result.percentile:.0f}% 岗位薪资")


def _render_radar(result):
    """绘制五维雷达图。"""
    categories = ["技能匹配", "薪资定位", "技能稀缺", "市场热度", "经验学历"]
    values = [
        result.skill_match,
        result.salary_position,
        result.skill_rarity,
        result.market_heat,
        result.exp_edu_align,
    ]
    values.append(values[0])
    categories.append(categories[0])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=categories, fill="toself",
        name="你的竞争力", line_color="#00b4d8",
        fillcolor="rgba(0,180,216,0.25)",
    ))
    # 参考线
    fig.add_trace(go.Scatterpolar(
        r=[50, 50, 50, 50, 50, 50],
        theta=categories, fill="none",
        name="市场中位(50)", line=dict(color="gray", dash="dot"),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False)),
        height=380, margin=dict(t=30, b=0, l=40, r=40),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_salary_distribution(salaries: pd.Series, target: float):
    """薪资分布直方图 + 你的位置标注。"""
    import plotly.express as px
    fig = px.histogram(
        salaries, nbins=40,
        title=f"目标城市薪资分布 (中位: ¥{salaries.median():,.0f})",
        labels={"value": "月薪(元)", "count": "岗位数"},
        color_discrete_sequence=["#90be6d"],
    )
    fig.add_vline(
        x=target, line_dash="solid", line_color="#f94144", line_width=2,
        annotation_text=f"你的期望 ¥{target:,.0f}",
        annotation_position="top",
    )
    fig.add_vline(
        x=salaries.median(), line_dash="dash", line_color="gray",
        annotation_text=f"中位 ¥{salaries.median():,.0f}",
    )
    fig.update_layout(height=350, margin=dict(t=40, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

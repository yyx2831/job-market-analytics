"""趋势分析标签页 — 岗位发布趋势、技能 ROI 模型、类别薪资对比。"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.nlp import category_stats
from src.analytics.purchasing_power import add_purchasing_power
from src.trends import analyze_trends, SkillROIModel


def render_trends(jobs: pd.DataFrame) -> None:
    """渲染趋势标签页 — 时间趋势、技能 ROI、类别薪资与购买力。"""
    st.subheader("📊 市场趋势")

    real = jobs[jobs["publish_time"].notna()].copy()
    if len(real) >= 10:
        real["publish_dt"] = pd.to_datetime(real["publish_time"], format="mixed", errors="coerce")
        real = real[real["publish_dt"].notna()]
        if len(real) < 10:
            st.info("有效发布日期不足 10 条，无法计算趋势。")
            return
        real["week"] = real["publish_dt"].dt.to_period("W").astype(str)
        weekly = real.groupby("week").agg(
            岗位数=("id", "count"),
            平均薪资=("salary_avg", "mean"),
        ).reset_index()

        if len(weekly) >= 2:
            fig = px.line(weekly, x="week", y=["岗位数", "平均薪资"],
                          title="📈 每周发布趋势", markers=True,
                          line_shape="spline", render_mode="svg")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("需多周数据才能展示趋势。")
    else:
        st.info("暂无发布日期数据，无法计算趋势。")

    st.markdown("---")

    # ── 技能 ROI 分析 ──
    st.subheader("💎 技能投资回报 (Skill ROI)")
    city_name = jobs["city"].iloc[0] if len(jobs["city"].unique()) == 1 else "多城"
    st.caption(f"综合需求频率（45%）x 薪资水平（55%）| 数据范围：{city_name}")

    skills_col = jobs["skills"].dropna()
    if len(skills_col) > 50:
        roi_model = SkillROIModel(real)
        roi_results = roi_model.analyze()

        if roi_results:
            col_a, col_b = st.columns([1, 1])

            with col_a:
                st.markdown("**🏆 技能 ROI 排行榜**")
                table_data = []
                for idx, r in enumerate(roi_results[:20], 1):
                    tier_badge = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}.get(r["tier"], "")
                    table_data.append({
                        "排名": idx,
                        "技能": f"{tier_badge} {r['skill']}",
                        "需求": r["demand"],
                        "中位薪资": f"{r['median_salary']:.0f}K",
                        "ROI得分": f"{r['roi_score']:.1f}",
                    })
                st.dataframe(pd.DataFrame(table_data), use_container_width=True,
                             hide_index=True, height=680)

            with col_b:
                plot_data = []
                for r in roi_results:
                    plot_data.append({
                        "技能": r["skill"],
                        "需求次数": r["demand"],
                        "中位薪资(K/月)": r["median_salary"],
                        "ROI得分": r["roi_score"],
                        "等级": r["tier"],
                    })
                df_plot = pd.DataFrame(plot_data)
                tier_colors = {"gold": "#FFD700", "silver": "#C0C0C0", "bronze": "#CD7F32"}

                fig_roi = go.Figure()
                for tier, color in tier_colors.items():
                    tier_df = df_plot[df_plot["等级"] == tier]
                    if tier_df.empty:
                        continue
                    fig_roi.add_trace(go.Scatter(
                        x=tier_df["需求次数"],
                        y=tier_df["中位薪资(K/月)"],
                        mode="markers+text",
                        name={"gold": "🥇黄金", "silver": "🥈白银", "bronze": "🥉青铜"}[tier],
                        text=tier_df["技能"],
                        textposition="top center",
                        marker=dict(
                            size=tier_df["ROI得分"] * 1.5,
                            color=color,
                            line=dict(width=1, color="white"),
                            opacity=0.85,
                        ),
                    ))

                fig_roi.update_layout(
                    title="技能需求 vs 薪资 (气泡大小=ROI)",
                    xaxis_title="需求次数",
                    yaxis_title="中位薪资 (K/月)",
                    height=480,
                    showlegend=True,
                    hovermode="closest",
                )
                st.plotly_chart(fig_roi, use_container_width=True)

            tier_stats = roi_model.tier_stats(roi_results)
            gold_skills = [r["skill"] for r in roi_results if r["tier"] == "gold"]
            silver_skills = [r["skill"] for r in roi_results if r["tier"] == "silver"]

            conclusion_parts = []
            if gold_skills:
                conclusion_parts.append(
                    f"🥇 **黄金级**（{', '.join(gold_skills[:6])}）: 高薪+高需，优先投"
                )
            if silver_skills:
                conclusion_parts.append(
                    f"🥈 **白银级**（{', '.join(silver_skills[:8])}）: 性价比优秀，适合进阶"
                )
            if conclusion_parts:
                st.success(" | ".join(conclusion_parts))
            st.caption(f"基于 {city_name} {len(roi_results)} 个技能标签分析 · 过滤需求<3的低频技能")
        else:
            st.info("暂无足够技能标签数据。")
    else:
        st.info("暂无技能标签数据。")

    # ── 技能需求趋势（上升/稳定/衰退） ──
    st.markdown("---")
    st.subheader("📉 技能需求趋势追踪")
    st.caption("基于 publish_time 按月统计，线性回归判断技能热度走势")

    from src.analytics.skill_trend import compute_skill_demand_trend, trend_summary

    trend_df = compute_skill_demand_trend(jobs)
    if not trend_df.empty:
        summary = trend_summary(jobs)
        col_r, col_s, col_d = st.columns(3)
        col_r.metric("📈 上升期", f"{summary['rising']} 技能")
        col_s.metric("➡️  稳定期", f"{summary['stable']} 技能")
        col_d.metric("📉 衰退期", f"{summary['declining']} 技能")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            rising = trend_df[trend_df["trend_label"] == "rising"].head(10)
            if not rising.empty:
                st.markdown("**📈 上升期技能 TOP10**")
                fig_rising = px.bar(
                    rising.sort_values("trend_slope", ascending=True),
                    x="trend_slope", y="skill", orientation="h",
                    title="需求增长斜率", color="trend_slope",
                    color_continuous_scale="greens",
                    labels={"trend_slope": "月均需求增量", "skill": "技能"},
                    hover_data=["total_demand", "recent_avg"],
                )
                fig_rising.update_layout(height=300, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_rising, use_container_width=True)
            else:
                st.info("暂无上升期技能（需求数据跨月不足）")

        with col_t2:
            declining = trend_df[trend_df["trend_label"] == "declining"].head(10)
            if not declining.empty:
                st.markdown("**📉 衰退期技能 TOP10**")
                fig_dec = px.bar(
                    declining.sort_values("trend_slope"),
                    x="trend_slope", y="skill", orientation="h",
                    title="需求衰减斜率", color="trend_slope",
                    color_continuous_scale="reds",
                    labels={"trend_slope": "月均需求减量", "skill": "技能"},
                    hover_data=["total_demand", "recent_avg"],
                )
                fig_dec.update_layout(height=300, yaxis={"categoryorder": "total descending"})
                st.plotly_chart(fig_dec, use_container_width=True)
            else:
                st.info("暂无衰退期技能")

        # 完整趋势表
        with st.expander("📋 所有技能趋势明细", expanded=False):
            display_cols = [c for c in ["skill", "total_demand", "months", "trend_label",
                                         "trend_slope", "r_squared", "recent_avg"]
                            if c in trend_df.columns]
            label_map = {"rising": "📈 上升", "stable": "➡️ 稳定", "declining": "📉 衰退"}
            trend_df_display = trend_df[display_cols].copy()
            if "trend_label" in trend_df_display.columns:
                trend_df_display["trend_label"] = trend_df_display["trend_label"].map(label_map)
            st.dataframe(trend_df_display, use_container_width=True, hide_index=True)
    else:
        st.info("需要跨月的数据才能分析趋势。当前数据可能只覆盖单月。")

    # ── 类别薪资对比（已有逻辑）──
    if "category" in jobs.columns:
        st.markdown("---")
        st.subheader("📂 各类别薪资与购买力")

        df_cat = category_stats(jobs)
        if not df_cat.empty and len(df_cat) > 1:
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                fig_cat = px.bar(
                    df_cat.sort_values("平均薪资", ascending=True),
                    x="平均薪资", y="category", orientation="h",
                    title="各类别平均薪资", color="平均薪资",
                    color_continuous_scale="teal",
                    hover_data=["岗位数", "薪资中位"],
                    labels={"category": "类别", "平均薪资": "K/月"},
                )
                fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, height=300)
                st.plotly_chart(fig_cat, use_container_width=True)
            with col_c2:
                real_pp = add_purchasing_power(jobs[jobs["salary_avg"].notna()].copy())
                if "pp_salary" in real_pp.columns and "category" in real_pp.columns:
                    pp_cat = real_pp.groupby("category").agg(
                        raw=("salary_avg", "mean"),
                        adj=("pp_salary", "mean"),
                        cnt=("id", "count"),
                    ).reset_index()
                    pp_cat.columns = ["category", "原始均薪", "购买力均薪", "岗位数"]
                    pp_cat["原始均薪"] = pp_cat["原始均薪"].round(1)
                    pp_cat["购买力均薪"] = pp_cat["购买力均薪"].round(1)
                    pp_melt = pp_cat.melt(
                        id_vars=["category"],
                        value_vars=["原始均薪", "购买力均薪"],
                        var_name="类型", value_name="均薪(K)",
                    )
                    fig_pp = px.bar(
                        pp_melt.sort_values("均薪(K)", ascending=True),
                        x="均薪(K)", y="category", color="类型",
                        orientation="h", barmode="group",
                        title="各类别：原始均薪 vs 购买力均薪",
                        color_discrete_map={
                            "原始均薪": "#00b4d8", "购买力均薪": "#ef476f",
                        },
                        labels={"category": "类别"},
                    )
                    fig_pp.update_layout(
                        yaxis={"categoryorder": "total ascending"}, height=300,
                        legend=dict(orientation="h", y=1.12),
                    )
                    st.plotly_chart(fig_pp, use_container_width=True)
    else:
        st.info("请先运行岗位分类 (classify_dataframe) 以查看类别分析。")

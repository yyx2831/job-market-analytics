"""薪资趋势标签页 — 技能薪资历史走势追踪。"""

from pathlib import Path
from typing import List, Optional, Union

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics.salary_tracker import (
    load_salary_history,
    compute_salary_changes,
    get_available_skills_for_tracking,
    init_salary_history,
)


def render_salary_trend(db_path: Union[str, Path]) -> None:
    """渲染薪资趋势标签页。"""
    import sqlite3

    conn = sqlite3.connect(str(db_path))

    try:
        _render(conn)
    finally:
        conn.close()


def _render(conn) -> None:
    st.subheader("📈 薪资历史追踪")

    # ── 初始化快照区 ──
    col_l, col_r = st.columns([3, 1])
    with col_l:
        st.caption("追踪技能薪资随时间的变化，了解市场动向。")

    with col_r:
        if st.button("📸 生成快照", help="基于当前数据生成薪资快照"):
            count = init_salary_history(conn)
            st.success(f"已生成 {count} 条薪资记录")
            st.rerun()

    # ── 获取可追踪的技能列表 ──
    skills = get_available_skills_for_tracking(conn)
    if not skills:
        st.info(
            "暂无薪资历史数据。\n\n"
            "点击「生成快照」按钮，基于当前数据库生成首次薪资记录。\n"
            "后续每次采集后点一次，即可积累历史趋势。"
        )
        return

    # ── 城市选择 ──
    cities_in_data = load_salary_history(conn)["city"].unique().tolist()
    selected_city = st.selectbox(
        "选择城市", ["全部"] + sorted(cities_in_data),
        key="salary_trend_city",
    )

    city_filter = None if selected_city == "全部" else selected_city

    # ── 1. 薪资变化排行 ──
    st.markdown("---")
    st.markdown("### 🔥 薪资变化排行")

    changes = compute_salary_changes(conn, city=city_filter, top_n=20)
    if not changes.empty:
        rising = changes[changes["change"] > 0].head(10)
        falling = changes[changes["change"] < 0].head(10)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**📈 涨幅 TOP**")
            if not rising.empty:
                fig_up = px.bar(
                    rising.sort_values("change"),
                    x="change", y="skill", orientation="h",
                    title=f"{selected_city} 技能薪资涨幅",
                    color="change", color_continuous_scale="greens",
                    hover_data=["first_salary", "last_salary", "change_pct"],
                    labels={"change": "涨薪(K/月)", "skill": "技能"},
                )
                fig_up.update_layout(height=350, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_up, use_container_width=True)
            else:
                st.info("暂无涨幅数据")

        with col_b:
            st.markdown("**📉 跌幅 TOP**")
            if not falling.empty:
                fig_down = px.bar(
                    falling.sort_values("change"),
                    x="change", y="skill", orientation="h",
                    title=f"{selected_city} 技能薪资跌幅",
                    color="change", color_continuous_scale="reds",
                    hover_data=["first_salary", "last_salary", "change_pct"],
                    labels={"change": "降薪(K/月)", "skill": "技能"},
                )
                fig_down.update_layout(height=350, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_down, use_container_width=True)
            else:
                st.info("暂无跌幅数据")

        with st.expander("📋 完整变化数据", expanded=False):
            st.dataframe(
                changes[[
                    "city", "skill", "first_salary", "last_salary",
                    "change", "change_pct", "first_date", "last_date",
                ]],
                use_container_width=True, hide_index=True,
                column_config={
                    "first_salary": "初始均薪(K)",
                    "last_salary": "最新均薪(K)",
                    "change": "变化(K)",
                    "change_pct": st.column_config.NumberColumn("变化(%)", format="%.1f%%"),
                    "first_date": "起始日期",
                    "last_date": "最新日期",
                },
            )

    # ── 2. 指定技能趋势 ──
    st.markdown("---")
    st.markdown("### 📊 技能薪资走势")

    current_skills = get_available_skills_for_tracking(conn)
    if city_filter:
        city_skills = load_salary_history(conn, city=city_filter)["skill"].unique().tolist()
        available = sorted(set(current_skills) & set(city_skills))
    else:
        available = sorted(current_skills)

    selected_skills: List[str] = st.multiselect(
        "选择技能（可多选）",
        available,
        default=available[:3] if len(available) >= 3 else available,
        key="salary_trend_skills",
    )

    if selected_skills:
        trend_data = load_salary_history(conn, city=city_filter)
        if not trend_data.empty:
            filtered = trend_data[trend_data["skill"].isin(selected_skills)]
            if not filtered.empty:
                filtered["图例"] = filtered["city"] + " · " + filtered["skill"]

                fig_trend = px.line(
                    filtered.sort_values("record_date"),
                    x="record_date", y="avg_salary",
                    color="图例",
                    title=f"{selected_city} — 技能薪资走势",
                    markers=True,
                    line_shape="spline",
                    labels={
                        "record_date": "日期",
                        "avg_salary": "平均薪资(K/月)",
                    },
                )
                fig_trend.update_layout(height=450, hovermode="x unified")
                st.plotly_chart(fig_trend, use_container_width=True)

                if st.checkbox("显示薪资分位区间", value=False):
                    fig_range = go.Figure()
                    for _, row in filtered.iterrows():
                        label = f"{row['city']} · {row['skill']}"
                        fig_range.add_trace(go.Scatter(
                            x=[row["record_date"], row["record_date"]],
                            y=[row["p25_salary"], row["p75_salary"]],
                            mode="lines",
                            line=dict(width=0),
                            showlegend=False,
                        ))
                        fig_range.add_trace(go.Scatter(
                            x=[row["record_date"]] * 2,
                            y=[row["p25_salary"], row["p75_salary"]],
                            mode="markers",
                            marker=dict(size=4, symbol="line-ns"),
                            name=label,
                            showlegend=(row.name == 0),
                        ))
                    st.plotly_chart(fig_range, use_container_width=True)
            else:
                st.info("所选技能在当前筛选条件下无历史数据。")

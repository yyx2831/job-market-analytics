"""岗位明细表格标签页 — 可排序、可过滤的完整数据列表。"""

import pandas as pd
import streamlit as st


def render_job_table(jobs: pd.DataFrame) -> None:
    """渲染明细标签页 — 可筛选、可排序的岗位列表。"""
    st.subheader("📋 岗位明细")
    st.caption(f"共 {len(jobs)} 个岗位 | 可排序、搜索")

    show_cols = [
        "title", "company_name", "city", "district", "salary_text",
        "experience", "education", "industry", "skills", "publish_time", "source"
    ]
    available = [c for c in show_cols if c in jobs.columns]
    display = jobs[available].copy()

    # 格式化薪资
    if "salary_avg" in jobs.columns:
        display.insert(4, "月薪(K)", jobs["salary_avg"].fillna(0).round(1).astype(str))

    st.dataframe(
        display.sort_values("publish_time", ascending=False, na_position="last")
        if "publish_time" in available else display,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "publish_time": st.column_config.DatetimeColumn("发布日期", format="YYYY-MM-DD"),
            "title": st.column_config.TextColumn("岗位", width="large"),
        },
    )

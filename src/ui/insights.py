"""观点/洞察标签页 — 基于数据自动生成分析文本。"""

import streamlit as st
from src.insights import generate_insights


def render_insights(jobs) -> None:
    """渲染洞察标签页 — 自动生成的分析观点。"""
    st.subheader("🧠 市场洞察")
    st.caption("基于当前筛选数据自动生成的智能分析")

    insights = generate_insights(jobs)
    if not insights:
        st.warning("当前数据范围暂无足够数据生成洞察。")
        return

    for insight in insights:
        with st.expander(getattr(insight, "title", "洞察"), expanded=len(insights) <= 3):
            st.markdown(getattr(insight, "body", ""))

"""学习路线标签页 — 技能学习路径、市场数据、ROI 分析。"""

import streamlit as st
from src.skill_guide import get_all_guides, get_learning_path_summary


def render_skill_guide() -> None:
    """渲染技能学习路线指南标签页。"""
    st.subheader("📚 技能学习路线")
    st.caption("基于真实招聘数据，分析每个技能的市场需求、学习路径、时间投入，帮你制定学习计划。")

    # 顶部总结
    summary = get_learning_path_summary()
    with st.expander("🎯 综合学习建议", expanded=True):
        st.markdown(summary)

    st.markdown("---")

    # 单个技能详细拆解
    guides = sorted(get_all_guides(), key=lambda g: g.market_data.get("roi_score", 0), reverse=True)

    for g in guides:
        roi = g.market_data.get("roi_score", 0)
        if roi >= 60:
            badge = "🥇"
        elif roi >= 40:
            badge = "🥈"
        else:
            badge = "🥉"

        with st.expander(
            f"{badge} {g.skill} — 需求 {g.market_data['demand']} 个岗位，"
            f"中位 {g.market_data['median_salary']}/月，ROI {roi}"
        ):
            col1, col2 = st.columns([3, 2])

            with col1:
                st.markdown(f"**{g.summary}**")
                st.markdown(f"> {g.why_learn}")

                st.markdown("##### 📖 学习路径")
                total = g.total_hours
                st.progress(min(total / 400, 1.0), text=f"总学时: ~{total}h")

                for sub in g.subs:
                    level_emoji = {"入门": "🟢", "进阶": "🟡", "精通": "🔴"}.get(sub.level, "⚪")
                    st.markdown(
                        f"{level_emoji} **{sub.name}** ({sub.level}, ~{sub.hours}h) — {sub.desc}"
                    )

            with col2:
                st.markdown("##### 🔗 共现技能")
                for cs in g.co_skills[:5]:
                    st.markdown(f"- {cs}")

                st.markdown("##### 💼 典型岗位")
                for role in g.typical_roles[:4]:
                    st.markdown(f"- {role}")

                st.markdown("##### 📝 推荐资源")
                st.caption(g.resources_hint)

                st.markdown(f"##### ⚡ 难度: {g.difficulty}")

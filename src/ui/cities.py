"""城市比较标签页 — 多城市薪资对比、岗位分布、购买力分析。"""

import pandas as pd
import plotly.express as px
import streamlit as st


def render_city_compare(jobs_all: pd.DataFrame) -> None:
    """渲染城市对比标签页 — 多城市薪资、购买力、岗位数横向对比。"""
    st.subheader("🌍 城市对比")
    st.caption("跨城市薪资水平、购买力调整薪资、岗位数量横向对比")

    real = jobs_all[jobs_all["source"] == "51job"]
    real = real[real["salary_avg"].notna()]
    cities = sorted(real["city"].unique())

    if len(cities) < 2:
        st.info("需要至少两个城市的数据才能对比。")
        return

    from src.analytics.purchasing_power import city_comparison_adjusted

    # 原始城市汇总
    df_cmp = city_comparison_adjusted(real)
    if "city" in df_cmp.columns:
        df_cmp = df_cmp.rename(columns={"city": "城市"})

    # 两列：数据表 + 柱状图
    col1, col2 = st.columns(2)
    with col1:
        show_cols = ["城市", "岗位数", "原始均薪", "购买力均薪", "成本指数"]
        available = [c for c in show_cols if c in df_cmp.columns]
        st.dataframe(df_cmp[available], hide_index=True, use_container_width=True)
    with col2:
        # 双柱图：原始 vs 购买力
        if "原始均薪" in df_cmp.columns and "购买力均薪" in df_cmp.columns:
            df_melt = df_cmp.melt(
                id_vars=["城市"], value_vars=["原始均薪", "购买力均薪"],
                var_name="类型", value_name="均薪(K)"
            )
            fig = px.bar(df_melt, x="城市", y="均薪(K)", color="类型",
                         barmode="group",
                         title="💰 原始均薪 vs 购买力均薪（成都等值）",
                         color_discrete_map={"原始均薪": "#00b4d8", "购买力均薪": "#ef476f"},
                         labels={"均薪(K)": "月薪(K)"})
            fig.update_layout(height=380, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig, use_container_width=True)

    # 购买力排名
    st.markdown("---")
    st.subheader("🏠 购买力排名")
    st.caption("将各城市薪资按生活成本折算为「成都等值」，消除地域偏差")

    if "购买力均薪" in df_cmp.columns:
        df_pp = df_cmp.sort_values("购买力均薪", ascending=False).copy()
        df_pp["排名"] = range(1, len(df_pp) + 1)

        col3, col4 = st.columns(2)
        with col3:
            # 购买力条形图
            fig3 = px.bar(
                df_pp.sort_values("购买力均薪", ascending=True).tail(15),
                x="购买力均薪", y="城市", orientation="h",
                title="🏆 购买力均薪 Top15 城市",
                color="购买力均薪", color_continuous_scale="greens",
                labels={"购买力均薪": "成都等值月薪(K)"},
            )
            fig3.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400)
            st.plotly_chart(fig3, use_container_width=True)
        with col4:
            # 成本指数一目了然
            if "成本指数" in df_cmp.columns:
                df_cost = df_cmp[df_cmp["成本指数"] > 0].sort_values("成本指数", ascending=False)
                fig4 = px.bar(
                    df_cost, x="成本指数", y="城市", orientation="h",
                    title="📊 城市生活成本指数（成都=100）",
                    color="成本指数", color_continuous_scale="oranges",
                    labels={"成本指数": "生活成本指数"},
                )
                fig4.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400)
                st.plotly_chart(fig4, use_container_width=True)

    # 岗位数 vs 薪资散点
    st.markdown("---")
    st.subheader("📈 岗位机会 vs 薪资水平")
    fig2 = px.scatter(df_cmp, x="岗位数", y="原始均薪", text="城市",
                      title="岗位数 vs 原始薪资水平",
                      size="岗位数", color="原始均薪",
                      color_continuous_scale="bluered",
                      labels={"原始均薪": "平均月薪(K/月)"})
    fig2.update_traces(textposition="top center")
    st.plotly_chart(fig2, use_container_width=True)

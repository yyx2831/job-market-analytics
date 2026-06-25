"""薪资分析标签页 — 经验/学历/规模 薪资分布 + 年薪换算。"""

import pandas as pd
import plotly.express as px
import streamlit as st


def render_salary_analysis(jobs: pd.DataFrame) -> None:
    """渲染薪资分析标签页 — 按经验、学历、公司规模拆分。"""
    st.subheader("💰 薪资深度分析")
    st.caption("按经验/学历/公司规模拆解薪资分布，助力精准定位")

    real = jobs.dropna(subset=["salary_avg"])
    if real.empty:
        st.warning("当前筛选条件没有薪资数据。")
        return

    tabs = st.tabs(["经验", "学历", "规模", "年薪换算"])

    with tabs[0]:
        if "experience" in real.columns and real["experience"].notna().any():
            exp = real.groupby("experience")["salary_avg"].agg(["mean", "count"]).reset_index()
            exp.columns = ["经验", "平均薪资", "数量"]
            exp["平均薪资"] = exp["平均薪资"].round(1)
            col_a, col_b = st.columns(2)
            with col_a:
                st.dataframe(exp, hide_index=True, use_container_width=True)
            with col_b:
                fig_exp = px.box(real, x="experience", y="salary_avg",
                                 title="经验 vs 薪资分布",
                                 color="experience",
                                 labels={"salary_avg": "月薪(K/月)", "experience": "经验"})
                fig_exp.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig_exp, use_container_width=True)
        else:
            st.info("暂无经验字段数据。")

    with tabs[1]:
        if "education" in real.columns and real["education"].notna().any():
            edu = real.groupby("education")["salary_avg"].agg(["mean", "count"]).reset_index()
            edu.columns = ["学历", "平均薪资", "数量"]
            edu["平均薪资"] = edu["平均薪资"].round(1)
            col_a, col_b = st.columns(2)
            with col_a:
                st.dataframe(edu, hide_index=True, use_container_width=True)
            with col_b:
                fig_edu = px.box(real, x="education", y="salary_avg",
                                 title="学历 vs 薪资分布",
                                 color="education",
                                 labels={"salary_avg": "月薪(K/月)", "education": "学历"})
                fig_edu.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig_edu, use_container_width=True)
        else:
            st.info("暂无学历字段数据。")

    with tabs[2]:
        if "company_size" in real.columns and real["company_size"].notna().any():
            size = real.groupby("company_size")["salary_avg"].agg(["mean", "count"]).reset_index()
            size.columns = ["公司规模", "平均薪资", "数量"]
            size["平均薪资"] = size["平均薪资"].round(1)
            col_a, col_b = st.columns(2)
            with col_a:
                st.dataframe(size, hide_index=True, use_container_width=True)
            with col_b:
                fig_size = px.box(real, x="company_size", y="salary_avg",
                                  title="公司规模 vs 薪资分布",
                                  color="company_size",
                                  labels={"salary_avg": "月薪(K/月)", "company_size": "公司规模"})
                fig_size.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig_size, use_container_width=True)
        else:
            st.info("暂无公司规模数据。")

    with tabs[3]:
        _render_annual_salary(real)


def _render_annual_salary(jobs: pd.DataFrame) -> None:
    """年薪换算 — 14薪真实年薪 + 薪数分布 + 12薪 vs 13+薪对比。"""
    import plotly.graph_objects as go
    from src.analytics.salary_parser import (
        enhance_salary_columns, months_distribution, fourteen_month_analysis,
    )

    enhanced = enhance_salary_columns(jobs)
    analysis = fourteen_month_analysis(enhanced)

    # ── KPI ──
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("12薪岗位", f"{analysis['cnt_12m']} 个", f"均薪 ¥{analysis['avg_12m']:,.0f}")
    with col_b:
        st.metric("13+薪岗位", f"{analysis['cnt_13p']} 个", f"均薪 ¥{analysis['avg_13p']:,.0f}")
    with col_c:
        premium = 0
        if analysis["avg_12m"] > 0:
            premium = (analysis["avg_13p"] / analysis["avg_12m"] - 1) * 100
        st.metric("多薪月薪溢价", f"{premium:+.1f}%", "13+薪岗底薪更高" if premium > 0 else "")
    with col_d:
        ann_12 = analysis["avg_12m"] * 12 if analysis["avg_12m"] else 0
        ann_13 = analysis["avg_13p"] * 14 if analysis["avg_13p"] else 0
        st.metric("年薪差距(估)", f"¥{ann_13 - ann_12:+,.0f}", "13+薪额外收入" if ann_13 > ann_12 else "")

    st.markdown("---")

    # ── 薪数分布 + 箱线 ──
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        md = months_distribution(enhanced)
        fig_pie = go.Figure(data=[go.Pie(
            labels=list(md.keys()), values=list(md.values()), hole=0.4,
            marker_colors=["#90be6d", "#f9c74f", "#f9844a", "#f3722c", "#f94144"],
        )])
        fig_pie.update_layout(title="年薪月数分布", height=350, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_m2:
        ec = enhanced.dropna(subset=["salary_avg", "salary_months"])
        ec["月数标签"] = ec["salary_months"].apply(lambda m: f"{int(m)}薪" if m >= 12 else "未知")
        fig_box = px.box(ec, x="月数标签", y="salary_avg",
                         title="各薪数月薪分布", color="月数标签",
                         labels={"salary_avg": "月薪(元)", "月数标签": ""})
        fig_box.update_layout(showlegend=False, height=350, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_box, use_container_width=True)

    # ── 年薪直方图 ──
    st.markdown("### 💰 实际年薪分布")
    st.caption("月薪 × 年薪月数 = 实际年薪，含 12/13/14/15/16+ 薪")
    ea = enhanced.dropna(subset=["salary_annual"])
    if not ea.empty:
        fig_ann = px.histogram(ea, x="salary_annual", nbins=40,
                               title="实际年薪分布",
                               labels={"salary_annual": "年薪(元)", "count": "岗位数"},
                               color_discrete_sequence=["#00b4d8"])
        fig_ann.add_vline(x=ea["salary_annual"].median(), line_dash="dash",
                          line_color="orange", annotation_text=f"中位 ¥{ea['salary_annual'].median():,.0f}")
        fig_ann.add_vline(x=ea["salary_annual"].quantile(0.75), line_dash="dot",
                          line_color="green", annotation_text=f"P75 ¥{ea['salary_annual'].quantile(0.75):,.0f}")
        fig_ann.update_layout(height=350, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_ann, use_container_width=True)

        if "city" in ea.columns and ea["city"].nunique() > 1:
            st.markdown("### 🌍 分城市年薪对比")
            city_ann = ea.groupby("city").agg(
                岗位数=("salary_annual", "count"),
                年薪均=("salary_annual", "mean"),
                年薪中位=("salary_annual", "median"),
            ).round(0).sort_values("年薪中位", ascending=False)
            st.dataframe(city_ann, use_container_width=True)

    # ── 各城市溢价 ──
    by_city = analysis.get("by_city", [])
    if by_city:
        st.markdown("---")
        st.markdown("### 🏙️ 城市多薪月溢价")
        st.caption("13+薪 vs 12薪 岗位月薪差异")
        df_cc = pd.DataFrame(by_city)
        fig_cc = px.bar(df_cc.sort_values("16薪溢价"), x="城市", y="16薪溢价",
                        title="多薪月溢价率(%)", color="16薪溢价",
                        color_continuous_scale="rdylgn", labels={"16薪溢价": "溢价%"})
        fig_cc.update_layout(height=350)
        st.plotly_chart(fig_cc, use_container_width=True)

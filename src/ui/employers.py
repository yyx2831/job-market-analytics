"""雇主画像标签页 — 扎根城市：公司生态图谱、薪酬梯队、技术栈聚类、增长信号。"""

import json
from collections import Counter
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ── Helpers ──

def _extract_skills(series: pd.Series) -> Counter:
    c = Counter()
    for val in series.dropna():
        try:
            items = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(val).split(",") if s.strip()]
        for s in items:
            c[str(s).strip()] += 1
    return c


def _company_skills(jobs: pd.DataFrame) -> Dict[str, str]:
    """返回 {公司: '技能1, 技能2, 技能3'} """
    result = {}
    for company in jobs["company_name"].dropna().unique():
        cj = jobs[jobs["company_name"] == company]
        skills = _extract_skills(cj["skills"]).most_common(5)
        result[company] = ", ".join(f"{s}({n})" for s, n in skills) if skills else "-"
    return result


def _is_local(c: str, city: str) -> Optional[bool]:
    """判断公司是否本地注册（简单规则：公司名含城市名）。"""
    if pd.isna(c):
        return None
    c = str(c)
    city_short = city.replace("市", "")
    # 公司名含城市名 → 大概率本地
    if city_short in c or city in c:
        return True
    # 公司名含其他知名城市 → 外地总部
    for other in ["北京", "上海", "深圳", "广州", "杭州", "武汉", "南京", "西安", "重庆", "天津", "长沙", "苏州", "合肥"]:
        if other != city_short and other in c:
            return False
    return True  # 未匹配 → 倾向本地


# ── Main Render ──

def render_employers(jobs_all: pd.DataFrame) -> None:
    """渲染城市扎根雇主分析页。"""
    st.subheader("🏢 扎根城市 · 雇主深度画像")

    if "city" not in jobs_all.columns or jobs_all.empty:
        st.info("暂无城市数据。")
        return

    # ── 城市选择器 ──
    city_options = sorted(jobs_all["city"].dropna().unique())
    if "成都" in city_options:
        default_idx = city_options.index("成都")
    else:
        default_idx = 0

    col_sel, col_kpi1, col_kpi2, col_kpi3 = st.columns([3, 2, 2, 2])
    with col_sel:
        selected_city = st.selectbox("🎯 聚焦城市", city_options, index=default_idx)

    jobs = jobs_all[jobs_all["city"] == selected_city].copy()
    if jobs.empty:
        st.info(f"{selected_city} 暂无数据。")
        return

    # ── KPI Bar ──
    total_jobs = len(jobs)
    total_co = jobs["company_name"].nunique() if "company_name" in jobs.columns else 0
    real_sal = jobs[jobs["salary_avg"].notna()]
    med_sal = real_sal["salary_avg"].median() if not real_sal.empty else 0
    # 估算本地公司数
    if "company_name" in jobs.columns:
        local_co = len(set(
            jobs[jobs["company_name"].dropna().apply(lambda x: _is_local(x, selected_city))]["company_name"]
        ))
    else:
        local_co = total_co

    with col_kpi1:
        st.metric("招聘岗位", f"{total_jobs} 个")
    with col_kpi2:
        st.metric("活跃雇主", f"{total_co} 家", f"本地 {local_co} 家")
    with col_kpi3:
        st.metric("薪资中位", f"{med_sal:,.0f} 元/月")

    st.markdown("---")

    # ══════════════════════════════════════════
    # Section 1: 公司生态全景
    # ══════════════════════════════════════════
    st.subheader(f"🔍 {selected_city} 公司生态全景")

    if "company_name" not in jobs.columns:
        st.info("暂无公司数据。")
        return

    # 1a. 雇主规模 × 薪资散点图
    co_agg = jobs.groupby("company_name").agg(
        岗位数=("id", "count"),
        平均薪资=("salary_avg", "mean"),
        行业=("industry", "first"),
        规模=("company_size", "first"),
        融资=("financing_stage", "first"),
    ).reset_index()
    co_agg["平均薪资"] = co_agg["平均薪资"].round(0)
    co_agg["本地"] = co_agg["company_name"].apply(lambda x: _is_local(x, selected_city))

    col_left, col_right = st.columns(2)

    with col_left:
        fig_scatter = px.scatter(
            co_agg.dropna(subset=["平均薪资"]),
            x="岗位数", y="平均薪资",
            size="岗位数", color="本地",
            color_discrete_map={True: "#00b4d8", False: "#ff6b6b"},
            hover_name="company_name",
            hover_data={"行业": True, "规模": True, "本地": False},
            title=f"🏙️ 雇主矩阵：规模 × 薪资",
            labels={"平均薪资": "平均薪资(元/月)", "岗位数": "招聘岗位数", "本地": "本地企业"},
            size_max=30,
        )
        # 标注平均值
        x_med = co_agg["岗位数"].median()
        y_med = co_agg["平均薪资"].median()
        fig_scatter.add_hline(y=y_med, line_dash="dash", line_color="gray", opacity=0.5,
                              annotation_text=f"薪资中位{int(y_med):,}")
        fig_scatter.add_vline(x=x_med, line_dash="dash", line_color="gray", opacity=0.5,
                              annotation_text=f"岗位中位{int(x_med)}")
        fig_scatter.update_layout(height=450, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_right:
        # 本地 vs 外地 对比
        local_jobs = jobs[jobs["company_name"].apply(lambda x: _is_local(x, selected_city))]
        nonlocal_jobs = jobs[~jobs["company_name"].apply(lambda x: _is_local(x, selected_city))]

        local_stats = {
            "分类": ["🏠 本地企业", "✈️ 外地分部"],
            "公司数": [local_jobs["company_name"].nunique(), nonlocal_jobs["company_name"].nunique()],
            "岗位数": [len(local_jobs), len(nonlocal_jobs)],
        }
        if not local_jobs.empty and not nonlocal_jobs.empty:
            local_sal = local_jobs["salary_avg"].dropna()
            nonlocal_sal = nonlocal_jobs["salary_avg"].dropna()
            local_stats["平均薪资"] = [
                int(local_sal.mean()) if not local_sal.empty else 0,
                int(nonlocal_sal.mean()) if not nonlocal_sal.empty else 0,
            ]
            local_stats["薪资中位"] = [
                int(local_sal.median()) if not local_sal.empty else 0,
                int(nonlocal_sal.median()) if not nonlocal_sal.empty else 0,
            ]

        df_lv = pd.DataFrame(local_stats)
        st.markdown("**🏠 本地 vs ✈️ 外地分部**")
        st.dataframe(df_lv, use_container_width=True, hide_index=True)

        # 薪酬对比条
        if not local_jobs.empty and not nonlocal_jobs.empty:
            fig_lv = go.Figure()
            for label, df_sub, color in [
                ("本地企业", local_jobs, "#00b4d8"),
                ("外地分部", nonlocal_jobs, "#ff6b6b"),
            ]:
                sal = df_sub["salary_avg"].dropna()
                if sal.empty:
                    continue
                fig_lv.add_trace(go.Box(y=sal, name=label, marker_color=color,
                                        boxmean="sd"))
            fig_lv.update_layout(
                title="本地 vs 外地 薪酬箱线对比",
                height=280, margin=dict(t=40, b=0, l=0, r=0),
                yaxis_title="月薪(元)",
            )
            st.plotly_chart(fig_lv, use_container_width=True)

    # ══════════════════════════════════════════
    # Section 2: 行业扎根
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader(f"📂 {selected_city} 行业扎根分析")

    col_i1, col_i2 = st.columns(2)

    with col_i1:
        if "industry" in jobs.columns:
            ind = jobs["industry"].dropna()
            if not ind.empty:
                ind_counts = ind.value_counts().head(12)
                fig_ind = px.bar(
                    x=ind_counts.values, y=ind_counts.index, orientation="h",
                    title="行业岗位分布 TOP12",
                    color=ind_counts.values, color_continuous_scale="teal",
                    labels={"x": "岗位数", "y": "行业"},
                )
                fig_ind.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_ind, use_container_width=True)
            else:
                st.info("行业数据不足")

    with col_i2:
        # 行业 × 薪资
        if "industry" in jobs.columns and "salary_avg" in jobs.columns:
            ind_sal = jobs.dropna(subset=["industry", "salary_avg"]).groupby("industry").agg(
                岗位数=("id", "count"),
                均薪=("salary_avg", "mean"),
                高薪=("salary_max", "mean"),
            ).round(0).sort_values("岗位数", ascending=False).head(12)

            if not ind_sal.empty:
                fig_ind2 = px.scatter(
                    ind_sal.reset_index(), x="均薪", y="岗位数",
                    size="岗位数", color="高薪",
                    hover_name="industry",
                    title="行业薪酬 × 需求规模",
                    labels={"均薪": "平均薪资(元/月)", "岗位数": "岗位数", "高薪": "薪资上限(元)"},
                    size_max=40, color_continuous_scale="viridis",
                )
                fig_ind2.update_layout(height=400)
                st.plotly_chart(fig_ind2, use_container_width=True)

    # ══════════════════════════════════════════
    # Section 3: 规模 & 融资
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader("📏 规模 / 融资分析")

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        if "company_size" in jobs.columns:
            sz = jobs["company_size"].dropna()
            if not sz.empty:
                size_order = ["少于50人", "50-150人", "150-500人", "500-1000人",
                              "1000-5000人", "5000-10000人", "10000人以上"]
                sz_counts = sz.value_counts()

                # 按规则排序
                ordered = []
                for s in size_order:
                    if s in sz_counts:
                        ordered.append((s, sz_counts[s]))
                for s, v in sz_counts.items():
                    if s not in size_order:
                        ordered.append((s, v))

                df_sz = pd.DataFrame(ordered, columns=["规模", "岗位数"])
                fig_sz = px.bar(df_sz, x="规模", y="岗位数",
                                title="企业规模分布",
                                color="岗位数", color_continuous_scale="blues",
                                labels={"规模": "", "岗位数": "岗位数"})
                fig_sz.update_layout(height=350)
                st.plotly_chart(fig_sz, use_container_width=True)

                # 规模 × 薪资
                sz_sal = jobs.dropna(subset=["company_size", "salary_avg"]).groupby("company_size")["salary_avg"].mean().round(0)
                if not sz_sal.empty:
                    sz_sal = sz_sal.reset_index()
                    sz_sal.columns = ["规模", "均薪"]
                    fig_sz2 = px.bar(sz_sal, x="规模", y="均薪",
                                     title="各规模企业均薪",
                                     color="均薪", color_continuous_scale="greens",
                                     labels={"均薪": "元/月", "规模": ""})
                    fig_sz2.update_layout(height=280)
                    st.plotly_chart(fig_sz2, use_container_width=True)
            else:
                st.info("暂无规模数据")

    with col_s2:
        if "financing_stage" in jobs.columns:
            fin = jobs["financing_stage"].dropna()
            if not fin.empty:
                fin_counts = fin.value_counts()
                stage_order = ["未融资", "天使轮", "A轮", "B轮", "C轮及以上", "上市公司", "不需要融资"]
                fin_ordered = []
                for s in stage_order:
                    if s in fin_counts:
                        fin_ordered.append((s, fin_counts[s]))
                for s, v in fin_counts.items():
                    if s not in stage_order:
                        fin_ordered.append((s, v))

                if fin_ordered:
                    df_fin = pd.DataFrame(fin_ordered, columns=["融资阶段", "岗位数"])
                    fig_fin = px.pie(df_fin, values="岗位数", names="融资阶段",
                                     title="融资阶段分布", hole=0.4,
                                     color_discrete_sequence=px.colors.qualitative.Set3)
                    fig_fin.update_layout(height=350)
                    st.plotly_chart(fig_fin, use_container_width=True)

                # 融资 × 薪资
                fin_sal = jobs.dropna(subset=["financing_stage", "salary_avg"]).groupby("financing_stage")["salary_avg"].mean().round(0)
                if not fin_sal.empty:
                    fin_sal = fin_sal.reset_index()
                    fin_sal.columns = ["融资阶段", "均薪"]
                    fig_fin2 = px.bar(fin_sal, x="融资阶段", y="均薪",
                                      title="各融资阶段均薪",
                                      color="均薪", color_continuous_scale="oranges",
                                      labels={"均薪": "元/月", "融资阶段": ""})
                    fig_fin2.update_layout(height=280)
                    st.plotly_chart(fig_fin2, use_container_width=True)
            else:
                st.info("暂无融资数据")

    # ══════════════════════════════════════════
    # Section 4: 成长信号
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader("📈 雇主成长信号")

    if "publish_time" in jobs.columns and not jobs.empty:
        jobs_dt = jobs.copy()
        jobs_dt["publish_dt"] = pd.to_datetime(jobs_dt["publish_time"], format="mixed", errors="coerce")
        jobs_dt = jobs_dt[jobs_dt["publish_dt"].notna()]

        if not jobs_dt.empty and jobs_dt["publish_dt"].nunique() > 1:
            jobs_dt["month"] = jobs_dt["publish_dt"].dt.to_period("M").astype(str)
            months_sorted = sorted(jobs_dt["month"].unique())

            if len(months_sorted) >= 2:
                col_g1, col_g2 = st.columns(2)

                with col_g1:
                    # 公司月度招聘趋势
                    last2 = months_sorted[-2:]
                    co_month = jobs_dt.groupby(["company_name", "month"]).size().reset_index(name="cnt")
                    co_recent = co_month[co_month["month"].isin(last2)]

                    growth_signals = []
                    for company in co_recent["company_name"].unique():
                        cd = co_recent[co_recent["company_name"] == company]
                        m0 = cd[cd["month"] == last2[0]]["cnt"].sum() if last2[0] in cd["month"].values else 0
                        m1 = cd[cd["month"] == last2[1]]["cnt"].sum() if last2[1] in cd["month"].values else 0
                        if m0 > 0:
                            growth = (m1 - m0) / m0
                            growth_signals.append({
                                "公司": company, "上月": int(m0), "本月": int(m1),
                                "增长": f"{growth:+.0%}", "_growth": growth,
                            })

                    if growth_signals:
                        df_growth = pd.DataFrame(growth_signals).sort_values("_growth", ascending=False)
                        rising = df_growth[df_growth["_growth"] > 0].head(10)
                        if not rising.empty:
                            st.markdown("**🚀 近期扩招最猛的公司**")
                            st.dataframe(
                                rising[["公司", "上月", "本月", "增长"]],
                                use_container_width=True, hide_index=True,
                            )

                with col_g2:
                    # 新进入的公司（之前没招过、最近开始招）
                    old_months = set(months_sorted[:-1])
                    latest_m = months_sorted[-1]
                    latest_co = set(jobs_dt[jobs_dt["month"] == latest_m]["company_name"].unique())
                    old_co = set(jobs_dt[jobs_dt["month"].isin(old_months)]["company_name"].unique())
                    newcomers = latest_co - old_co
                    if newcomers:
                        st.markdown(f"**🆕 本月新进雇主 ({len(newcomers)} 家)**")
                        ncc = jobs_dt[jobs_dt["company_name"].isin(newcomers) & (jobs_dt["month"] == latest_m)]
                        nc_agg = ncc.groupby("company_name").agg(
                            岗位数=("id", "count"),
                            行业=("industry", "first"),
                        ).sort_values("岗位数", ascending=False).head(10)
                        st.dataframe(nc_agg, use_container_width=True)

    # ══════════════════════════════════════════
    # Section 5: 技术栈生态
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader(f"🛠️ {selected_city} 技术栈生态")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        # Top 技能排行
        all_skills = _extract_skills(jobs["skills"])
        if all_skills:
            top_skills = all_skills.most_common(15)
            df_sk = pd.DataFrame(top_skills, columns=["技能", "需求数"])
            fig_sk = px.bar(
                df_sk, x="需求数", y="技能", orientation="h",
                title="🔥 Top15 技能需求",
                color="需求数", color_continuous_scale="plasma",
            )
            fig_sk.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_sk, use_container_width=True)

    with col_t2:
        # 技能 × 薪资
        skill_sal_data = []
        for skill, _ in all_skills.most_common(30):
            mask = jobs["skills"].astype(str).str.contains(skill, na=False, regex=False)
            sj = jobs[mask & jobs["salary_avg"].notna()]
            if not sj.empty:
                skill_sal_data.append({
                    "技能": skill, "均薪": int(sj["salary_avg"].mean()),
                    "岗位数": len(sj),
                })
        if skill_sal_data:
            df_ss = pd.DataFrame(skill_sal_data).sort_values("均薪", ascending=False).head(15)
            fig_ss = px.bar(
                df_ss.sort_values("均薪"), x="均薪", y="技能", orientation="h",
                title="💰 技能薪酬排行榜",
                color="均薪", color_continuous_scale="rdylgn",
                hover_data=["岗位数"],
                labels={"均薪": "该技能岗位均薪(元/月)"},
            )
            fig_ss.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_ss, use_container_width=True)

    # ══════════════════════════════════════════
    # Section 6: 薪资梯队
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader(f"💰 {selected_city} 薪资梯队")
    st.caption("按平均薪资将公司分为四档，分析各梯队特征")

    if not co_agg.empty and "平均薪资" in co_agg.columns:
        sal_valid = co_agg.dropna(subset=["平均薪资"])
        if len(sal_valid) >= 10:
            sal_valid["薪资梯队"] = pd.qcut(
                sal_valid["平均薪资"], q=4,
                labels=["T4-入门", "T3-标准", "T2-优质", "T1-顶薪"]
            )
            tier_stats = sal_valid.groupby("薪资梯队", observed=True).agg(
                公司数=("company_name", "count"),
                均薪=("平均薪资", "mean"),
                均岗数=("岗位数", "mean"),
            ).round(0)
            tier_stats["均薪"] = tier_stats["均薪"].astype(int)
            tier_stats["均岗数"] = tier_stats["均岗数"].astype(int)

            cols_tier = st.columns(4)
            tier_colors = {"T4-入门": "#90be6d", "T3-标准": "#f9c74f",
                           "T2-优质": "#f9844a", "T1-顶薪": "#f94144"}
            for i, (tier_name, row) in enumerate(tier_stats.iterrows()):
                with cols_tier[i]:
                    color = tier_colors.get(tier_name, "#888")
                    st.markdown(
                        f"<div style='background:{color}15;border-left:4px solid {color};"
                        f"padding:12px;border-radius:4px;'>"
                        f"<b>{tier_name}</b><br>"
                        f"{int(row['公司数'])} 家公司<br>"
                        f"均薪 ¥{row['均薪']:,}/月<br>"
                        f"均 {int(row['均岗数'])} 岗/家</div>",
                        unsafe_allow_html=True,
                    )

            # 各梯队典型公司
            with st.expander("查看各梯队公司明细", expanded=False):
                for tier_name in ["T1-顶薪", "T2-优质", "T3-标准", "T4-入门"]:
                    subset = sal_valid[sal_valid["薪资梯队"] == tier_name].sort_values("平均薪资", ascending=False).head(5)
                    if subset.empty:
                        continue
                    st.markdown(f"**{tier_name}**  (均薪 ¥{int(subset['平均薪资'].mean()):,})")
                    st.dataframe(
                        subset[["company_name", "岗位数", "平均薪资", "行业", "规模"]]
                        .rename(columns={"company_name": "公司"}),
                        use_container_width=True, hide_index=True,
                    )

    # ══════════════════════════════════════════
    # Section 7: 全量雇主表
    # ══════════════════════════════════════════
    st.markdown("---")
    st.subheader("📋 雇主全景表")

    comp_skills = _company_skills(jobs)
    full_table = co_agg.copy()
    full_table["核心技能"] = full_table["company_name"].map(comp_skills)
    full_table["本地"] = full_table["本地"].map({True: "🏠", False: "✈️"})
    full_table = full_table.sort_values("岗位数", ascending=False)

    show_cols = [c for c in ["company_name", "本地", "岗位数", "平均薪资", "行业", "规模", "融资", "核心技能"]
                 if c in full_table.columns]
    rename_map = {"company_name": "公司"}
    st.dataframe(
        full_table[show_cols].rename(columns=rename_map),
        use_container_width=True, hide_index=True,
        column_config={
            "平均薪资": st.column_config.NumberColumn("均薪(元/月)", format="%.0f"),
        },
        height=500,
    )

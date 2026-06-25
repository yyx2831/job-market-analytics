"""
成都岗位市场深度专题分析 — 独立标签页。

聚焦成都本地 987 条岗位数据，多维度挖掘：
  - 区域分布 & 薪资热力图
  - 行业 / 公司 / 技能 TOP 排名
  - 经验-学历-薪资交叉分析
  - 核心洞察 & 求职建议
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def _load_chengdu(conn: sqlite3.Connection) -> pd.DataFrame:
    """加载成都数据（含有效薪资）。"""
    return pd.read_sql("""
        SELECT *
        FROM jobs
        WHERE city = '成都'
          AND salary_avg > 0
          AND salary_avg < 100000
    """, conn)


def _load_chengdu_full(conn: sqlite3.Connection) -> pd.DataFrame:
    """加载成都全部数据（含无薪资记录）。"""
    return pd.read_sql("SELECT * FROM jobs WHERE city = '成都'", conn)


def render_chengdu_special(db_path: str | Path) -> None:
    """渲染成都深度专题分析页。"""
    st.header("🐼 成都岗位市场深度分析")
    st.caption(f"聚焦成都本地招聘数据，为扎根成都的求职者提供决策参考")

    conn = sqlite3.connect(str(db_path))
    cd = _load_chengdu(conn)
    cd_full = _load_chengdu_full(conn)
    conn.close()

    if cd.empty:
        st.warning("暂无成都数据，请先运行采集脚本。")
        return

    # ━━━ 第0行: KPI 卡片 ━━━
    _render_kpi_row(cd)

    # ━━━ 第1行: 区域分布 + 区域薪资热力 ━━━
    col_a, col_b = st.columns(2)
    with col_a:
        _render_district_jobs(cd_full)
    with col_b:
        _render_district_salary(cd)

    # ━━━ 第2行: 行业分布 + 技能 TOP ━━━
    st.markdown("---")
    col_c, col_d = st.columns(2)
    with col_c:
        _render_industry_chengdu(cd)
    with col_d:
        _render_top_skills_chengdu(cd)

    # ━━━ 第3行: 经验-薪资 + 学历-薪资 ━━━
    col_e, col_f = st.columns(2)
    with col_e:
        _render_exp_salary_chengdu(cd)
    with col_f:
        _render_edu_salary_chengdu(cd)

    # ━━━ 第4行: TOP 雇主 ━━━
    st.markdown("---")
    _render_top_companies(cd)

    # ━━━ 第5行: 核心洞察 ━━━
    st.markdown("---")
    _render_chengdu_insights(cd)


# ── 组件函数 ──────────────────────────────────────────────────────

def _render_kpi_row(cd: pd.DataFrame) -> None:
    """KPI 卡片行。"""
    total = len(cd)

    arr = cd["salary_avg"].dropna().values
    mean_sal = np.mean(arr) if len(arr) > 0 else 0
    median_sal = np.median(arr) if len(arr) > 0 else 0
    p25_sal = np.percentile(arr, 25) if len(arr) > 0 else 0
    p75_sal = np.percentile(arr, 75) if len(arr) > 0 else 0

    # 最高薪岗位
    top_job = cd.loc[cd["salary_avg"].idxmax()] if len(cd) > 0 else None

    # 行业数量
    n_industries = cd["industry"].nunique()

    # 公司数量
    n_companies = cd["company_name"].nunique()

    # 技能种类
    all_skills: Counter = Counter()
    for s in cd["skills"].dropna():
        for sk in str(s).split(","):
            sk = sk.strip()
            if sk:
                all_skills[sk] += 1
    n_skills = len(all_skills)
    top_skill = all_skills.most_common(1)[0][0] if all_skills else "—"

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("📋 岗位总数", f"{total:,}")
    k2.metric("💰 均薪", f"¥{mean_sal:,.0f}")
    k3.metric("📊 中位薪资", f"¥{median_sal:,.0f}")
    k4.metric("🏭 行业数", f"{n_industries}")
    k5.metric("🏢 公司数", f"{n_companies}")
    k6.metric("🔧 技能种类", f"{n_skills}", help=f"TOP 技能: {top_skill}")

    st.caption(
        f"薪资区间: P25 ¥{p25_sal:,.0f} → P75 ¥{p75_sal:,.0f}，"
        f"最高薪: {top_job['title']} @ {top_job['company_name']} ¥{top_job['salary_avg']:,.0f}/月"
        if top_job is not None else ""
    )


def _render_district_jobs(cd_full: pd.DataFrame) -> None:
    """成都各区岗位数量分布。"""
    st.markdown("#### 📍 各区岗位数量")

    district = cd_full["district"].fillna("未知")
    # 清洗：去掉"成都-"前缀
    district = district.str.replace(r"^成都[-—–]?", "", regex=True).str.strip()
    district = district.replace("", "未知")

    counts = district.value_counts().head(15)

    fig = px.bar(
        x=counts.values, y=counts.index,
        orientation="h",
        text=counts.values,
        labels={"x": "岗位数", "y": ""},
        color=counts.values,
        color_continuous_scale="Oranges",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=40, t=10, b=10),
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_district_salary(cd: pd.DataFrame) -> None:
    """成都各区平均薪资分布。"""
    st.markdown("#### 💰 各区平均薪资")

    district = cd["district"].fillna("未知")
    district = district.str.replace(r"^成都[-—–]?", "", regex=True).str.strip()
    district = district.replace("", "未知")

    df = pd.DataFrame({"district": district, "salary_avg": cd["salary_avg"]})
    # 过滤样本 < 5 的区域
    district_counts = df["district"].value_counts()
    valid = district_counts[district_counts >= 5].index
    df = df[df["district"].isin(valid)]

    grouped = df.groupby("district")["salary_avg"].agg(["mean", "count"]).reset_index()
    grouped = grouped.sort_values("mean", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=grouped["district"],
        x=grouped["mean"],
        orientation="h",
        text=[f"¥{v:,.0f} ({n}条)" for v, n in zip(grouped["mean"], grouped["count"])],
        textposition="outside",
        marker=dict(
            color=grouped["mean"],
            colorscale="OrRd",
            showscale=False,
        ),
    ))
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis_title="平均月薪 (元)",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("过滤样本数 < 5 的区域")


def _render_industry_chengdu(cd: pd.DataFrame) -> None:
    """成都行业分布 TOP 12。"""
    st.markdown("#### 🏭 行业分布 TOP 12")

    ind = cd["industry"].fillna("未知").value_counts().head(12)

    # 增加均薪信息
    ind_sal = cd.groupby("industry")["salary_avg"].agg(["mean", "count"]).reindex(ind.index)

    fig = px.bar(
        x=ind.values, y=ind.index,
        orientation="h",
        text=[f"{v} 个 (均¥{ind_sal.loc[i, 'mean']:,.0f})" if i in ind_sal.index else f"{v} 个"
              for i, v in ind.items()],
        labels={"x": "岗位数", "y": ""},
        color=ind.values,
        color_continuous_scale="Blues",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=80, t=10, b=10),
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_top_skills_chengdu(cd: pd.DataFrame) -> None:
    """成都技能需求 TOP 15。"""
    st.markdown("#### 🔧 技能需求 TOP 15")

    counter: Counter = Counter()
    for s in cd["skills"].dropna():
        for sk in str(s).split(","):
            sk = sk.strip()
            if sk:
                counter[sk] += 1

    top = counter.most_common(15)
    skills = [s for s, c in top]
    counts = [c for s, c in top]
    pct = [c / len(cd) * 100 for c in counts]

    # 计算含该技能的岗位均薪
    skill_sal = {}
    for skill, _ in top:
        mask = cd["skills"].fillna("").str.contains(skill, regex=False)
        skill_sal[skill] = cd.loc[mask, "salary_avg"].mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=skills,
        x=counts,
        orientation="h",
        text=[f"{c}次 ({p:.1f}%) · 均¥{skill_sal.get(s, 0):,.0f}" for s, c, p in zip(skills, counts, pct)],
        textposition="outside",
        marker=dict(
            color=counts,
            colorscale="Greens",
            showscale=False,
        ),
    ))
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=100, t=10, b=10),
        xaxis_title="出现次数",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_exp_salary_chengdu(cd: pd.DataFrame) -> None:
    """成都经验-薪资关系。"""
    st.markdown("#### 📈 经验年限 vs 薪资")

    exp_order = [
        "无需经验", "1年", "1年及以上", "1-2年", "1-3年", "1-5年",
        "2年", "2年及以上", "2-3年", "2-5年", "2-6年",
        "3年", "3年及以上", "3-4年", "3-5年", "3-6年", "3-8年",
        "4年及以上",
        "5年及以上", "5-7年", "5-10年",
        "7-10年", "8年及以上", "10年及以上",
        "不限",
    ]

    exp_data = cd.groupby("experience").agg(
        count=("salary_avg", "count"),
        mean_salary=("salary_avg", "mean"),
        median_salary=("salary_avg", "median"),
    ).reset_index()
    exp_data = exp_data[exp_data["count"] >= 3]  # 过滤样本过少

    # 尝试按 exp_order 排序
    order_map = {e: i for i, e in enumerate(exp_order)}
    exp_data["_order"] = exp_data["experience"].map(order_map).fillna(99)
    exp_data = exp_data.sort_values("_order")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=exp_data["experience"],
        y=exp_data["mean_salary"],
        name="均薪",
        text=[f"¥{v:,.0f}" for v in exp_data["mean_salary"]],
        textposition="outside",
        marker_color="#E6550D",
    ))
    fig.add_trace(go.Scatter(
        x=exp_data["experience"],
        y=exp_data["median_salary"],
        name="中位数",
        mode="lines+markers",
        line=dict(color="#3182BD", width=2),
        marker=dict(size=8),
    ))
    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=10, b=60),
        yaxis_title="月薪 (元)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis=dict(tickangle=-30),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"过滤样本数 < 3 的经验档位 | 共 {len(exp_data)} 档有效")


def _render_edu_salary_chengdu(cd: pd.DataFrame) -> None:
    """成都学历-薪资关系。"""
    st.markdown("#### 🎓 学历要求 vs 薪资")

    edu_order = ["初中", "高中", "中技/中专", "大专", "本科", "硕士", "博士", "不限"]

    edu_data = cd.groupby("education").agg(
        count=("salary_avg", "count"),
        mean_salary=("salary_avg", "mean"),
        median_salary=("salary_avg", "median"),
    ).reset_index()

    order_map = {e: i for i, e in enumerate(edu_order)}
    edu_data["_order"] = edu_data["education"].map(order_map).fillna(99)
    edu_data = edu_data.sort_values("_order")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=edu_data["education"],
        y=edu_data["mean_salary"],
        name="均薪",
        text=[f"¥{v:,.0f}<br>({n}个)" for v, n in zip(edu_data["mean_salary"], edu_data["count"])],
        textposition="outside",
        marker_color="#31A354",
    ))
    fig.add_trace(go.Scatter(
        x=edu_data["education"],
        y=edu_data["median_salary"],
        name="中位数",
        mode="lines+markers",
        line=dict(color="#756BB1", width=2),
        marker=dict(size=10),
    ))
    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="月薪 (元)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_top_companies(cd: pd.DataFrame) -> None:
    """成都 TOP 招聘公司。"""
    st.markdown("#### 🏢 成都招聘量 TOP 15 公司")

    comp = cd["company_name"].fillna("未知").value_counts().head(15)
    comp_sal = cd.groupby("company_name")["salary_avg"].agg(["mean", "max"]).reindex(comp.index)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=[f"{c[:20]}" for c in comp.index],
        x=comp.values,
        orientation="h",
        text=[f"{v} 个 (均¥{comp_sal.loc[c, 'mean']:,.0f} · 最高¥{comp_sal.loc[c, 'max']:,.0f})"
              for c, v in comp.items()],
        textposition="outside",
        marker=dict(color=comp.values, colorscale="Purples", showscale=False),
    ))
    fig.update_layout(
        height=450,
        margin=dict(l=10, r=120, t=10, b=10),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_chengdu_insights(cd: pd.DataFrame) -> None:
    """成都市场核心洞察。"""
    st.markdown("### 💡 成都求职核心洞察")

    total = len(cd)
    arr = cd["salary_avg"].dropna().values
    mean_sal = np.mean(arr)
    median_sal = np.median(arr)

    # 各维度快速统计
    edu_counts = cd["education"].value_counts()
    exp_counts = cd["experience"].value_counts()

    bachelor_pct = (edu_counts.get("本科", 0) / total * 100)
    junior_pct = (edu_counts.get("大专", 0) / total * 100)
    no_exp = exp_counts.get("无需经验", 0)
    senior = sum(v for k, v in exp_counts.items() if "5年" in k or "8年" in k or "10年" in k)

    # TOP 行业
    top_ind = cd["industry"].value_counts().head(5)

    # TOP 技能
    skill_counter: Counter = Counter()
    for s in cd["skills"].dropna():
        for sk in str(s).split(","):
            sk = sk.strip()
            if sk:
                skill_counter[sk] += 1
    top_skills = [s for s, _ in skill_counter.most_common(5)]

    # 区域
    dist = cd["district"].fillna("未知").str.replace(r"^成都[-—–]?", "", regex=True).str.strip()
    top_dist = dist.value_counts().head(3)

    insights = [
        f"📊 **市场规模**：成都共 {total:,} 条有效岗位，均薪 ¥{mean_sal:,.0f}/月，"
        f"中位数 ¥{median_sal:,.0f}/月。薪资呈 "
        f"{'右偏' if mean_sal > median_sal else '左偏'}分布（均值与中位数差距¥{abs(mean_sal - median_sal):,.0f}）。",

        f"📍 **区域热度**：岗位密集区为 {', '.join(top_dist.index[:3])}，"
        f"占比 {top_dist.iloc[:3].sum() / total * 100:.1f}%。",

        f"🏭 **行业结构**：{', '.join(top_ind.index[:5])} 为成都最大招聘赛道，"
        f"合计占比 {top_ind.iloc[:5].sum() / total * 100:.1f}%。",

        f"🔧 **技能需求**：{', '.join(top_skills)} 是成都市场最刚需技能。",

        f"🎓 **学历门槛**：本科要求 {bachelor_pct:.1f}%，大专 {junior_pct:.1f}%，"
        f"硕博需求相对较少。整体学历门槛适中。",

        f"⏳ **经验要求**：无需经验岗位 {no_exp} 个（{no_exp / total * 100:.1f}%），"
        f"5+年高级岗位 {senior} 个（{senior / total * 100:.1f}%），"
        f"市场以 1-5 年经验需求为主。",

        f"💡 **成都优势**：IT/互联网行业密集，生活成本低于一线但薪资竞争力尚可，"
        f"适合 1-5 年经验的技术人才长期发展。",
    ]

    for i, ins in enumerate(insights):
        st.markdown(f"{i + 1}. {ins}")

    st.info(
        "💡 建议关注武侯区/高新区机会（IT 企业密集），"
        "掌握 {top_skills[0]} 和 {top_skills[1]} 技能组合在成都市场议价能力最强。"
        if len(top_skills) >= 2 else
        "💡 建议关注武侯区/高新区机会（IT 企业密集）。"
    )

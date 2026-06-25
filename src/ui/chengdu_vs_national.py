"""
成都 vs 全国深度对比分析 — Streamlit 仪表盘标签页。

对比维度：
  - 薪资分布 (P25/P50/P75 双柱状图)
  - 职位族占比 (堆叠柱状图)
  - TOP 技能渗透率差异 (水平 bar chart)
  - 学历 / 经验要求对比
  - 公司类型分布对比
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _load_chengdu(conn: sqlite3.Connection) -> pd.DataFrame:
    """加载成都数据（含薪资，去除异常值）。"""
    return pd.read_sql("""
        SELECT *
        FROM jobs
        WHERE city = '成都'
          AND salary_avg > 0
          AND salary_avg < 100000
    """, conn)


def _load_national(conn: sqlite3.Connection) -> pd.DataFrame:
    """加载全国数据（排除成都 / 未知 / NULL 城区）。"""
    return pd.read_sql("""
        SELECT *
        FROM jobs
        WHERE city IS NOT NULL
          AND city != '成都'
          AND city != ''
          AND city != '未知'
          AND salary_avg > 0
          AND salary_avg < 100000
    """, conn)


def _classify_family(df: pd.DataFrame) -> pd.DataFrame:
    """为 DataFrame 增加 title_family 列（复用 position_benchmark 的分类器）。"""
    from src.analytics.position_benchmark import normalize_title

    families = []
    for t in df["title"]:
        _, _, fam = normalize_title(t or "")
        families.append(fam)
    df = df.copy()
    df["title_family"] = families
    return df


def _salary_percentiles(df: pd.DataFrame) -> dict[str, float]:
    """计算薪资 P25 / P50 / P75。"""
    arr = df["salary_avg"].dropna().values
    if len(arr) == 0:
        return {"p25": 0, "p50": 0, "p75": 0, "mean": 0}
    return {
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "mean": float(np.mean(arr)),
    }


def _skill_penetration(df: pd.DataFrame) -> dict[str, float]:
    """计算技能渗透率（技能出现次数 / 岗位总数）。"""
    total = len(df)
    counter: Counter = Counter()
    for skills_str in df["skills"].dropna():
        for s in str(skills_str).split(","):
            s = s.strip()
            if s:
                counter[s] += 1
    return {k: v / total for k, v in counter.items()}


def render_chengdu_vs_national(db_path: str | Path) -> None:
    """渲染"成都 vs 全国"对比分析标签页。"""
    st.subheader("🏙️ 成都 vs 全国 深度对比分析")
    st.caption("数据范围：salary_avg > 0 且 < 100000 元/月，排除异常值")

    conn = sqlite3.connect(str(db_path))
    cd = _load_chengdu(conn)
    nat = _load_national(conn)
    conn.close()

    cd = _classify_family(cd)
    nat = _classify_family(nat)

    # ━━━ KPI 卡片 ━━━
    cd_sal = _salary_percentiles(cd)
    nat_sal = _salary_percentiles(nat)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("成都·岗位数", f"{len(cd):,}")
    k2.metric("成都·均薪", f"¥{cd_sal['mean']:,.0f}",
              delta=f"{cd_sal['mean'] - nat_sal['mean']:+,.0f} vs 全国" if nat_sal['mean'] else None)
    k3.metric("成都·中位数", f"¥{cd_sal['p50']:,.0f}")
    k4.metric("全国·均薪", f"¥{nat_sal['mean']:,.0f}")

    # ━━━ 第1行: 薪资分布 + 职位族占比 ━━━
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 💰 薪资分位数对比")
        _render_salary_bars(cd_sal, nat_sal)

    with col_b:
        st.markdown("#### 🧩 职位族占比对比")
        _render_family_stack(cd, nat)

    # ━━━ 第2行: 技能渗透率差 + 经验/学历对比 ━━━
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("#### 🔧 TOP 技能渗透率差异")
        _render_skill_gap(cd, nat)

    with col_d:
        st.markdown("#### 🎓 经验 / 学历要求对比")
        _render_exp_edu(cd, nat)

    # ━━━ 第3行: 公司类型分布 ━━━
    st.markdown("---")
    col_e, col_f = st.columns(2)

    with col_e:
        st.markdown("#### 🏢 公司规模分布")
        _render_company_size(cd, nat)

    with col_f:
        st.markdown("#### 🏭 行业分布 TOP10")
        _render_industry(cd, nat)

    # ━━━ 第4行: 核心洞察 ━━━
    st.markdown("---")
    st.markdown("### 📊 核心洞察")
    _render_insights(cd, nat, cd_sal, nat_sal)


# ── 可视化函数 ────────────────────────────────────────────────────

def _render_salary_bars(cd_sal: dict, nat_sal: dict) -> None:
    """双柱状图：成都 vs 全国薪资 P25 / P50 / P75 + 均值。"""
    cats = ["P25", "P50", "P75", "均值"]
    cd_vals = [cd_sal["p25"], cd_sal["p50"], cd_sal["p75"], cd_sal["mean"]]
    nat_vals = [nat_sal["p25"], nat_sal["p50"], nat_sal["p75"], nat_sal["mean"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=cats, y=cd_vals, name="成都",
        text=[f"¥{v:,.0f}" for v in cd_vals],
        textposition="outside",
        marker_color="#E6550D",
    ))
    fig.add_trace(go.Bar(
        x=cats, y=nat_vals, name="全国(除成都)",
        text=[f"¥{v:,.0f}" for v in nat_vals],
        textposition="outside",
        marker_color="#3182BD",
    ))
    fig.update_layout(
        barmode="group",
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="元/月",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_family_stack(cd: pd.DataFrame, nat: pd.DataFrame) -> None:
    """堆叠柱状图：职位族占比对比。"""
    cd_counts = cd["title_family"].value_counts(normalize=True)
    nat_counts = nat["title_family"].value_counts(normalize=True)
    all_fams = sorted(set(cd_counts.index) | set(nat_counts.index),
                      key=lambda f: -(cd_counts.get(f, 0) + nat_counts.get(f, 0)))

    cd_pct = [cd_counts.get(f, 0) * 100 for f in all_fams]
    nat_pct = [nat_counts.get(f, 0) * 100 for f in all_fams]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["成都", "全国(除成都)"], y=cd_pct,
        name=all_fams[0] if len(all_fams) > 0 else "",
        text=[f"{cd_pct[0]:.1f}%" if len(cd_pct) > 0 else "", f"{nat_pct[0]:.1f}%" if len(nat_pct) > 0 else ""],
        textposition="inside",
    ))
    # 由于 Plotly 堆叠需要逐层添加，这里用分组柱状图代替更清晰
    # 重新构造为分组柱状图
    fig2 = go.Figure()
    colors = ["#E6550D", "#3182BD", "#31A354", "#756BB1", "#D6616B",
              "#E7BA52", "#7B4173", "#A55194", "#843C39", "#8C6D31",
              "#637939", "#CEDB9C"]
    for i, fam in enumerate(all_fams):
        fig2.add_trace(go.Bar(
            x=["成都", "全国(除成都)"],
            y=[cd_counts.get(fam, 0) * 100, nat_counts.get(fam, 0) * 100],
            name=fam,
            text=[f"{cd_counts.get(fam, 0) * 100:.1f}%", f"{nat_counts.get(fam, 0) * 100:.1f}%"],
            textposition="inside",
            marker_color=colors[i % len(colors)],
        ))
    fig2.update_layout(
        barmode="stack",
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="占比 (%)",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
    )
    st.plotly_chart(fig2, use_container_width=True)


def _render_skill_gap(cd: pd.DataFrame, nat: pd.DataFrame) -> None:
    """水平 bar：成都 vs 全国 TOP 技能渗透率差。"""
    cd_pen = _skill_penetration(cd)
    nat_pen = _skill_penetration(nat)

    all_skills = set(cd_pen.keys()) | set(nat_pen.keys())
    gaps = []
    for sk in all_skills:
        cd_rate = cd_pen.get(sk, 0)
        nat_rate = nat_pen.get(sk, 0)
        gaps.append({
            "skill": sk,
            "cd_pct": cd_rate * 100,
            "nat_pct": nat_rate * 100,
            "gap": (cd_rate - nat_rate) * 100,
            "total": cd_rate + nat_rate,
        })

    gaps_df = pd.DataFrame(gaps)
    # 按合成渗透率加权排序，选 TOP 15
    gaps_df = gaps_df.sort_values("total", ascending=False).head(15)
    # 按差值排序展示
    gaps_df = gaps_df.sort_values("gap", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=gaps_df["skill"],
        x=gaps_df["gap"],
        orientation="h",
        marker=dict(
            color=[ "#E6550D" if v >= 0 else "#3182BD" for v in gaps_df["gap"] ],
        ),
        text=[f"{v:+.1f}%" for v in gaps_df["gap"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="成都 - 全国 技能渗透率差 (百分点)",
        height=400,
        margin=dict(l=10, r=30, t=40, b=10),
        xaxis_title="渗透率差 (%)",
        yaxis=dict(autorange="reversed"),
    )
    fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("正值 = 成都高于全国；负值 = 成都低于全国")


def _render_exp_edu(cd: pd.DataFrame, nat: pd.DataFrame) -> None:
    """经验 + 学历分布对比。"""
    # 经验
    exp_order = ["无需经验", "1年及以上", "1-3年", "2年及以上", "2-5年",
                 "3年及以上", "3-5年", "5年及以上", "5-10年", "8年及以上", "10年及以上"]

    def _pct(series):
        s = series.value_counts(normalize=True) * 100
        return {k: s.get(k, 0) for k in exp_order if s.get(k, 0) > 0.5 or k in series.values}

    cd_exp = cd["experience"].value_counts(normalize=True) * 100
    nat_exp = nat["experience"].value_counts(normalize=True) * 100
    all_exp = sorted(set(cd_exp.index) | set(nat_exp.index),
                     key=lambda e: exp_order.index(e) if e in exp_order else 99)

    # 学历
    edu_order = ["初中", "高中", "中技/中专", "大专", "本科", "硕士", "博士"]
    cd_edu = cd["education"].value_counts(normalize=True) * 100
    nat_edu = nat["education"].value_counts(normalize=True) * 100
    all_edu = sorted(set(cd_edu.index) | set(nat_edu.index),
                     key=lambda e: edu_order.index(e) if e in edu_order else 99)

    # 双柱
    sub_a, sub_b = st.columns(2)

    with sub_a:
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=all_exp, y=[cd_exp.get(e, 0) for e in all_exp],
            name="成都", marker_color="#E6550D",
            text=[f"{cd_exp.get(e, 0):.1f}%" for e in all_exp],
            textposition="outside",
        ))
        fig1.add_trace(go.Bar(
            x=all_exp, y=[nat_exp.get(e, 0) for e in all_exp],
            name="全国", marker_color="#3182BD",
            text=[f"{nat_exp.get(e, 0):.1f}%" for e in all_exp],
            textposition="outside",
        ))
        fig1.update_layout(
            barmode="group", height=300,
            margin=dict(l=10, r=10, t=30, b=40),
            title="经验要求",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig1, use_container_width=True)

    with sub_b:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=all_edu, y=[cd_edu.get(e, 0) for e in all_edu],
            name="成都", marker_color="#E6550D",
            text=[f"{cd_edu.get(e, 0):.1f}%" for e in all_edu],
            textposition="outside",
        ))
        fig2.add_trace(go.Bar(
            x=all_edu, y=[nat_edu.get(e, 0) for e in all_edu],
            name="全国", marker_color="#3182BD",
            text=[f"{nat_edu.get(e, 0):.1f}%" for e in all_edu],
            textposition="outside",
        ))
        fig2.update_layout(
            barmode="group", height=300,
            margin=dict(l=10, r=10, t=30, b=40),
            title="学历要求",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig2, use_container_width=True)


def _render_company_size(cd: pd.DataFrame, nat: pd.DataFrame) -> None:
    """公司规模分布对比。"""
    cd_sz = cd["company_size"].value_counts(normalize=True) * 100
    nat_sz = nat["company_size"].value_counts(normalize=True) * 100

    # 合并分类（处理同类名称）
    size_groups = {}
    for s in set(cd_sz.index) | set(nat_sz.index):
        key = s
        if s in ("少于50人", "20-99人", "少于15人", "15-50人"):
            key = "小型 (<100人)"
        elif s in ("50-150人", "100-499人", "150-500人"):
            key = "中型 (100-500人)"
        elif s in ("500-999人", "500-1000人", "1000-5000人", "1000-9999人"):
            key = "大型 (500-10000人)"
        elif s in ("5000-10000人", "10000人以上"):
            key = "超大型 (5000人+)"
        else:
            key = s
        size_groups.setdefault(key, {"cd": 0, "nat": 0})
        size_groups[key]["cd"] += cd_sz.get(s, 0)
        size_groups[key]["nat"] += nat_sz.get(s, 0)

    order = ["小型 (<100人)", "中型 (100-500人)", "大型 (500-10000人)", "超大型 (5000人+)", "未知"]
    labels = [k for k in order if k in size_groups] + \
             [k for k in size_groups if k not in order]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=[size_groups[l]["cd"] for l in labels],
        name="成都", marker_color="#E6550D",
        text=[f"{size_groups[l]['cd']:.1f}%" for l in labels],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=labels, y=[size_groups[l]["nat"] for l in labels],
        name="全国", marker_color="#3182BD",
        text=[f"{size_groups[l]['nat']:.1f}%" for l in labels],
        textposition="outside",
    ))
    fig.update_layout(
        barmode="group", height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="占比 (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_industry(cd: pd.DataFrame, nat: pd.DataFrame) -> None:
    """行业分布 TOP 10 对比。"""
    cd_ind = cd["industry"].value_counts(normalize=True).head(10) * 100
    nat_ind = nat["industry"].value_counts(normalize=True).head(10) * 100

    all_ind = sorted(set(cd_ind.index) | set(nat_ind.index),
                     key=lambda i: -(cd_ind.get(i, 0) + nat_ind.get(i, 0)))[:12]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=all_ind, y=[cd_ind.get(i, 0) for i in all_ind],
        name="成都", marker_color="#E6550D",
        text=[f"{cd_ind.get(i, 0):.1f}%" for i in all_ind],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=all_ind, y=[nat_ind.get(i, 0) for i in all_ind],
        name="全国", marker_color="#3182BD",
        text=[f"{nat_ind.get(i, 0):.1f}%" for i in all_ind],
        textposition="outside",
    ))
    fig.update_layout(
        barmode="group", height=360,
        margin=dict(l=10, r=10, t=10, b=60),
        yaxis_title="占比 (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis=dict(tickangle=-30),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_insights(
    cd: pd.DataFrame, nat: pd.DataFrame,
    cd_sal: dict, nat_sal: dict,
) -> None:
    """生成核心洞察文本。"""
    insights: list[str] = []

    # 1. 薪资差距
    gap_pct = ((cd_sal["mean"] - nat_sal["mean"]) / nat_sal["mean"] * 100) if nat_sal["mean"] > 0 else 0
    if gap_pct > 0:
        insights.append(f"📈 **薪资水平**：成都均薪 ¥{cd_sal['mean']:,.0f}，比全国(除成都)均薪 ¥{nat_sal['mean']:,.0f} 高 {gap_pct:+.1f}%。中位数差异为 ¥{cd_sal['p50'] - nat_sal['p50']:+,.0f}。")
    else:
        insights.append(f"📉 **薪资水平**：成都均薪 ¥{cd_sal['mean']:,.0f}，低于全国均薪 ¥{nat_sal['mean']:,.0f} ({gap_pct:+.1f}%)。")

    # 2. 职位族差异
    cd_fam = cd["title_family"].value_counts(normalize=True)
    nat_fam = nat["title_family"].value_counts(normalize=True)
    top_diff = sorted(
        ((f, cd_fam.get(f, 0) - nat_fam.get(f, 0)) for f in set(cd_fam.index) | set(nat_fam.index)),
        key=lambda x: -abs(x[1])
    )[:3]
    if top_diff:
        parts = []
        for fam, diff in top_diff:
            direction = "更高" if diff > 0 else "更低"
            parts.append(f"「{fam}」占比{direction} ({diff:+.1%})")
        insights.append(f"🧩 **职位族差异**：{'; '.join(parts)}。")

    # 3. 技能差异
    cd_pen = _skill_penetration(cd)
    nat_pen = _skill_penetration(nat)
    all_skills = set(cd_pen.keys()) | set(nat_pen.keys())
    skill_diffs = sorted(
        [(s, cd_pen.get(s, 0) - nat_pen.get(s, 0)) for s in all_skills],
        key=lambda x: -abs(x[1])
    )[:5]
    if skill_diffs:
        cd_high = [s for s, d in skill_diffs if d > 0][:3]
        nat_high = [s for s, d in skill_diffs if d < 0][:3]
        if cd_high:
            insights.append(f"🔧 **成都侧重技能**：{', '.join(cd_high)} 渗透率显著高于全国。")
        if nat_high:
            insights.append(f"🔧 **全国侧重技能**：{', '.join(nat_high)} 渗透率显著高于成都。")

    # 4. 公司规模
    cd_small = (cd["company_size"].isin(["少于50人", "20-99人", "少于15人", "15-50人"]).mean() * 100)
    nat_small = (nat["company_size"].isin(["少于50人", "20-99人", "少于15人", "15-50人"]).mean() * 100)
    cd_large = (cd["company_size"].isin(["5000-10000人", "10000人以上"]).mean() * 100)
    nat_large = (nat["company_size"].isin(["5000-10000人", "10000人以上"]).mean() * 100)
    insights.append(f"🏢 **公司规模**：成都小型企业占比 {cd_small:.1f}% (全国 {nat_small:.1f}%)，超大型企业占比 {cd_large:.1f}% (全国 {nat_large:.1f}%)。")

    # 5. 教育门槛
    cd_bachelor = (cd["education"] == "本科").mean() * 100
    nat_bachelor = (nat["education"] == "本科").mean() * 100
    cd_master = (cd["education"] == "硕士").mean() * 100
    nat_master = (nat["education"] == "硕士").mean() * 100
    insights.append(f"🎓 **学历门槛**：成都本科要求 {cd_bachelor:.1f}% (全国 {nat_bachelor:.1f}%)，硕士要求 {cd_master:.1f}% (全国 {nat_master:.1f}%)。")

    for ins in insights:
        st.markdown(ins)

    # 数据卡片
    st.caption(f"数据：成都 {len(cd):,} 条 | 全国 {len(nat):,} 条 | 成都占比 {len(cd) / (len(cd) + len(nat)) * 100:.1f}%")

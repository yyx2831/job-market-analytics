"""技能需求趋势分析 — 按月追踪技能需求变化，区分上升期/稳定期/衰退期。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd


def compute_skill_demand_trend(
    jobs: pd.DataFrame,
    min_skill_count: int = 10,
    min_months: int = 2,
) -> pd.DataFrame:
    """计算技能月度需求趋势。

    基于 publish_time 按月聚合各技能需求次数，
    然后计算线性趋势斜率判断上升/稳定/衰退。

    Args:
        jobs: 岗位 DataFrame，需含 skills 和 publish_time 列
        min_skill_count: 最低总需求次数过滤
        min_months: 最少月份数过滤

    Returns:
        DataFrame，每行一个技能的月度趋势总结：
        - skill, total_demand, months
        - trend_slope: 斜率（月均需求变化）
        - trend_label: rising / stable / declining
        - monthly_data: 各月需求字典（JSON）
    """
    import json
    from collections import defaultdict

    if "skills" not in jobs.columns or "publish_time" not in jobs.columns:
        return pd.DataFrame()

    # 安全日期解析
    jobs = jobs.copy()
    jobs["publish_dt"] = pd.to_datetime(jobs["publish_time"], format="mixed", errors="coerce")
    jobs = jobs[jobs["publish_dt"].notna()]
    if jobs.empty:
        return pd.DataFrame()

    jobs["month"] = jobs["publish_dt"].dt.to_period("M").astype(str)

    # ── 技能 × 月份 计数 ──
    skill_month: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, row in jobs.iterrows():
        skills_str = row.get("skills", "")
        if pd.isna(skills_str) or not skills_str:
            continue
        try:
            items = json.loads(skills_str)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(skills_str).split(",") if s.strip()]
        m = row["month"]
        for s in items:
            s = str(s).strip()
            if s:
                skill_month[s][m] += 1

    if not skill_month:
        return pd.DataFrame()

    # ── 趋势分析 ──
    all_months = sorted(jobs["month"].unique())
    results = []

    for skill, month_counts in skill_month.items():
        total = sum(month_counts.values())
        months_present = len(month_counts)
        if total < min_skill_count or months_present < min_months:
            continue

        # 构建时间序列向量
        xs = []
        ys = []
        for m in all_months:
            xs.append(all_months.index(m))
            ys.append(month_counts.get(m, 0))

        # 线性回归斜率
        n = len(xs)
        if n < 2:
            continue
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0.0

        # R² 计算
        ss_res = sum((ys[i] - (slope * xs[i] + (mean_y - slope * mean_x))) ** 2 for i in range(n))
        ss_tot = sum((ys[i] - mean_y) ** 2 for i in range(n))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # 分类
        if slope > 0.5 and r_squared > 0.3:
            label = "rising"
        elif slope < -0.3 and r_squared > 0.3:
            label = "declining"
        else:
            label = "stable"

        # 最近趋势
        recent_months = sorted(month_counts.keys())[-3:]
        recent_avg = sum(month_counts[m] for m in recent_months) / len(recent_months) if recent_months else 0

        results.append({
            "skill": skill,
            "total_demand": total,
            "months": months_present,
            "trend_slope": round(slope, 3),
            "r_squared": round(r_squared, 3),
            "trend_label": label,
            "recent_avg": round(recent_avg, 1),
            "monthly_data": {str(k): v for k, v in sorted(month_counts.items())},
        })

    df = pd.DataFrame(results)
    if df.empty:
        return df
    return df.sort_values("total_demand", ascending=False)


def get_trending_skills(
    jobs: pd.DataFrame,
    trend: str = "rising",
    top_n: int = 10,
) -> List[dict]:
    """获取指定趋势类型的技能。

    Args:
        jobs: 岗位 DataFrame
        trend: 趋势类型 — "rising" / "stable" / "declining"
        top_n: 返回数量

    Returns:
        技能列表（含趋势斜率、月度数据）
    """
    df = compute_skill_demand_trend(jobs)
    if df.empty:
        return []
    subset = df[df["trend_label"] == trend].head(top_n)
    return subset.to_dict("records")


def trend_summary(jobs: pd.DataFrame) -> dict:
    """技能趋势总览摘要。

    Returns:
        {"rising": N, "stable": N, "declining": N,
         "top_rising": [...], "top_declining": [...]}
    """
    df = compute_skill_demand_trend(jobs)
    if df.empty:
        return {"rising": 0, "stable": 0, "declining": 0, "top_rising": [], "top_declining": []}

    rising = df[df["trend_label"] == "rising"]
    declining = df[df["trend_label"] == "declining"]
    stable = df[df["trend_label"] == "stable"]

    return {
        "rising": len(rising),
        "stable": len(stable),
        "declining": len(declining),
        "top_rising": rising.head(5)[["skill", "trend_slope", "total_demand"]].to_dict("records"),
        "top_declining": declining.head(5)[["skill", "trend_slope", "total_demand"]].to_dict("records"),
    }

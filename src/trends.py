"""趋势分析引擎 - 从时间维度挖掘市场变化方向。

涵盖：薪资趋势、技能需求趋势、行业热度变化、城市活跃度变化、技能投资回报分析。
"""
from __future__ import annotations

from collections import defaultdict
import re
from dataclasses import dataclass

import pandas as pd
import numpy as np


@dataclass
class Trend:
    title: str
    body: str
    direction: str = "→"  # ↑ / ↓ / →
    strength: str = "medium"  # strong / medium / weak


def _safe_pct(old, new) -> str:
    if old == 0:
        return "新增"
    pct = (new - old) / old * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0f}%"


def analyze_trends(jobs: pd.DataFrame) -> list[Trend]:
    """从岗位数据提取趋势信号。"""
    trends = []

    real = jobs[jobs["salary_avg"].notna()].copy()
    if real.empty or "publish_time" not in real.columns:
        return [Trend("时间字段缺失", "数据中无 publish_time 列，无法做趋势分析。", "→", "weak")]

    real["pub_date"] = pd.to_datetime(real["publish_time"], errors="coerce")
    real = real.dropna(subset=["pub_date"])
    if len(real) < 20:
        return [Trend("数据量不足", f"仅有 {len(real)} 条未过期数据，趋势分析需至少20条。", "→", "weak")]

    city_name = real["city"].iloc[0] if real["city"].nunique() == 1 else "多城市"

    # ── 1. 薪资月度趋势 ──
    real["month"] = real["pub_date"].dt.to_period("M").astype(str)
    monthly = real.groupby("month").agg(
        岗位数=("title", "count"),
        平均薪资=("salary_avg", "mean"),
        中位薪资=("salary_avg", "median"),
    ).sort_index()

    if len(monthly) >= 2:
        recent = monthly.iloc[-2:]
        salary_change = (recent["中位薪资"].iloc[-1] - recent["中位薪资"].iloc[0]) / recent["中位薪资"].iloc[0] * 100
        direction = "↑" if salary_change > 2 else "↓" if salary_change < -2 else "→"
        strength = "strong" if abs(salary_change) > 5 else "medium" if abs(salary_change) > 2 else "weak"
        trends.append(Trend(
            title="💰 薪资走势",
            body=f"从 {recent.index[0]} 到 {recent.index[-1]}："
                 f"中位薪资从 ¥{recent['中位薪资'].iloc[0]/1000:.1f}K → ¥{recent['中位薪资'].iloc[-1]/1000:.1f}K"
                 f"（{'涨' if salary_change > 0 else '跌'}{abs(salary_change):.1f}%），"
                 f"岗位数从 {int(recent['岗位数'].iloc[0])} → {int(recent['岗位数'].iloc[-1])}"
                 f"（{_safe_pct(recent['岗位数'].iloc[0], recent['岗位数'].iloc[-1])}）。",
            direction=direction,
            strength=strength,
        ))

    # ── 2. 技能需求趋势 ──
    if "skills" in real.columns:
        first_half = real[real["pub_date"] <= real["pub_date"].median()]
        second_half = real[real["pub_date"] > real["pub_date"].median()]

        def extract_skills(df):
            c = defaultdict(int)
            for _, row in df.iterrows():
                s = row.get("skills", "")
                if pd.isna(s) or not s:
                    continue
                for t in re.split(r'[,;，；、]+', str(s)):
                    t = t.strip()
                    if t:
                        c[t] += 1
            return c

        s1 = extract_skills(first_half)
        s2 = extract_skills(second_half)

        all_skills = set(s1) | set(s2)
        changes = {}
        for sk in all_skills:
            c1 = s1.get(sk, 0)
            c2 = s2.get(sk, 0)
            if c1 + c2 >= 4:
                changes[sk] = (c2 - c1) / max(c1, 1) * 100

        if changes:
            rising = sorted(changes.items(), key=lambda x: -x[1])[:5]
            falling = sorted(changes.items(), key=lambda x: x[1])[:5]

            if rising and any(v > 0 for _, v in rising):
                r_items = [f"• {s}：{_safe_pct(max(s1.get(s,1),1), s2.get(s,0))}" for s, v in rising if v > 5]
                if r_items:
                    trends.append(Trend(
                        title="📈 热门技能上升榜",
                        body="\n".join(r_items),
                        direction="↑",
                        strength="medium",
                    ))

            if falling and any(v < 0 for _, v in falling):
                f_items = [f"• {s}：{_safe_pct(max(s1.get(s,1),1), s2.get(s,0))}" for s, v in falling if v < -10]
                if f_items:
                    trends.append(Trend(
                        title="📉 技能需求降温榜",
                        body="\n".join(f_items),
                        direction="↓",
                        strength="medium",
                    ))

    # ── 3. 行业热度趋势 ──
    if "industry" in real.columns:
        first_half = real[real["pub_date"] <= real["pub_date"].median()]
        second_half = real[real["pub_date"] > real["pub_date"].median()]

        i1 = first_half["industry"].value_counts()
        i2 = second_half["industry"].value_counts()

        ind_changes = []
        for ind in set(i1.index) | set(i2.index):
            c1 = i1.get(ind, 0)
            c2 = i2.get(ind, 0)
            if c1 + c2 >= 3:
                ind_changes.append((ind, c1, c2, (c2 - c1) / max(c1, 1) * 100))

        hot = sorted(ind_changes, key=lambda x: -x[3])[:3]
        cold = sorted(ind_changes, key=lambda x: x[3])[:3]

        if hot and any(x[3] > 10 for x in hot):
            h_items = [f"• {ind}：{int(c1)}→{int(c2)}（{_safe_pct(c1,c2)}）" for ind, c1, c2, _ in hot]
            trends.append(Trend(
                title="🔥 行业升温榜",
                body="\n".join(h_items),
                direction="↑",
                strength="medium",
            ))

        if cold and any(x[3] < -10 for x in cold):
            c_items = [f"• {ind}：{int(c1)}→{int(c2)}（{_safe_pct(c1,c2)}）" for ind, c1, c2, _ in cold]
            trends.append(Trend(
                title="❄️ 行业降温榜",
                body="\n".join(c_items),
                direction="↓",
                strength="medium",
            ))

    # ── 4. 综合趋势判断 ──
    if len(monthly) >= 2:
        latest = monthly.iloc[-1]
        prev = monthly.iloc[-2]
        job_change = (latest["岗位数"] - prev["岗位数"]) / max(prev["岗位数"], 1) * 100
        sal_change = (latest["中位薪资"] - prev["中位薪资"]) / max(prev["中位薪资"], 1) * 100

        verdict = ""
        if job_change > 10 and sal_change > 2:
            verdict = "扩张期（岗位量↑薪资↑），求职窗口好。"
        elif job_change > 10:
            verdict = "扩量期（岗位量↑但薪资持平），可能偏初级岗。"
        elif sal_change > 5:
            verdict = "提薪期（岗位量稳但薪资↑），可能偏高端岗争夺。"
        elif job_change < -10:
            verdict = "收缩期（岗位量↓），谨慎窗口。"
        else:
            verdict = "稳态期，正常波动范围内。"

        trends.append(Trend(
            title="🔍 市场综合信号",
            body=f"岗位量 {_safe_pct(prev['岗位数'], latest['岗位数'])}，"
                 f"薪资 {_safe_pct(prev['中位薪资'], latest['中位薪资'])}。"
                 f"判断：{verdict}",
            direction="↑" if job_change > 0 and sal_change > 0 else "↓" if job_change < 0 else "→",
            strength="strong" if abs(job_change) > 15 or abs(sal_change) > 7 else "medium",
        ))

    return trends


# ──────────────────────────────────────────────
# 技能投资回报分析
# ──────────────────────────────────────────────

class SkillROIModel:
    """技能投资回报模型。

    综合需求频率与薪资水平计算 ROI 得分：
        ROI = 需求频率归一化 × 45% + 薪资归一化 × 55%

    分为三档：
    - 🥇 黄金：高薪+高需
    - 🥈 白银：高薪+中需 或 中薪+高需
    - 🥉 青铜：其余
    """

    def __init__(self, jobs: pd.DataFrame):
        self.jobs = jobs

    def analyze(self, min_demand: int = 3) -> list[dict]:
        """执行 ROI 分析。

        Args:
            min_demand: 最低需求次数过滤（默认 3）

        Returns:
            排序后的技能 ROI 列表，每项含:
            - skill: 技能名
            - demand: 需求次数
            - median_salary: 中位薪资（K/月）
            - avg_salary: 均值薪资（K/月）
            - roi_score: ROI 综合得分 0-100
            - tier: 等级 (gold/silver/bronze)
        """
        from collections import defaultdict
        import re

        real = self.jobs[self.jobs["salary_avg"].notna()].copy()
        if real.empty:
            return []

        skill_freq: dict[str, int] = defaultdict(int)
        skill_salaries: dict[str, list[float]] = defaultdict(list)

        for _, row in real.iterrows():
            skills_str = row.get("skills", "")
            if pd.isna(skills_str) or not skills_str:
                continue

            s_min = row.get("salary_min")
            s_max = row.get("salary_max")
            s_unit = row.get("salary_unit", "month")

            mid_k = None
            if pd.notna(s_min) and pd.notna(s_max):
                mid = (s_min + s_max) / 2
                if s_unit == "year":
                    mid = mid / 12
                elif s_unit == "day":
                    mid = mid * 22
                mid_k = round(mid / 1000, 1)
                if mid_k > 100:
                    mid_k = None

            for sk in re.split(r"[,;，；、]+", str(skills_str)):
                sk = sk.strip()
                if not sk:
                    continue
                skill_freq[sk] += 1
                if mid_k is not None:
                    skill_salaries[sk].append(mid_k)

        if not skill_freq:
            return []

        max_freq = max(skill_freq.values())
        results = []

        for sk, freq in skill_freq.items():
            if freq < min_demand:
                continue

            salaries = skill_salaries.get(sk, [])
            if salaries:
                sorted_sal = sorted(salaries)
                avg_salary = round(sum(salaries) / len(salaries), 1)
                median_salary = sorted_sal[len(sorted_sal) // 2]
            else:
                avg_salary = 0
                median_salary = 0

            freq_norm = freq / max_freq
            sal_norm = median_salary / 30 if median_salary else 0
            roi_score = round((freq_norm * 0.45 + sal_norm * 0.55) * 100)

            # 分级
            if median_salary >= 18 and freq >= 20:
                tier = "gold"
            elif median_salary >= 15 and freq >= 10:
                tier = "gold"
            elif (median_salary >= 15 and freq >= 5) or (freq >= 20 and median_salary >= 12):
                tier = "silver"
            else:
                tier = "bronze"

            results.append({
                "skill": sk,
                "demand": freq,
                "median_salary": median_salary,
                "avg_salary": avg_salary,
                "roi_score": roi_score,
                "tier": tier,
            })

        results.sort(key=lambda x: -x["roi_score"])
        return results

    def tier_stats(self, results: list[dict]) -> dict:
        """按等级汇总统计。"""
        tiers = {"gold": [], "silver": [], "bronze": []}
        for r in results:
            tiers[r["tier"]].append(r)
        return {
            t: {
                "count": len(items),
                "avg_demand": round(sum(i["demand"] for i in items) / len(items)) if items else 0,
                "avg_salary": round(sum(i["median_salary"] for i in items) / len(items), 1) if items else 0,
            }
            for t, items in tiers.items()
        }

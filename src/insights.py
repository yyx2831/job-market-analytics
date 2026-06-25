"""行动级观点引擎 - 不仅描述现象，更给出可执行的行动建议。

每一条观点都力求回答：知道了这个，我该怎么做？
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import pandas as pd


@dataclass
class Insight:
    title: str
    body: str
    level: str = "info"       # highlight / warning / info
    section: str = "general"  # general / salary / skill / company / career
    action: str = ""           # 可执行建议


def _skill_stats(jobs: pd.DataFrame) -> dict:
    """从 skills 列计算每个技能的出现次数和薪资聚合。"""
    counter = Counter()
    salaries = defaultdict(list)
    for _, row in jobs.iterrows():
        s = row.get("skills", "")
        if pd.isna(s) or not s:
            continue
        for t in re.split(r'[,;，；、]+', str(s)):
            t = t.strip()
            if t and len(t) >= 2:
                counter[t] += 1
                salaries[t].append(row["salary_avg"])
    return {
        sk: {"count": cnt, "avg_salary": sum(salaries[sk]) / len(salaries[sk])}
        for sk, cnt in counter.items() if len(salaries[sk]) >= 2
    }


def _format_salary(val: float) -> str:
    k = val / 1000
    return f"¥{k:.1f}K" if k < 10 else f"¥{k:.0f}K"


def generate_insights(jobs: pd.DataFrame) -> list[Insight]:
    """从岗位数据生成行动级观点。"""
    insights = []

    real = jobs[jobs["salary_avg"].notna()]
    if real.empty:
        return [Insight("数据不足", "当前筛选条件下无足够数据支撑分析。", "warning")]

    salary = real["salary_avg"]
    p25, p50, p75 = salary.quantile([0.25, 0.5, 0.75])
    total = len(jobs)
    city_name = jobs["city"].iloc[0] if jobs["city"].nunique() == 1 else "多城市"

    # ── 1. 市场全貌 ──
    insights.append(Insight(
        title=f"📊 {city_name}市场全貌",
        body=f"共分析 {total} 个岗位（{jobs['company_name'].nunique()} 家公司）。"
             f"薪资中位数 {_format_salary(p50)}，均值 {_format_salary(salary.mean())}。"
             f"月薪 3K-{int(salary.max()/1000)}K 宽幅分布，{'存在明显长尾高薪层' if salary.mean() > p50 * 1.15 else '分布相对均匀'}。",
        level="highlight",
        section="general",
        action=f"你的薪资锚点：平均 {_format_salary(salary.mean())}，中位 {_format_salary(p50)}。"
               f"求职可将目标定在 {_format_salary(p75)} 以上进入前25%。"
    ))

    # ── 2. 薪资分层与跃迁路径 ──
    tiers = [
        ("底层", salary.min(), p25, "入门/基础岗位"),
        ("腰部", p25, p75, f"主力岗位，覆盖50%市场"),
        ("头部", p75, salary.max(), f"高薪区间，前25%"),
    ]
    tier_lines = []
    for name, lo, hi, desc in tiers:
        tier_lines.append(f"• {name}（{_format_salary(lo)}–{_format_salary(hi)}）：{desc}")
    insights.append(Insight(
        title="📈 薪资三级跳",
        body="\n".join(tier_lines),
        level="highlight",
        section="salary",
        action=f"目标策略：先进入腰部（≥{_format_salary(p25)}），积累2-3年后冲刺头部（≥{_format_salary(p75)}）。"
               f"每跨越一层薪资增幅约 {p75/p25:.1f} 倍。"
    ))

    # ── 3. 经验-薪资台阶 ──
    exp_salary = real.groupby("experience")["salary_avg"].agg(["mean", "median", "count"])
    exp_salary = exp_salary[exp_salary["count"] >= 3].sort_values("mean")
    if len(exp_salary) >= 3:
        steps = []
        prev_m = None
        for exp, row in exp_salary.iterrows():
            m = row["mean"]
            step = ""
            if prev_m and prev_m > 0:
                jump = (m - prev_m) / prev_m * 100
                step = f"（+{jump:.0f}%）" if jump > 0 else ""
            steps.append(f"• {exp}：均薪 {_format_salary(m)} {step}")
            prev_m = m
        insights.append(Insight(
            title="🪜 经验薪资台阶",
            body="\n".join(steps),
            level="info",
            section="career",
            action="每个经验层级的薪资跃升幅度，帮你规划职业节奏。找到跳跃最大的那个台阶。"
        ))

    # ── 4. 技能组合定价 ──
    sk = _skill_stats(real)
    if sk:
        # 高频技能薪资
        top_freq = sorted(sk.items(), key=lambda x: -x[1]["count"])[:8]
        freq_lines = [f"• {s}：需求 {d['count']}次，均薪 {_format_salary(d['avg_salary'])}"
                      for s, d in top_freq]
        insights.append(Insight(
            title="🔧 核心技能定价",
            body="\n".join(freq_lines),
            level="info",
            section="skill",
            action="高频=门票技能，建议至少持有2-3项。关注高薪但低频的技能差异化。"
        ))

        # 高溢价技能（出现≥3次，薪资>p75）
        premium = [(s, d["avg_salary"], d["count"])
                   for s, d in sk.items() if d["count"] >= 3 and d["avg_salary"] > p75]
        premium.sort(key=lambda x: -x[1])
        if premium:
            p_list = [f"• {s}：均薪 {_format_salary(v)}（需求{cnt}次）" for s, v, cnt in premium[:6]]
            insights.append(Insight(
                title="💎 高溢价技能（值得投资）",
                body="\n".join(p_list) + f"\n\n这些技能的拥有者薪资高于市场75%分位（{_format_salary(p75)}）。",
                level="highlight",
                section="skill",
                action="如果你的技能栈中能增加1-2项高溢价技能，薪资谈判空间大幅提升。优先学与现有技能互补的。"
            ))

        # 技能升级建议：从基础到高薪的路径
        basic_skills = {s for s, d in sk.items() if d["avg_salary"] < p50 and d["count"] >= 5}
        adv_skills = {s for s, d in sk.items() if d["avg_salary"] > p75}
        # Find co-occurring pairs
        skill_pairs = Counter()
        for _, row in real.iterrows():
            s = row.get("skills", "")
            if pd.isna(s) or not s:
                continue
            tokens = [t.strip() for t in re.split(r'[,;，；、]+', str(s)) if t.strip()]
            for i, t1 in enumerate(tokens):
                for t2 in tokens[i+1:]:
                    if (t1 in basic_skills and t2 in adv_skills) or (t2 in basic_skills and t1 in adv_skills):
                        skill_pairs[(t1, t2)] += 1

        if skill_pairs:
            top_pairs = skill_pairs.most_common(3)
            upgrade_tips = []
            for (a, b), cnt in top_pairs:
                sa = sk.get(a, {}).get("avg_salary", 0)
                sb = sk.get(b, {}).get("avg_salary", 0)
                upgrade_tips.append(
                    f"• 「{a}」→ 搭配「{b}」：薪资从{_format_salary(min(sa,sb))}→{_format_salary(max(sa,sb))}"
                )
            insights.append(Insight(
                title="🔄 技能升级路径",
                body=f"最常见的技能升级组合（同一岗位中同时出现基础+高薪技能）：\n" + "\n".join(upgrade_tips),
                level="highlight",
                section="skill",
                action="这些都是市场上验证过的升级路径，不是凭空猜测。你的下一个学习方向就在这里。"
            ))

    # ── 5. 行业薪资地图 ──
    ind_salary = real.groupby("industry")["salary_avg"].agg(["mean", "count"])
    ind_salary = ind_salary[ind_salary["count"] >= 3].sort_values("mean", ascending=False)
    if len(ind_salary) >= 3:
        ind_lines = [f"• {ind}：均薪 {_format_salary(r['mean'])}（{int(r['count'])}岗）"
                     for ind, r in ind_salary.iterrows()]
        insights.append(Insight(
            title="🏭 行业薪资地图",
            body="\n".join(ind_lines),
            level="info",
            section="salary",
            action=f"换行业是涨薪最快的路径之一。头部行业（{ind_salary.index[0]}）比尾部高 {ind_salary.iloc[0]['mean']/ind_salary.iloc[-1]['mean']:.1f} 倍。"
        ))

    # ── 6. 学历 ROI ──
    edu_salary = real.groupby("education")["salary_avg"].agg(["mean", "median", "count"])
    edu_salary = edu_salary[edu_salary["count"] >= 3].sort_values("mean")
    if len(edu_salary) >= 2:
        edu_lines = [f"• {edu}：中位 {_format_salary(r['median'])}，均 {_format_salary(r['mean'])}"
                     for edu, r in edu_salary.iterrows()]
        insights.append(Insight(
            title="🎓 学历投资回报",
            body="\n".join(edu_lines),
            level="info",
            section="career",
            action="学历是成本很高的投资。如果差距<30%，更值得花时间在技能积累上而非学历提升。"
        ))

    # ── 7. 公司规模薪资对比 ──
    if "company_size" in real.columns:
        size_salary = real.groupby("company_size")["salary_avg"].agg(["mean", "count"])
        size_salary = size_salary[size_salary["count"] >= 3].sort_values("mean", ascending=False)
        if len(size_salary) >= 2:
            size_lines = [f"• {s}：{_format_salary(r['mean'])}（{int(r['count'])}岗）"
                          for s, r in size_salary.iterrows()]
            top_size = size_salary.index[0]
            insights.append(Insight(
                title="🏢 规模 ≠ 薪资",
                body="\n".join(size_lines),
                level="info",
                section="company",
                action=f"「{top_size}」薪资最高。大公司未必出手最阔，看准规模定位。"
            ))

    # ── 8. 招聘活跃公司 ──
    co_rank = real.groupby("company_name").agg(
        岗位数=("title", "count"),
        平均薪资=("salary_avg", "mean"),
    ).query("岗位数 >= 3").sort_values("岗位数", ascending=False)
    if not co_rank.empty:
        top_cos = co_rank.head(10)
        co_lines = [f"• {c}：{int(r['岗位数'])}岗，均薪 {_format_salary(r['平均薪资'])}"
                    for c, r in top_cos.iterrows()]
        insights.append(Insight(
            title="🔥 活跃雇主 TOP10",
            body="\n".join(co_lines),
            level="info",
            section="company",
            action="这些公司当前招聘需求旺盛，面试机会多。关注它们的技术栈偏好可精准投递。"
        ))

    # ── 9. 薪资分布诊断 ──
    cv = salary.std() / salary.mean() if salary.mean() > 0 else 0
    skew = "右偏（高薪拉动）" if salary.mean() > salary.median() * 1.05 else \
           "左偏（低薪集中）" if salary.mean() < salary.median() * 0.95 else "近正态"
    insights.append(Insight(
        title="📊 薪资结构诊断",
        body=f"分布形态：{skew}。变异系数 {cv:.2f}——"
             f"{'机会分化显著，选对赛道收益差异大' if cv > 0.5 else '同质化程度高，差异化是关键' if cv < 0.3 else '存在分层但跨层可期'}。",
        level="info" if cv > 0.3 else "warning",
        section="salary",
        action=f"{'建议用技能组合或行业选择来离群' if cv > 0.5 else '通用能力之外，重点打造1-2个长板' if cv < 0.3 else '找到薪资跃迁最快的经验/技能节点'}。"
    ))

    # ── 10. 综合行动清单 ──
    action_items = []

    # Best experience
    if "experience" in real.columns:
        exp_rank = real.groupby("experience")["salary_avg"].median().sort_values(ascending=False)
        if not exp_rank.empty:
            action_items.append(
                f"🎯 优先匹配「{exp_rank.index[0]}」岗位，薪资最高（中位{_format_salary(exp_rank.iloc[0])}）"
            )

    # Best industry
    if "industry" in real.columns:
        ind_rank = real.groupby("industry")["salary_avg"].mean().sort_values(ascending=False)
        ind_n = min(3, len(ind_rank))
        if ind_n > 0:
            top_inds = "、".join(ind_rank.index[:ind_n])
            action_items.append(f"🏭 高薪行业方向：{top_inds}")

    # Best skills to learn
    if sk:
        high = [(s, d["avg_salary"], d["count"])
                for s, d in sk.items() if d["count"] >= 3 and d["avg_salary"] > p75]
        high.sort(key=lambda x: -x[1])
        if high:
            action_items.append(f"📚 技能升级推荐：{'、'.join(s for s,_,_ in high[:3])}")

    if action_items:
        insights.append(Insight(
            title="✅ 你的行动清单",
            body="\n".join(action_items),
            level="highlight",
            section="general",
            action="以上建议基于实时市场数据，有效期约1-2个月。关注变化，动态调整策略。"
        ))

    return insights


def compare_cities(jobs: pd.DataFrame, cities: list[str]) -> list[Insight]:
    """城市间对比分析。"""
    cities_data = {}
    for c in cities:
        cd = jobs[(jobs["city"] == c) & (jobs["salary_avg"].notna())]
        if len(cd) >= 10:
            cities_data[c] = cd

    if len(cities_data) < 2:
        return [Insight("对比数据不足", "需要至少两个城市各10条以上数据。", "warning")]

    insights = []
    comparisons = [
        ("平均薪资", lambda df: df["salary_avg"].mean()),
        ("中位薪资", lambda df: df["salary_avg"].median()),
    ]

    for name, stat_fn in comparisons:
        rankings = [(c, stat_fn(cd), len(cd)) for c, cd in cities_data.items()]
        rankings.sort(key=lambda x: -x[1])

        lines = [f"{i+1}. {c} ¥{v/1000:.1f}K ({cnt}样本)" for i, (c, v, cnt) in enumerate(rankings)]
        top, bot = rankings[0][0], rankings[-1][0]
        gap = rankings[0][1] / rankings[-1][1] if rankings[-1][1] > 0 else 1

        insights.append(Insight(
            title=f"🏆 {name}城市排行",
            body="\n".join(lines) + f"\n\n{top}是{bot}的 {gap:.1f} 倍。",
            level="highlight",
            section="salary",
            action=f"{top}排第一，但别忘了算生活成本。真正的可支配收入才是衡量标准。"
        ))

    return insights

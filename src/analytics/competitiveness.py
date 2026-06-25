"""求职竞争力指数 — 多维评分模型（纯计算，无需 LLM）。

维度：
  1. 技能匹配度   — 你的技能栈在市场中的需求覆盖率
  2. 薪资定位     — 你的期望/当前薪资在同城同岗中的百分位
  3. 技能稀缺性   — 你掌握的技能中，最稀缺的那项的值
  4. 市场热度     — 匹配岗位的绝对数量 & 增长趋势
  5. 经验/学历对齐 — 你与目标岗位要求的匹配

输出：
  - 0-100 竞争力总分（加权）
  - 各维度明细 + 建议
  - 同城同岗排名（前 25%/50%/75%）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ── 默认权重（可调） ──
DEFAULT_WEIGHTS = {
    "skill_match": 0.35,
    "salary_position": 0.25,
    "skill_rarity": 0.15,
    "market_heat": 0.15,
    "exp_edu_align": 0.10,
}


@dataclass
class CompetitorProfile:
    """求职者画像。"""
    skills: List[str]
    target_city: str
    target_salary: float          # 期望月薪（元）
    experience: str = "3-4年"     # 1年以下/1-3年/3-4年/5-7年/8-9年/10年以上
    education: str = "本科"
    target_industry: str = ""     # 空 = 不限
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


@dataclass
class ScoreBreakdown:
    """各维度得分明细。"""
    skill_match: float = 0.0
    salary_position: float = 0.0
    skill_rarity: float = 0.0
    market_heat: float = 0.0
    exp_edu_align: float = 0.0
    total: float = 0.0
    percentile: float = 0.0          # 在全市同岗中的排名百分比
    total_matched_jobs: int = 0
    salary_rank: str = ""            # "top 10%" / "top 25%" / "average" / "below average"
    top_missing_skills: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)


class CompetitivenessAnalyzer:
    """求职竞争力分析引擎。

    用法:
        analyzer = CompetitivenessAnalyzer(jobs_df)
        profile = CompetitorProfile(
            skills=["Python", "SQL", "Docker"],
            target_city="成都", target_salary=15000,
        )
        result = analyzer.analyze(profile)
    """

    def __init__(self, jobs: pd.DataFrame):
        self.jobs = jobs.copy()
        self.jobs["skills_clean"] = self.jobs["skills"].fillna("").apply(
            lambda s: [x.strip() for x in s.split(",") if x.strip()]
        )
        self.jobs["skills_text"] = self.jobs["skills_clean"].apply(
            lambda x: " ".join(x) if x else ""
        )

        # 全局技能词库 + TF-IDF
        valid = self.jobs[self.jobs["skills_text"] != ""]
        if not valid.empty:
            self.tfidf = TfidfVectorizer(token_pattern=r"(?u)\b\w[\w+#.-]*\b")
            self.skill_matrix = self.tfidf.fit_transform(valid["skills_text"])
            self.valid_indices = valid.index.tolist()
        else:
            self.tfidf = None
            self.skill_matrix = None
            self.valid_indices = []

        # 技能频率表（用于稀缺性计算）
        all_skills = []
        for sl in self.jobs["skills_clean"]:
            all_skills.extend(sl)
        skill_counts = pd.Series(all_skills).value_counts()
        self.skill_freq = skill_counts
        self.total_skills = len(all_skills)

    def analyze(self, profile: CompetitorProfile) -> ScoreBreakdown:
        w = profile.weights
        result = ScoreBreakdown()

        # 1. 过滤目标市场
        market = self.jobs[self.jobs["city"] == profile.target_city].copy()
        if profile.target_industry:
            market = market[market["industry"].str.contains(
                profile.target_industry, na=False
            )]

        if market.empty:
            result.insights.append("⚠️ 目标城市暂无数据，无法评估。")
            return result

        result.total_matched_jobs = len(market)

        # ── 维度 1: 技能匹配度 ──
        result.skill_match = self._calc_skill_match(profile.skills, market)

        # ── 维度 2: 薪资定位 ──
        result.salary_position, result.salary_rank = self._calc_salary_position(
            profile.target_salary, market
        )

        # ── 维度 3: 技能稀缺性 ──
        result.skill_rarity = self._calc_skill_rarity(profile.skills)

        # ── 维度 4: 市场热度 ──
        result.market_heat = self._calc_market_heat(profile.skills, market)

        # ── 维度 5: 经验学历对齐 ──
        result.exp_edu_align = self._calc_exp_edu_align(profile, market)

        # ── 加权总分 ──
        result.total = (
            w["skill_match"] * result.skill_match
            + w["salary_position"] * result.salary_position
            + w["skill_rarity"] * result.skill_rarity
            + w["market_heat"] * result.market_heat
            + w["exp_edu_align"] * result.exp_edu_align
        )
        result.total = min(100, round(result.total, 1))

        # ── 全局排名（同城 + 同经验段） ──
        result.percentile = self._calc_global_percentile(profile, market)

        # ── 缺失技能 ──
        result.top_missing_skills = self._find_missing_skills(profile.skills, market)

        # ── 生成洞察 ──
        result.insights = self._generate_insights(result, profile)

        return result

    # ══════════════════════════════════════════════
    #  维度计算
    # ══════════════════════════════════════════════

    def _calc_skill_match(self, skills: List[str], market: pd.DataFrame) -> float:
        """技能覆盖度：你的技能能命中多少市场岗位的需求。"""
        if not skills or market.empty:
            return 0.0
        # 每个岗位的技能需求
        job_skills = market["skills_clean"]
        total_jobs = len(job_skills)

        matched = 0
        for js in job_skills:
            if js and set(s.name.lower() for s in pd.Series(skills).str.lower()).intersection(
                set(x.lower() for x in js)
            ):
                matched += 1

        coverage = matched / total_jobs if total_jobs else 0
        # 同时考虑你技能能命中岗位需求的程度
        total_hits = 0
        for js in job_skills:
            for skill in skills:
                if js and any(str(skill).lower() in x.lower() for x in js):
                    total_hits += 1
                    break

        hit_rate = total_hits / total_jobs if total_jobs else 0
        return round(min(100, (coverage * 60 + hit_rate * 40)), 1)

    def _calc_salary_position(
        self, target: float, market: pd.DataFrame
    ) -> Tuple[float, str]:
        """薪资百分位 & 评级。"""
        salaries = market["salary_avg"].dropna()
        if salaries.empty or target <= 0:
            return 0.0, "无数据"

        pct = (salaries < target).sum() / len(salaries) * 100
        p50 = salaries.median()
        p75 = salaries.quantile(0.75)
        p90 = salaries.quantile(0.90)

        if target >= p90:
            rank = "🏆 top 10%"
            score = 95
        elif target >= p75:
            rank = "🥇 top 25%"
            score = 80
        elif target >= p50:
            rank = "🥈 above average"
            score = 55
        elif target >= salaries.quantile(0.25):
            rank = "🥉 average"
            score = 35
        else:
            rank = "📉 below average"
            score = max(5, round(pct))

        # 如果远超市场 → 可能期望过高，做高斯衰减
        if pct > 95:
            score = max(60, 100 - (pct - 95) * 4)

        return score, rank

    def _calc_skill_rarity(self, skills: List[str]) -> float:
        """技能稀缺性：越少见的技能分越高。"""
        if not skills or self.skill_freq.empty:
            return 0.0

        scores = []
        for s in skills:
            sl = s.lower()
            matches = [k for k in self.skill_freq.index if sl in k.lower()]
            if not matches:
                rarity = 95  # 市场中完全没出现的 → 极高稀缺
            else:
                best_count = min(self.skill_freq[matches])
                rarity = max(5, 100 * (1 - best_count / max(1, self.skill_freq.max())))

            scores.append(rarity)

        return round(sum(scores) / len(scores), 1)

    def _calc_market_heat(self, skills: List[str], market: pd.DataFrame) -> float:
        """市场热度：匹配岗位的数量 & 近期活跃度。"""
        if market.empty or not skills:
            return 0.0

        # 数量分（对数缩放）
        n_jobs = len(market)
        qty_score = min(100, math.log2(n_jobs + 1) * 20)

        # 技能需求密集度
        skill_hits = 0
        for js in market["skills_clean"]:
            for skill in skills:
                if js and any(str(skill).lower() in x.lower() for x in js):
                    skill_hits += 1
                    break
        density = skill_hits / n_jobs if n_jobs else 0
        density_score = density * 100

        # 近期活跃（7天内发布的岗位）
        if "publish_time" in market.columns:
            recent = market[market["publish_time"].notna()]
            if not recent.empty:
                recent["pub_dt"] = pd.to_datetime(
                    recent["publish_time"], format="mixed", errors="coerce"
                )
                latest = recent["pub_dt"].max()
                if pd.notna(latest):
                    days_in = (pd.Timestamp.now() - latest).days
                    in_window = recent[recent["pub_dt"] >= pd.Timestamp.now() - pd.Timedelta(days=7)]
                    freshness = len(in_window) / max(1, len(recent)) * 100
                else:
                    freshness = 50
            else:
                freshness = 50
        else:
            freshness = 50

        return round(min(100, qty_score * 0.4 + density_score * 0.3 + freshness * 0.3), 1)

    def _calc_exp_edu_align(
        self, profile: CompetitorProfile, market: pd.DataFrame
    ) -> float:
        """经验 & 学历匹配度。"""
        score = 0.0
        n = 0

        if profile.experience and "experience" in market.columns:
            exp_data = market["experience"].dropna()
            if not exp_data.empty:
                exp_match = exp_data.str.contains(
                    profile.experience.replace("年以上", ""), na=False
                ).mean()
                score += exp_match * 100
                n += 1

        if profile.education and "education" in market.columns:
            edu_data = market["education"].dropna()
            if not edu_data.empty:
                edu_match = edu_data.str.contains(profile.education, na=False).mean()
                score += edu_match * 100
                n += 1

        return round(score / n, 1) if n else 0.0

    def _calc_global_percentile(
        self, profile: CompetitorProfile, market: pd.DataFrame
    ) -> float:
        """在同城+同经验段人群中，你的技能组合薪资能排多少。"""
        # 简化：用技能匹配度 × 薪资分作为代理
        if market.empty:
            return 50.0

        # 计算市场中所有「可匹配此技能组」的岗位薪资分布
        salaries = market["salary_avg"].dropna()
        if salaries.empty:
            return 50.0

        target = profile.target_salary
        pct = (salaries < target).sum() / len(salaries) * 100
        return round(pct, 1)

    def _find_missing_skills(
        self, my_skills: List[str], market: pd.DataFrame
    ) -> List[str]:
        """找到市场中需求大、但我没有的技能。"""
        if market.empty or not my_skills:
            return []

        my_set = set(s.lower() for s in my_skills)
        market_skills = []
        for js in market["skills_clean"]:
            market_skills.extend(js)

        from collections import Counter
        freq = Counter(s.lower() for s in market_skills if s.lower() not in my_set)
        top = freq.most_common(10)
        return [s for s, _ in top if freq[s] >= 3]

    def _generate_insights(
        self, result: ScoreBreakdown, profile: CompetitorProfile
    ) -> List[str]:
        insights = []

        if result.total >= 80:
            insights.append(
                f"🚀 综合竞争力 {result.total} 分，在 {profile.target_city} 市场竞争力很强"
            )
        elif result.total >= 60:
            insights.append(
                f"✅ 综合竞争力 {result.total} 分，中等偏上，有提升空间"
            )
        elif result.total >= 40:
            insights.append(
                f"⚡ 综合竞争力 {result.total} 分，建议针对弱项补强"
            )
        else:
            insights.append(
                f"🔧 综合竞争力 {result.total} 分，需要系统性提升"
            )

        # 薪资维度
        insights.append(
            f"💰 期望薪资 ¥{profile.target_salary:,.0f} 处于 {result.salary_rank}"
        )

        # 技能缺口
        if result.top_missing_skills:
            top3 = result.top_missing_skills[:3]
            insights.append(
                f"📚 推荐学习: {', '.join(top3)}"
            )

        # 市场热度
        insights.append(
            f"📊 {profile.target_city} 匹配 {result.total_matched_jobs} 个岗位"
        )

        # 弱项定位
        if result.skill_match < 50:
            insights.append("💡 技能覆盖面偏窄，建议拓展 1-2 个关联技能")
        if result.skill_rarity < 30:
            insights.append("💡 技能较常见，建议深入掌握一项稀缺技术")
        if result.exp_edu_align < 40:
            insights.append("💡 经验/学历与市场需求匹配度偏低")

        return insights


def batch_compare(
    profiles: List[CompetitorProfile], jobs: pd.DataFrame
) -> pd.DataFrame:
    """批量对比多个求职者画像。"""
    analyzer = CompetitivenessAnalyzer(jobs)
    rows = []
    for i, p in enumerate(profiles):
        r = analyzer.analyze(p)
        rows.append({
            "编号": i + 1,
            "技能": ", ".join(p.skills[:5]),
            "目标城市": p.target_city,
            "期望薪资": p.target_salary,
            "竞争力总分": r.total,
            "薪资定位": r.salary_rank,
            "技能匹配": r.skill_match,
            "市场热度": r.market_heat,
            "排名": f"前 {100 - r.percentile:.0f}%",
        })
    return pd.DataFrame(rows)

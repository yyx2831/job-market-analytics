"""岗位推荐引擎 — 基于技能匹配 + 薪资拟合 + 多维度加权的智能推荐。

核心流程:
  1. 用户输入 → 技能向量(TF-IDF) + 约束条件(城市/薪资/经验/行业)
  2. 候选人池 = 过滤条件(query) ∩ 用户约束
  3. 得分 = α·技能余弦相似度 + β·薪资拟合度 + γ·其他信号

支持:
  - 技能语义匹配(jieba 分词 + TF-IDF)
  - 薪资带宽匹配(目标薪资在岗位薪资区间内的拟合度)
  - 城市偏好加权
  - 经验等级对齐
"""

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class JobSeeker:
    """求职者画像。"""
    target_skills: List[str]           # 目标技能列表
    preferred_cities: List[str] = field(default_factory=list)  # 偏好城市
    target_salary: Optional[float] = None  # 期望月薪(元)
    experience_level: Optional[str] = None # 经验要求, None=不限制
    preferred_industries: List[str] = field(default_factory=list)  # 偏好行业
    weights: Dict[str, float] = field(default_factory=lambda: {
        "skills": 0.55,
        "salary_fit": 0.25,
        "relevance": 0.20,
    })


class JobRecommender:
    """岗位推荐引擎。"""

    def __init__(self, jobs_df: pd.DataFrame):
        """
        Args:
            jobs_df: 完整岗位数据 DataFrame，需含 skills / salary_min / salary_max / salary_avg / city / experience
        """
        self.jobs = jobs_df.copy()
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.skill_matrix = None
        self._fitted = False

    def _clean_skills(self, val) -> str:
        """Normalize skills into whitespace-separated tokens."""
        if pd.isna(val):
            return ""
        try:
            items = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(val).split(",") if s.strip()]
        return " ".join(str(s).strip() for s in items)

    def fit(self) -> "JobRecommender":
        """构建技能 TF-IDF 矩阵。"""
        texts = self.jobs["skills"].apply(self._clean_skills)
        self.vectorizer = TfidfVectorizer(
            token_pattern=r"(?u)\b\S+\b",
            max_features=300,
            sublinear_tf=True,
        )
        self.skill_matrix = self.vectorizer.fit_transform(texts)
        self._fitted = True
        return self

    def _skills_similarity(self, seeker_vec) -> np.ndarray:
        """返回 seeker 向量与所有岗位的余弦相似度 [0,1] 数组。"""
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        sim = cosine_similarity(seeker_vec, self.skill_matrix)[0]
        # 归一化到 [0,1]
        return sim

    def _salary_fit(self, salaries: pd.Series, target: Optional[float]) -> np.ndarray:
        """
        薪资拟合度:
        - 岗位区间 [min, max] 与目标值的接近程度
        - 目标在区间内 → 1.0
        - 目标在区间外 → 按距离衰减 (高斯衰减)
        """
        n = len(salaries)
        if target is None or target <= 0:
            return np.full(n, 0.5)  # 不设偏好 → 中性

        fit = np.zeros(n)
        for i in range(n):
            lo = self.jobs.iloc[i].get("salary_min", 0) or 0
            hi = self.jobs.iloc[i].get("salary_max", 0) or 0

            if lo == 0 and hi == 0:
                fit[i] = 0.3
                continue

            if lo <= target <= hi:
                fit[i] = 1.0
            else:
                # 距离带宽的比例
                dist = min(abs(target - lo), abs(target - hi))
                bandwidth = max(hi - lo, target * 0.1)  # 防止除零
                fit[i] = math.exp(- (dist / bandwidth) ** 2)

        return fit

    def _relevance_score(self, seeker: JobSeeker) -> np.ndarray:
        """计算额外相关性分数: 城市偏好 + 行业偏好 + 经验匹配。"""
        n = len(self.jobs)
        scores = np.ones(n) * 0.5  # 基准

        # 城市偏好
        if seeker.preferred_cities:
            city_set = set(seeker.preferred_cities)
            mask = self.jobs["city"].isin(city_set)
            scores[mask] = 1.0
            scores[~mask] = 0.2

        # 行业偏好 (轻微加权)
        if seeker.preferred_industries:
            ind_set = set(seeker.preferred_industries)
            ind_mask = self.jobs["industry"].isin(ind_set)
            scores = np.where(ind_mask, np.minimum(scores + 0.15, 1.0), scores)

        # 经验匹配
        if seeker.experience_level:
            exp = seeker.experience_level
            exp_col = self.jobs["experience"].fillna("")
            # 简单规则: 含"无需经验" + "不限" → 全匹配
            match_mask = (
                exp_col.str.contains(exp, case=False, na=False)
                | exp_col.str.contains("不限", case=False, na=False)
                | exp_col.str.contains("无需经验", case=False, na=False)
                | (exp_col == "")
            )
            scores[match_mask] = np.minimum(scores[match_mask] + 0.1, 1.0)

        return scores

    def recommend(
        self,
        seeker: JobSeeker,
        top_k: int = 20,
        min_salary: Optional[float] = None,
        max_salary: Optional[float] = None,
    ) -> pd.DataFrame:
        """生成推荐列表。

        Args:
            seeker: 求职者画像
            top_k: 返回数量
            min_salary: 最低月薪过滤(元)
            max_salary: 最高月薪过滤(元)

        Returns:
            DataFrame with columns: 原始列 + score / skills_sim / salary_fit / relevance / recommended_for
        """
        if not self._fitted:
            self.fit()

        # ── Step 1: 技能语义搜索 ──
        skill_query = " ".join(seeker.target_skills)
        seeker_vec = self.vectorizer.transform([skill_query])
        skills_sim = self._skills_similarity(seeker_vec)

        # ── Step 2: 薪资拟合 ──
        salary_fit = self._salary_fit(
            self.jobs["salary_avg"], seeker.target_salary
        )

        # ── Step 3: 相关性 ──
        relevance = self._relevance_score(seeker)

        # ── Step 4: 加权综合 ──
        w = seeker.weights
        scores = (
            w["skills"] * skills_sim
            + w["salary_fit"] * salary_fit
            + w["relevance"] * relevance
        )

        # ── Step 5: 构建结果 ──
        result = self.jobs.copy()
        result["skills_sim"] = np.round(skills_sim, 4)
        result["salary_fit"] = np.round(salary_fit, 4)
        result["relevance"] = np.round(relevance, 4)
        result["score"] = np.round(scores, 4)

        # 排序 & 过滤
        result = result.sort_values("score", ascending=False)

        if min_salary is not None:
            result = result[result["salary_avg"].fillna(0) >= min_salary]
        if max_salary is not None:
            result = result[result["salary_avg"].fillna(float("inf")) <= max_salary]

        return result.head(top_k)

    def recommend_by_job_id(self, job_id: str, top_k: int = 10) -> pd.DataFrame:
        """基于一个岗位 ID 推荐相似岗位（协同过滤简化版）。"""
        if not self._fitted:
            self.fit()

        # 找到该岗位的索引
        matches = self.jobs[self.jobs["id"].astype(str) == str(job_id)]
        if matches.empty:
            raise ValueError(f"Job {job_id} not found")

        idx = matches.index[0]
        anchor_vec = self.skill_matrix[idx]

        # 余弦相似度
        sims = cosine_similarity(anchor_vec, self.skill_matrix)[0]

        result = self.jobs.copy()
        result["score"] = np.round(sims, 4)

        # 排除自身
        result = result.drop(idx)
        return result.sort_values("score", ascending=False).head(top_k)


def skill_gap_analysis(seeker: JobSeeker, recommendations: pd.DataFrame) -> List[Dict]:
    """技能缺口分析：对比求职者已有技能与推荐岗位要求。

    Returns:
        [{skill: str, demand_count: int, avg_salary: float, gap_level: str}]
    """
    missing_skills = []
    seeker_set = set(s.lower() for s in seeker.target_skills)

    skill_counts = {}
    skill_sals = {}
    for _, row in recommendations.iterrows():
        skills = str(row.get("skills", ""))
        try:
            items = json.loads(skills)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in skills.split(",") if s.strip()]

        for s in items:
            s_low = s.strip().lower()
            if s_low not in seeker_set:
                skill_counts[s_low] = skill_counts.get(s_low, 0) + 1
                if "salary_avg" in row and row["salary_avg"]:
                    if s_low not in skill_sals:
                        skill_sals[s_low] = []
                    skill_sals[s_low].append(row["salary_avg"])

    for skill, cnt in sorted(skill_counts.items(), key=lambda x: -x[1])[:10]:
        avg_sal = np.mean(skill_sals[skill]) if skill in skill_sals else 0
        gap_level = "critical" if cnt >= 3 else "moderate" if cnt >= 2 else "nice-to-have"
        missing_skills.append({
            "skill": skill,
            "demand_count": cnt,
            "avg_salary": round(avg_sal, 0),
            "gap_level": gap_level,
        })

    return missing_skills


def competitor_analysis(
    seeker: JobSeeker, recommendations: pd.DataFrame
) -> Dict:
    """竞品分析：同类求职者的市场竞争状况。

    Returns:
        {
            avg_competitor_salary: 同类岗位平均薪资,
            competition_level: low/medium/high,
            salary_position: seeker salary percentile,
            demand_scale: 可匹配岗位总量估计,
        }
    """
    if recommendations.empty:
        return {"competition_level": "unknown", "demand_scale": 0}

    rec_salaries = recommendations["salary_avg"].dropna()
    if rec_salaries.empty:
        return {"competition_level": "unknown", "demand_scale": len(recommendations)}

    avg_sal = rec_salaries.mean()
    med_sal = rec_salaries.median()

    # 竞争烈度: 匹配岗位越多 → 机会越多(低竞争)
    match_count = len(recommendations)
    if match_count >= 50:
        level = "低"
    elif match_count >= 20:
        level = "中"
    else:
        level = "高"

    # seeker 薪资位置
    if seeker.target_salary and len(rec_salaries) > 0:
        pct = (rec_salaries < seeker.target_salary).sum() / len(rec_salaries) * 100
    else:
        pct = None

    return {
        "avg_competitor_salary": round(avg_sal, 0),
        "median_salary": round(med_sal, 0),
        "competition_level": level,
        "salary_percentile": round(pct, 1) if pct else None,
        "demand_scale": match_count,
    }

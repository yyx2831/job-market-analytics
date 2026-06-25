"""成都+远程 智能岗位推荐引擎。

评分维度（总分 100）：
- 技能匹配度 40%：个人技能集与岗位 skills 字段的交集百分比
- 薪资匹配度 25%：岗位薪资在目标区间 [15K, 25K] 内得分最高，偏离递减
- 成长潜力   20%：基于行业(AI/大数据+3)、公司类型(外企/上市+2)、职位族
- 公司质量   15%：知名企业名单匹配 + 公司规模 + 融资阶段

支持：
- 成都本地 + 远程岗位双通道推荐
- 技能缺口分析
- TOP 30 推荐
"""

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── 知名企业名单 ──
FAMOUS_COMPANIES = {
    "华为", "腾讯", "阿里巴巴", "字节跳动", "百度", "京东", "美团", "网易",
    "小米", "滴滴", "蚂蚁", "拼多多", "哔哩哔哩", "携程", "快手", "小红书",
    "微软", "谷歌", "亚马逊", "苹果", "IBM", "Oracle", "SAP", "Intel",
    "Samsung", "西门子", "博世", "大众", "宝马", "奔驰", "特斯拉",
    "中兴", "海康威视", "大疆", "商汤", "旷视", "科大讯飞",
    "工商银行", "建设银行", "农业银行", "中国银行", "招商银行", "平安",
    "万科", "碧桂园", "恒大", "龙湖",
}

# ── 高成长行业 ──
HIGH_GROWTH_INDUSTRIES = {
    "人工智能", "AI", "机器学习", "深度学习", "大数据", "数据服务",
    "云计算", "区块链", "物联网", "自动驾驶", "机器人",
    "新能源", "半导体", "芯片", "集成电路", "生物医药", "基因",
}

# ── 公司类型加分 ──
COMPANY_TYPE_BONUS = {
    "外商独资": 2, "中外合资": 2, "外企": 2,
    "上市公司": 2, "已上市": 2,
    "股份制企业": 1,
}

# ── 融资阶段加分 ──
FINANCING_BONUS = {
    "D轮及以上": 3, "E轮": 3, "F轮": 3, "Pre-IPO": 3,
    "C轮": 2, "B轮": 1,
    "已上市": 3,
}

# ── 公司规模加分 ──
SIZE_BONUS = {
    "10000人以上": 3, "5000-10000人": 3,
    "1000-5000人": 2, "500-1000人": 1,
    "100-500人": 0, "50-100人": 0, "少于50人": -1,
}

# ── 职位族映射（用于成长潜力评估） ──
JOB_FAMILY_BONUS = {
    "后端开发": 2, "算法工程师": 3, "数据工程师": 3,
    "前端开发": 1, "全栈工程师": 2, "DevOps": 2,
    "产品经理": 1, "测试开发": 1, "架构师": 3,
}


@dataclass
class JobSeekerProfile:
    """求职者画像 — Python 全栈工程师，成都。"""
    skills: List[str] = field(default_factory=lambda: [
        "Python", "Docker", "MySQL", "Redis", "FastAPI",
        "Linux", "Git", "SQL", "Vue", "React",
    ])
    preferred_cities: List[str] = field(default_factory=lambda: ["成都"])
    salary_min: float = 15000
    salary_max: float = 25000
    experience: str = ""
    remote_ok: bool = True
    weights: Dict[str, float] = field(default_factory=lambda: {
        "skills": 0.40,
        "salary": 0.25,
        "growth": 0.20,
        "company": 0.15,
    })


class JobRecommenderV2:
    """多维度加权岗位推荐引擎。"""

    def __init__(self, jobs_df: pd.DataFrame):
        self.jobs = jobs_df.copy()
        self._preprocess()

    def _parse_skills(self, val) -> List[str]:
        """Parse skills field into list."""
        if pd.isna(val):
            return []
        if isinstance(val, list):
            return [str(s).strip() for s in val]
        try:
            items = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(val).split(",") if s.strip()]
        return [str(s).strip() for s in items]

    def _preprocess(self):
        """预计算中间字段。"""
        # Parse skills
        self.jobs["_skills_list"] = self.jobs["skills"].apply(self._parse_skills)

        # Company size as string
        self.jobs["_company_size_str"] = self.jobs["company_size"].fillna("").astype(str)
        self.jobs["_financing_str"] = self.jobs["financing_stage"].fillna("").astype(str)
        self.jobs["_industry_str"] = self.jobs["industry"].fillna("").astype(str)
        self.jobs["_company_name_str"] = self.jobs["company_name"].fillna("").astype(str)

    # ── 维度 1：技能匹配度 (40%) ──
    def _score_skills(self, seeker_skills: List[str]) -> np.ndarray:
        """计算每个岗位与求职者技能集的交集百分比。"""
        seeker_set = set(s.lower() for s in seeker_skills)
        scores = np.zeros(len(self.jobs))

        for i, skills_list in enumerate(self.jobs["_skills_list"]):
            if not skills_list:
                scores[i] = 0.0
                continue
            job_set = set(s.lower() for s in skills_list)
            if not job_set:
                scores[i] = 0.0
                continue
            intersection = len(seeker_set & job_set)
            # 交集占 seeker 技能数的比例
            scores[i] = min(intersection / len(seeker_set), 1.0)

        return scores

    # ── 维度 2：薪资匹配度 (25%) ──
    def _score_salary(self, target_min: float, target_max: float) -> np.ndarray:
        """岗位薪资在 [target_min, target_max] 内得分最高。

        规则：
        - salary_avg 在区间内 → 1.0
        - salary_avg < target_min → 线性衰减到 0（0 元时）
        - salary_avg > target_max → 指数衰减
        - salary_avg 缺失 → 0.3 保底
        """
        n = len(self.jobs)
        scores = np.zeros(n)
        avg_sals = self.jobs["salary_avg"].fillna(0).values

        for i, sal in enumerate(avg_sals):
            if sal == 0:
                scores[i] = 0.2  # 无薪资信息，中性偏低
                continue

            if target_min <= sal <= target_max:
                scores[i] = 1.0
            elif sal < target_min:
                # 低于目标区间，线性衰减
                scores[i] = max(0.0, sal / target_min)
            else:
                # 高于目标区间，指数衰减
                excess = (sal - target_max) / target_max
                scores[i] = max(0.0, math.exp(-excess))

        return scores

    # ── 维度 3：成长潜力 (20%) ──
    def _score_growth(self) -> np.ndarray:
        """基于行业、公司类型、职位族评估成长潜力。

        满分 10 分，归一化到 [0,1]：
        - 行业：AI/大数据/云计算 +3
        - 公司类型：外企/上市 +2
        - 融资阶段：D轮+ +2
        - 职位族：后端/算法/数据 +3
        """
        n = len(self.jobs)
        scores = np.zeros(n)

        for i in range(n):
            row = self.jobs.iloc[i]
            pts = 0.0

            # 行业加分
            industry = row["_industry_str"]
            for hi in HIGH_GROWTH_INDUSTRIES:
                if hi in industry:
                    pts += 3
                    break  # 只加一次行业分

            # 公司类型加分
            company_size = row["_company_size_str"]
            for ctype, bonus in COMPANY_TYPE_BONUS.items():
                if ctype in company_size:
                    pts += bonus
                    break  # 只加一次公司类型分

            # 融资阶段加分
            financing = row["_financing_str"]
            for fstage, bonus in FINANCING_BONUS.items():
                if fstage in financing:
                    pts += bonus
                    break

            # 职位族加分
            title = str(row.get("title", "")).lower()
            for family, bonus in JOB_FAMILY_BONUS.items():
                if family.lower() in title:
                    pts += bonus
                    break

            scores[i] = min(pts / 10.0, 1.0)  # 归一化

        return scores

    # ── 维度 4：公司质量 (15%) ──
    def _score_company(self) -> np.ndarray:
        """基于知名企业名单 + 公司规模 + 融资阶段评分。

        满分 10，归一化。
        """
        n = len(self.jobs)
        scores = np.zeros(n)

        for i in range(n):
            row = self.jobs.iloc[i]
            pts = 0.0

            # 知名企业匹配
            company = row["_company_name_str"]
            for fc in FAMOUS_COMPANIES:
                if fc in company:
                    pts += 5  # 知名企业直接给满分基数
                    break

            # 公司规模
            for size_kw, bonus in SIZE_BONUS.items():
                if size_kw in row["_company_size_str"]:
                    pts += bonus + 2  # +2 基础偏移
                    break
            else:
                pts += 1  # 未知规模给1分

            # 融资阶段
            for fstage, bonus in FINANCING_BONUS.items():
                if fstage in row["_financing_str"]:
                    pts += bonus
                    break

            scores[i] = min(pts / 10.0, 1.0)

        return scores

    # ── 综合推荐 ──
    def recommend(
        self,
        profile: Optional[JobSeekerProfile] = None,
        top_k: int = 30,
    ) -> pd.DataFrame:
        """综合多维评分，返回 TOP K 推荐。

        Args:
            profile: 求职者画像，默认使用 Python 全栈工程师-成都
            top_k: 返回数量

        Returns:
            DataFrame with columns: 原始列 + final_score / skill_score / salary_score / growth_score / company_score / location_type
        """
        if profile is None:
            profile = JobSeekerProfile()

        w = profile.weights

        # 计算各维度得分
        skill_scores = self._score_skills(profile.skills)
        salary_scores = self._score_salary(profile.salary_min, profile.salary_max)
        growth_scores = self._score_growth()
        company_scores = self._score_company()

        # 加权综合
        final_scores = (
            w["skills"] * skill_scores
            + w["salary"] * salary_scores
            + w["growth"] * growth_scores
            + w["company"] * company_scores
        )

        # 构建结果
        result = self.jobs.copy()
        result["skill_score"] = np.round(skill_scores, 4)
        result["salary_score"] = np.round(salary_scores, 4)
        result["growth_score"] = np.round(growth_scores, 4)
        result["company_score"] = np.round(company_scores, 4)
        result["final_score"] = np.round(final_scores, 4)

        # ── 过滤：成都 or 远程 ──
        chengdu_set = {"成都", "chengdu"}
        is_chengdu = result["city"].str.lower().isin(chengdu_set)

        # 识别远程岗位（title 或 city 含"远程"等关键词，或 city 为全国/不限）
        remote_kw = "远程|remote|线上|居家|全国|不限"
        is_remote = (
            result["city"].str.contains(remote_kw, case=False, na=False)
            | result["title"].str.contains(remote_kw, case=False, na=False)
        )

        # 标签
        result["location_type"] = "其他"
        result.loc[is_chengdu & ~is_remote, "location_type"] = "🏙 成都"
        result.loc[is_remote, "location_type"] = "🌐 远程"
        result.loc[is_chengdu & is_remote, "location_type"] = "🏙 成都"

        # 如果只看成都+远程
        if profile.remote_ok:
            mask = is_chengdu | is_remote
        else:
            mask = is_chengdu
        result = result[mask]

        # 排序
        result = result.sort_values("final_score", ascending=False)

        return result.head(top_k)

    def skill_gap_analysis(self, recommendations: pd.DataFrame) -> List[Dict]:
        """技能缺口分析：推荐岗位需要的技能 vs 求职者已有技能。

        Returns:
            [{skill, demand_count, avg_salary, gap_level}]
        """
        seeker_set = set(s.lower() for s in JobSeekerProfile().skills)
        skill_counts: Dict[str, int] = {}
        skill_sals: Dict[str, List[float]] = {}

        for _, row in recommendations.iterrows():
            skills_list = row.get("_skills_list", [])
            for s in skills_list:
                s_low = s.lower()
                if s_low not in seeker_set:
                    skill_counts[s_low] = skill_counts.get(s_low, 0) + 1
                    sal = row.get("salary_avg")
                    if sal and sal > 0:
                        if s_low not in skill_sals:
                            skill_sals[s_low] = []
                        skill_sals[s_low].append(float(sal))

        result = []
        for skill, cnt in sorted(skill_counts.items(), key=lambda x: -x[1])[:15]:
            avg_sal = np.mean(skill_sals[skill]) if skill in skill_sals else 0
            gap_level = (
                "critical" if cnt >= 3
                else "moderate" if cnt >= 2
                else "nice-to-have"
            )
            result.append({
                "skill": skill,
                "demand_count": cnt,
                "avg_salary": round(avg_sal, 0),
                "gap_level": gap_level,
            })
        return result

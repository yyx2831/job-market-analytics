"""FastAPI Pydantic 请求/响应模型定义。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════════════
# Benchmark — 岗位对标
# ═════════════════════════════════════════════════════════════════════

class BenchmarkRequest(BaseModel):
    """岗位对标请求。"""
    title: str = Field(..., description="岗位名称，如 'Python开发'", min_length=1, max_length=100)
    salary: float = Field(..., description="个人月薪 (元/月)", gt=0)
    city: str = Field(..., description="所在城市", min_length=1, max_length=50)

    model_config = {
        "json_schema_extra": {
            "example": {"title": "Python开发", "salary": 15000, "city": "成都"}
        }
    }


class BenchmarkResponse(BaseModel):
    """岗位对标响应。"""
    title: str
    salary: int
    city: str
    peer_count: int
    peer_cities: list[str]
    market_p50: int
    city_p50: int
    percentile: float
    delta_vs_city: float
    delta_pct: float
    assessment: str
    top_skills: list[str]
    similar_roles: list[dict]


# ═════════════════════════════════════════════════════════════════════
# Predict — 薪资预测
# ═════════════════════════════════════════════════════════════════════

class PredictRequest(BaseModel):
    """薪资预测请求。"""
    city: str = Field("成都", description="城市", min_length=1, max_length=50)
    experience: str = Field("3-5年", description="经验级别", min_length=1, max_length=30)
    education: str = Field("本科", description="学历", min_length=1, max_length=20)
    skills: list[str] = Field(default_factory=lambda: ["Python", "Docker", "MySQL"], description="技能列表")
    company_size: str = Field("150-500人", description="公司规模")
    industry: str = Field("计算机软件", description="行业")

    model_config = {
        "json_schema_extra": {
            "example": {
                "city": "成都", "experience": "3-5年", "education": "本科",
                "skills": ["Python", "Docker", "MySQL"],
            }
        }
    }


class FeatureItem(BaseModel):
    """特征重要性条目。"""
    feature: str
    importance: float


class PredictResponse(BaseModel):
    """薪资预测响应。"""
    predicted_salary: int = Field(..., description="预测月薪 (元)")
    confidence_interval: list[int] = Field(..., description="置信区间 [下界, 上界]")
    top_features: list[FeatureItem] = Field(..., description="TOP 特征重要性")
    monthly: str = Field(..., description="可读月薪，如 ¥18.5K/月")


# ═════════════════════════════════════════════════════════════════════
# Search — 岗位搜索
# ═════════════════════════════════════════════════════════════════════

class SearchParams(BaseModel):
    """岗位搜索查询参数。"""
    keyword: Optional[str] = Field(None, description="搜索关键词（模糊匹配 title/company/description/skills）")
    city: Optional[str] = Field(None, description="城市筛选")
    min_salary: Optional[int] = Field(None, description="最低薪资 (元/月)", ge=0)
    limit: int = Field(20, description="返回条数上限", ge=1, le=200)

    model_config = {
        "json_schema_extra": {
            "example": {"keyword": "Python", "city": "成都", "min_salary": 15000, "limit": 20}
        }
    }


class JobItem(BaseModel):
    """岗位条目。"""
    id: int
    title: str
    company: str
    city: str
    salary_avg: Optional[int] = None
    salary_text: str
    experience: str
    education: str
    skills: list[str]
    industry: str
    company_size: str
    publish_time: str


class SearchResponse(BaseModel):
    """岗位搜索响应。"""
    total: int = Field(..., description="符合条件的总数")
    count: int = Field(..., description="本次返回数量")
    jobs: list[JobItem]


# ═════════════════════════════════════════════════════════════════════
# Heatmap — 薪资热力
# ═════════════════════════════════════════════════════════════════════

class HeatmapParams(BaseModel):
    """薪资热力查询参数。"""
    family: str = Field("AI/算法", description="职位族，如 'AI/算法'、'后端开发'、'前端开发' 等")
    min_count: int = Field(5, description="最少样本数阈值", ge=1)


class HeatmapItem(BaseModel):
    """单个城市的热力数据。"""
    city: str
    p25: int
    p50: int
    p75: int
    mean: int
    count: int


class HeatmapResponse(BaseModel):
    """薪资热力响应。"""
    family: str
    cities: int
    data: list[HeatmapItem]


# ═════════════════════════════════════════════════════════════════════
# Chengdu Stats — 成都市场概况
# ═════════════════════════════════════════════════════════════════════

class ChengduSkillItem(BaseModel):
    """成都技能条目。"""
    skill: str
    count: int
    penetration: float = Field(..., description="渗透率 (%)")


class ChengduFamilyItem(BaseModel):
    """成都职位族条目。"""
    family: str
    count: int
    pct: float = Field(..., description="占比 (%)")


class ChengduStatsResponse(BaseModel):
    """成都市场概况响应。"""
    total_jobs: int
    avg_salary: int
    median_salary: int
    p25_salary: int
    p75_salary: int
    top_skills: list[ChengduSkillItem]
    job_families: list[ChengduFamilyItem]
    education_dist: dict[str, int]
    experience_dist: dict[str, int]

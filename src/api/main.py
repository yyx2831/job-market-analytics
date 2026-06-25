"""FastAPI 服务 — 岗位市场分析 REST API 入口。

端点:
  POST /api/benchmark     — 岗位对标
  POST /api/predict        — 薪资预测
  GET  /api/search          — 岗位搜索
  GET  /api/heatmap         — 薪资热力
  GET  /api/stats/chengdu   — 成都市场概况

启动:
  uvicorn src.api.main:app --reload --port 8502
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    BenchmarkRequest,
    BenchmarkResponse,
    PredictRequest,
    PredictResponse,
    SearchParams,
    JobItem,
    SearchResponse,
    HeatmapParams,
    HeatmapItem,
    HeatmapResponse,
    ChengduStatsResponse,
    ChengduSkillItem,
    ChengduFamilyItem,
)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "processed" / "jobs.db")

app = FastAPI(
    title="Job Market Analytics API",
    description="岗位市场分析 REST API — 对标、预测、搜索、热力、统计",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═════════════════════════════════════════════════════════════════════
# POST /api/benchmark — 岗位对标
# ═════════════════════════════════════════════════════════════════════

@app.post("/api/benchmark", response_model=BenchmarkResponse, tags=["对标"])
async def benchmark(req: BenchmarkRequest):
    """将个人岗位条件与市场数据进行对标分析。

    调用 PositionBenchmark.benchmark() 获取完整对标结果，
    包括全国和本城的 P25/P50/P75、百分位定位、TOP 技能、相似岗位等。
    """
    from src.analytics.position_benchmark import PositionBenchmark

    if req.salary <= 0:
        raise HTTPException(status_code=400, detail="薪资必须大于 0")

    try:
        bm = PositionBenchmark(DB_PATH).load()
        result = bm.benchmark(
            title=req.title,
            salary=req.salary,
            city=req.city,
        )
        return BenchmarkResponse(**result.to_dict())

    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="数据库文件未找到，请先运行数据采集")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对标分析失败: {str(e)}")


# ═════════════════════════════════════════════════════════════════════
# POST /api/predict — 薪资预测
# ═════════════════════════════════════════════════════════════════════

@app.post("/api/predict", response_model=PredictResponse, tags=["预测"])
async def predict(req: PredictRequest):
    """基于城市/经验/学历/技能预测薪资。

    加载训练好的 SalaryPredictor 模型进行预测，
    返回预测月薪、置信区间和 TOP 特征重要性。
    """
    from src.analytics.salary_predictor import SalaryPredictor
    import numpy as np

    model_path = str(Path(DB_PATH).parent / "salary_model.pkl")
    if not Path(model_path).exists():
        raise HTTPException(status_code=503, detail="模型文件未找到，请先训练模型")

    try:
        pred = SalaryPredictor.load(model_path)
        result = pred.predict(
            city=req.city,
            experience=req.experience,
            education=req.education,
            skills=req.skills,
            company_size=req.company_size,
            industry=req.industry,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}")

    salary = result.get("prediction", 0)
    if salary is None or salary == 0:
        raise HTTPException(status_code=500, detail="模型返回无效预测值")

    # 置信区间：基于 MAE 的粗略估计 (±MAE)
    mae = pred.metrics.get("rf_mae", 3000)
    ci_low = max(0, int(salary - mae))
    ci_high = int(salary + mae)

    # TOP 特征
    top_features = [
        {"feature": k, "importance": round(v, 4)}
        for k, v in sorted(pred.rf_importance.items(), key=lambda x: -x[1])[:10]
    ]

    return PredictResponse(
        predicted_salary=salary,
        confidence_interval=[ci_low, ci_high],
        top_features=top_features,
        monthly=f"¥{salary / 1000:.1f}K/月",
    )


# ═════════════════════════════════════════════════════════════════════
# GET /api/search — 岗位搜索
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/search", response_model=SearchResponse, tags=["搜索"])
async def search_jobs(params: SearchParams = Depends()):
    """全文搜索 + 多维筛选岗位。

    支持 keyword 模糊搜索（title/company/description/skills）、
    city、min_salary 筛选，结果按 publish_time 降序排列。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 构建查询
    clauses = ["1=1"]
    sql_params: list = []

    if params.keyword:
        kw = f"%{params.keyword}%"
        clauses.append(
            "(title LIKE ? OR company_name LIKE ? OR description LIKE ? OR skills LIKE ?)"
        )
        sql_params.extend([kw, kw, kw, kw])

    if params.city:
        clauses.append("city = ?")
        sql_params.append(params.city)

    if params.min_salary and params.min_salary > 0:
        clauses.append("salary_avg >= ?")
        sql_params.append(params.min_salary)

    where = " AND ".join(clauses)
    limit = min(params.limit, 200)

    sql = f"""
        SELECT id, title, company_name as company, city, salary_avg,
               salary_text, experience, education, skills, industry,
               company_size, publish_time, crawl_time
        FROM jobs
        WHERE {where}
        ORDER BY publish_time DESC
        LIMIT ?
    """
    sql_params.append(limit)

    try:
        cur = conn.execute(sql, sql_params)
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
    finally:
        pass

    # Count total (without LIMIT)
    count_sql = f"SELECT COUNT(*) as cnt FROM jobs WHERE {where}"
    try:
        total = conn.execute(count_sql, sql_params[:-1]).fetchone()["cnt"]
    except Exception:
        total = len(rows)

    conn.close()

    jobs = [
        JobItem(
            id=r["id"],
            title=r["title"],
            company=r["company"],
            city=r["city"] or "",
            salary_avg=r["salary_avg"],
            salary_text=r["salary_text"] or "",
            experience=r["experience"] or "",
            education=r["education"] or "",
            skills=[s.strip() for s in (r["skills"] or "").split(",") if s.strip()],
            industry=r["industry"] or "",
            company_size=r["company_size"] or "",
            publish_time=r["publish_time"] or "",
        )
        for r in rows
    ]

    return SearchResponse(total=total, count=len(jobs), jobs=jobs)


# ═════════════════════════════════════════════════════════════════════
# GET /api/heatmap — 薪资热力
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/heatmap", response_model=HeatmapResponse, tags=["热力"])
async def heatmap(params: HeatmapParams = Depends()):
    """获取指定职位族的跨城市薪资热力数据。

    返回各城市的 P25/P50/P75/均值 和样本数量，
    按 P50 降序排列。
    """
    from src.analytics.position_benchmark import PositionBenchmark

    try:
        bm = PositionBenchmark(DB_PATH).load()
        data = bm.city_heatmap(
            title_family=params.family,
            min_count=params.min_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"热力分析失败: {str(e)}")

    items = [
        HeatmapItem(
            city=city,
            p25=d["p25"],
            p50=d["p50"],
            p75=d["p75"],
            mean=d["mean"],
            count=d["count"],
        )
        for city, d in sorted(data.items(), key=lambda x: -x[1]["p50"])
    ]

    return HeatmapResponse(family=params.family, cities=len(items), data=items)


# ═════════════════════════════════════════════════════════════════════
# GET /api/stats/chengdu — 成都市场概况
# ═════════════════════════════════════════════════════════════════════

@app.get("/api/stats/chengdu", response_model=ChengduStatsResponse, tags=["统计"])
async def chengdu_stats():
    """返回成都市场的核心统计指标。

    包含：总岗位数、均薪、中位薪资、热门技能 TOP 10、
    职位族分布、学历/经验分布等。
    """
    import numpy as np
    from collections import Counter
    from src.analytics.position_benchmark import normalize_title

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cur = conn.execute("""
        SELECT * FROM jobs
        WHERE city = '成都'
          AND salary_avg > 0
          AND salary_avg < 100000
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="成都暂无岗位数据")

    total = len(rows)
    salaries = np.array([r["salary_avg"] for r in rows if r["salary_avg"]])

    # 技能统计
    skill_counter: Counter = Counter()
    for r in rows:
        skills_str = r["skills"] or ""
        for s in skills_str.split(","):
            s = s.strip()
            if s:
                skill_counter[s] += 1

    top_skills = sorted(skill_counter.items(), key=lambda x: -x[1])[:10]

    # 职位族分布
    family_counter: Counter = Counter()
    for r in rows:
        _, _, fam = normalize_title(r["title"] or "")
        family_counter[fam] += 1

    # 学历分布
    edu_counter: Counter = Counter()
    for r in rows:
        edu_counter[r["education"] or "未知"] += 1

    # 经验分布
    exp_counter: Counter = Counter()
    for r in rows:
        exp_counter[r["experience"] or "未知"] += 1

    return ChengduStatsResponse(
        total_jobs=total,
        avg_salary=int(np.mean(salaries)) if len(salaries) > 0 else 0,
        median_salary=int(np.median(salaries)) if len(salaries) > 0 else 0,
        p25_salary=int(np.percentile(salaries, 25)) if len(salaries) > 0 else 0,
        p75_salary=int(np.percentile(salaries, 75)) if len(salaries) > 0 else 0,
        top_skills=[
            ChengduSkillItem(skill=sk, count=c, penetration=round(c / total * 100, 1))
            for sk, c in top_skills
        ],
        job_families=[
            ChengduFamilyItem(family=f, count=c, pct=round(c / total * 100, 1))
            for f, c in sorted(family_counter.items(), key=lambda x: -x[1])
        ],
        education_dist={k: v for k, v in sorted(edu_counter.items(), key=lambda x: -x[1])},
        experience_dist={k: v for k, v in sorted(exp_counter.items(), key=lambda x: -x[1])},
    )


# ── 健康检查 ───────────────────────────────────────────────────────

@app.get("/api/health", tags=["系统"])
async def health():
    """服务健康检查。"""
    db_exists = Path(DB_PATH).exists()
    return {
        "status": "ok" if db_exists else "degraded",
        "database": "connected" if db_exists else "missing",
        "version": "1.0.0",
    }

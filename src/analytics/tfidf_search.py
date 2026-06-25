"""TF-IDF 岗位搜索 — sentence-transformers 不可用时的备选方案。

使用 sklearn TfidfVectorizer 对 skills 字段做向量化，
支持自然语言查询的 cosine 相似度搜索。

用法:
  python3 -m src.analytics.tfidf_search --query "Python 后端 Docker" --top 10
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DB_PATH = Path(__file__).parent.parent.parent / "data" / "processed" / "jobs.db"

_VECTORIZER: TfidfVectorizer | None = None
_TFIDF_MATRIX = None
_JOBS_DF: pd.DataFrame | None = None


def _skills_to_text(val) -> str:
    """Convert skills field to a whitespace-separated string."""
    if pd.isna(val):
        return ""
    if isinstance(val, list):
        items = [str(s).strip() for s in val]
    else:
        try:
            items = json.loads(str(val))
        except (json.JSONDecodeError, TypeError):
            items = [s.strip() for s in str(val).split(",") if s.strip()]
    return " ".join(str(s).strip() for s in items)


def _preprocess_query(query: str) -> str:
    """Preprocess natural language query to match skills format.

    Removes common Chinese stopwords and keeps skill-like tokens.
    """
    # Remove common query words
    stopwords = ["招", "招聘", "招聘岗位", "岗位", "职位", "需求", "要求", "需要",
                 "的", "了", "和", "与", "及", "等", "有", "在", "是"]
    result = query
    for sw in stopwords:
        result = result.replace(sw, " ")
    # Replace punctuation
    result = result.replace("、", " ").replace("，", " ").replace("。", " ")
    return result.strip()


def _build_index(db_path: Path = DB_PATH, force: bool = False):
    """Build TF-IDF index from job skills."""
    global _VECTORIZER, _TFIDF_MATRIX, _JOBS_DF

    if _TFIDF_MATRIX is not None and not force:
        return

    conn = sqlite3.connect(db_path)
    _JOBS_DF = pd.read_sql(
        """SELECT id, title, company_name, city, skills, salary_avg, salary_min, salary_max,
                  experience, industry FROM jobs WHERE skills IS NOT NULL AND skills != ''""",
        conn,
    )
    conn.close()

    _JOBS_DF["_skills_text"] = _JOBS_DF["skills"].apply(_skills_to_text)

    print(f"📊 加载 {len(_JOBS_DF)} 个岗位", file=sys.stderr)

    _VECTORIZER = TfidfVectorizer(
        token_pattern=r"(?u)\b\S+\b",
        max_features=500,
        sublinear_tf=True,
        ngram_range=(1, 2),
    )
    _TFIDF_MATRIX = _VECTORIZER.fit_transform(_JOBS_DF["_skills_text"])
    print(f"✅ TF-IDF 矩阵维度: {_TFIDF_MATRIX.shape}", file=sys.stderr)


def search(query: str, top_k: int = 20, db_path: Path = DB_PATH) -> pd.DataFrame:
    """TF-IDF 搜索。

    Args:
        query: 自然语言查询
        top_k: 返回数量
        db_path: 数据库路径

    Returns:
        DataFrame with similarity scores
    """
    _build_index(db_path)
    assert _VECTORIZER is not None
    assert _TFIDF_MATRIX is not None
    assert _JOBS_DF is not None

    processed = _preprocess_query(query)
    query_vec = _VECTORIZER.transform([processed])
    sims = cosine_similarity(query_vec, _TFIDF_MATRIX)[0]

    result = _JOBS_DF.copy()
    result["similarity"] = np.round(sims, 4)
    result = result.sort_values("similarity", ascending=False)

    top = result.head(top_k)
    display = top[["id", "title", "company_name", "city", "salary_avg", "skills", "similarity"]].copy()
    display["salary_avg"] = display["salary_avg"].fillna(0).astype(int)
    return display


def similar_jobs(job_id: int, top_k: int = 10, db_path: Path = DB_PATH) -> pd.DataFrame:
    """查找与指定岗位最相似的岗位。"""
    _build_index(db_path)
    assert _TFIDF_MATRIX is not None
    assert _JOBS_DF is not None

    matches = _JOBS_DF[_JOBS_DF["id"] == job_id]
    if matches.empty:
        raise ValueError(f"岗位 ID {job_id} 不存在")

    idx = matches.index[0]
    anchor_vec = _TFIDF_MATRIX[idx]
    sims = cosine_similarity(anchor_vec, _TFIDF_MATRIX)[0]

    result = _JOBS_DF.copy()
    result["similarity"] = np.round(sims, 4)
    result = result.drop(idx)
    result = result.sort_values("similarity", ascending=False)

    top = result.head(top_k)
    display = top[["id", "title", "company_name", "city", "salary_avg", "skills", "similarity"]].copy()
    display["salary_avg"] = display["salary_avg"].fillna(0).astype(int)
    return display


def main():
    parser = argparse.ArgumentParser(description="TF-IDF 岗位搜索（备选方案）")
    parser.add_argument("--query", "-q", help="搜索查询")
    parser.add_argument("--top", type=int, default=10, help="返回数量")
    parser.add_argument("--similar", "-s", type=int, help="基于岗位 ID 找相似")
    parser.add_argument("--db", default=str(DB_PATH), help="数据库路径")
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.similar:
        print(f"🔍 查找与岗位 #{args.similar} 相似的其他岗位...")
        results = similar_jobs(args.similar, top_k=args.top, db_path=db_path)
        print(f"\n{'='*80}")
        print(f"  相似岗位 TOP {len(results)}")
        print(f"{'='*80}")
        for _, row in results.iterrows():
            skills_preview = str(row["skills"])[:40]
            print(
                f"  {row['similarity']:.4f} | #{row['id']} | {row['title'][:30]:30s} | "
                f"{row['city']:6s} | ¥{row['salary_avg']:,} | {skills_preview}"
            )
        return

    if args.query:
        print(f'🔍 搜索: "{args.query}"')
        results = search(args.query, top_k=args.top, db_path=db_path)
        print(f"\n{'='*80}")
        print(f"  搜索结果 TOP {len(results)}")
        print(f"{'='*80}")
        for _, row in results.iterrows():
            skills_preview = str(row["skills"])[:40]
            print(
                f"  {row['similarity']:.4f} | #{row['id']} | {row['title'][:30]:30s} | "
                f"{row['city']:6s} | ¥{row['salary_avg']:,} | {skills_preview}"
            )
        return

    parser.print_help()


if __name__ == "__main__":
    main()

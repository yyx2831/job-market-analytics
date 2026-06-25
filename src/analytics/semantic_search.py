"""语义搜索 - 基于 sentence-transformers 的岗位技能语义搜索。

使用模型: paraphrase-multilingual-MiniLM-L12-v2
功能:
  - search(query, top_k): 自然语言查询 → embedding → cosine 相似度排序
  - similar_jobs(job_id, top_k): 基于技能 embedding 找最相似岗位
  - 自动构建/缓存 embedding 矩阵

CLI 用法:
  python3 -m src.analytics.semantic_search --query "招Python后端,懂Docker和Kubernetes" --top 10
  python3 -m src.analytics.semantic_search --build  # 预构建 embedding 缓存
"""

from __future__ import annotations

import argparse
import json
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).parent.parent.parent / "data" / "processed" / "jobs.db"
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_FILE = CACHE_DIR / "skill_embeddings.pkl"

_MODEL = None
_EMBEDDINGS = None
_JOBS_DF = None


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    try:
        from sentence_transformers import SentenceTransformer
        model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        print(f"📥 加载模型: {model_name} ...", file=sys.stderr)
        _MODEL = SentenceTransformer(model_name)
        print("✅ 模型加载完成", file=sys.stderr)
        return _MODEL
    except ImportError:
        print("⚠️  sentence-transformers 未安装,使用 TF-IDF fallback", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  模型加载失败: {e},使用 TF-IDF fallback", file=sys.stderr)
        return None


def _load_jobs() -> pd.DataFrame:
    """Load jobs from SQLite database."""
    global _JOBS_DF
    if _JOBS_DF is not None:
        return _JOBS_DF

    conn = sqlite3.connect(DB_PATH)
    # Load key columns
    _JOBS_DF = pd.read_sql(
        "SELECT id, title, company_name, city, skills, salary_avg, salary_min, salary_max, experience, industry FROM jobs WHERE skills IS NOT NULL AND skills != ''",
        conn,
    )
    conn.close()

    # Ensure skills are parsed
    _JOBS_DF["_skills_text"] = _JOBS_DF["skills"].apply(_skills_to_text)
    print(f"📊 加载 {len(_JOBS_DF)} 个岗位", file=sys.stderr)
    return _JOBS_DF


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
    # Add spaces for multi-word skills
    return " ".join(str(s).strip().replace(" ", "_") for s in items)


def _build_embeddings(force: bool = False) -> np.ndarray:
    """Build or load cached skill embeddings for all jobs.

    Returns (n_jobs, embedding_dim) numpy array.
    """
    global _EMBEDDINGS

    if _EMBEDDINGS is not None:
        return _EMBEDDINGS

    # Try loading from cache
    if not force and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                cached = pickle.load(f)
                if len(cached) == len(_load_jobs()):
                    print("📦 从缓存加载 embedding", file=sys.stderr)
                    _EMBEDDINGS = cached
                    return _EMBEDDINGS
                else:
                    print("⚠️  缓存大小不匹配,重新构建", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  缓存加载失败: {e}", file=sys.stderr)

    model = _get_model()
    jobs = _load_jobs()
    texts = jobs["_skills_text"].tolist()

    if model is not None:
        print(f"🔨 构建 {len(texts)} 个岗位的语义向量...", file=sys.stderr)
        _EMBEDDINGS = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        print(f"✅ 矩阵维度: {_EMBEDDINGS.shape}", file=sys.stderr)

        # Cache
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(_EMBEDDINGS, f)
    else:
        # TF-IDF fallback
        from sklearn.feature_extraction.text import TfidfVectorizer
        print("🔨 使用 TF-IDF 构建文本向量...", file=sys.stderr)
        vectorizer = TfidfVectorizer(
            token_pattern=r"(?u)\b\S+\b",
            max_features=500,
            sublinear_tf=True,
        )
        _EMBEDDINGS = vectorizer.fit_transform(texts).toarray()
        # Store vectorizer for later query transforms
        global _VECTORIZER
        _VECTORIZER = vectorizer
        print(f"✅ TF-IDF 矩阵维度: {_EMBEDDINGS.shape}", file=sys.stderr)

    return _EMBEDDINGS


_VECTORIZER = None


def _encode_query(query: str) -> np.ndarray:
    """Encode a natural language query into the same embedding space."""
    model = _get_model()

    if model is not None:
        vec = model.encode([query], convert_to_numpy=True)
    else:
        from sklearn.feature_extraction.text import TfidfVectorizer
        global _VECTORIZER
        if _VECTORIZER is None:
            raise RuntimeError("请先调用 _build_embeddings() 初始化 TF-IDF")

        # Clean query: remove Chinese stop words, keep skill-like tokens
        import re
        stopwords = ["招", "招聘", "岗位", "职位", "需求", "要求", "需要",
                     "的", "了", "和", "与", "及", "等", "有", "在", "是",
                     "懂", "会", "熟悉", "掌握", "了解", "具备"]
        clean = query
        for sw in stopwords:
            clean = clean.replace(sw, " ")
        clean = re.sub(r'[，。、！？：；（）""\'\']', ' ', clean)
        clean = clean.replace(",", " ")
        vec = _VECTORIZER.transform([clean.strip()]).toarray()

    return vec


def search(query: str, top_k: int = 20) -> pd.DataFrame:
    """语义搜索:将自然语言查询转为 embedding,按 cosine 相似度排序。

    Args:
        query: 自然语言查询,如 "招Python后端,懂Docker和Kubernetes"
        top_k: 返回数量

    Returns:
        DataFrame with columns: id, title, company_name, city, skills, salary_avg, similarity
    """
    embeddings = _build_embeddings()
    jobs = _load_jobs()

    # Encode query
    query_vec = _encode_query(query)

    # Cosine similarity
    from sklearn.metrics.pairwise import cosine_similarity
    sims = cosine_similarity(query_vec, embeddings)[0]

    # Build results
    result = jobs.copy()
    result["similarity"] = np.round(sims, 4)

    # Sort descending
    result = result.sort_values("similarity", ascending=False)

    # Show top
    top = result.head(top_k)

    # Display columns
    display = top[["id", "title", "company_name", "city", "salary_avg", "skills", "similarity"]].copy()
    display["salary_avg"] = display["salary_avg"].fillna(0).astype(int)
    return display


def similar_jobs(job_id: int, top_k: int = 10) -> pd.DataFrame:
    """基于技能 embedding,找与指定岗位最相似的岗位。

    Args:
        job_id: 目标岗位 ID
        top_k: 返回数量 (不含自身)

    Returns:
        DataFrame with similarity scores
    """
    embeddings = _build_embeddings()
    jobs = _load_jobs()

    # Find job index
    matches = jobs[jobs["id"] == job_id]
    if matches.empty:
        raise ValueError(f"岗位 ID {job_id} 不存在")

    idx = matches.index[0]
    anchor_vec = embeddings[idx].reshape(1, -1)

    # Cosine similarity
    from sklearn.metrics.pairwise import cosine_similarity
    sims = cosine_similarity(anchor_vec, embeddings)[0]

    result = jobs.copy()
    result["similarity"] = np.round(sims, 4)

    # Exclude self
    result = result.drop(idx)
    result = result.sort_values("similarity", ascending=False)

    top = result.head(top_k)
    display = top[["id", "title", "company_name", "city", "salary_avg", "skills", "similarity"]].copy()
    display["salary_avg"] = display["salary_avg"].fillna(0).astype(int)
    return display


def main():
    parser = argparse.ArgumentParser(description="语义搜索 - 岗位技能语义匹配")
    parser.add_argument("--query", "-q", help="自然语言查询")
    parser.add_argument("--top", type=int, default=10, help="返回数量 (默认 10)")
    parser.add_argument("--similar", "-s", type=int, help="基于岗位 ID 找相似岗位")
    parser.add_argument("--build", action="store_true", help="预构建 embedding 缓存")
    parser.add_argument("--db", default=str(DB_PATH), help="数据库路径")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    if args.build:
        print("🔨 预构建 embedding 缓存...")
        embeddings = _build_embeddings(force=True)
        print(f"✅ 完成,矩阵维度: {embeddings.shape}")
        return

    if args.similar:
        print(f"🔍 查找与岗位 #{args.similar} 相似的其他岗位...")
        results = similar_jobs(args.similar, top_k=args.top)

        print(f"\n{'='*80}")
        print(f"  相似岗位 TOP {len(results)}")
        print(f"{'='*80}")
        for _, row in results.iterrows():
            skills_preview = str(row["skills"])[:40]
            print(
                f"  {row['similarity']:.4f} | #{row['id']} | {row['title'][:25]:25s} | "
                f"{row['city']:6s} | ¥{row['salary_avg']:,} | {skills_preview}"
            )
        return

    if args.query:
        print(f'🔍 语义搜索: "{args.query}"')
        results = search(args.query, top_k=args.top)

        print(f"\n{'='*80}")
        print(f"  搜索结果 TOP {len(results)}")
        print(f"{'='*80}")
        for _, row in results.iterrows():
            skills_preview = str(row["skills"])[:40]
            print(
                f"  {row['similarity']:.4f} | #{row['id']} | {row['title'][:25]:25s} | "
                f"{row['city']:6s} | ¥{row['salary_avg']:,} | {skills_preview}"
            )
        return

    parser.print_help()


if __name__ == "__main__":
    main()

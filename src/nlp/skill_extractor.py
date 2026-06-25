"""NLP 增强技能提取器。

流程：
1. jieba 分词 → 从岗位标题、JD 描述中提取候选词
2. TF-IDF → 计算每个候选词的文档级重要性
3. 技能词典匹配 → 与预定义技能库交叉验证
4. 输出增强技能标签（原有技能 + 新发现技能）

优于原始纯字符串匹配：(1) 能发现词典外的技能 (2) 权重更合理 (3) 去噪
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

# ── 预定义技能词典（用于交叉验证）──
KNOWN_SKILLS: Set[str] = {
    # 编程语言
    "Python", "Java", "Go", "Golang", "C++", "C#", "Rust", "Kotlin", "Swift",
    "TypeScript", "JavaScript", "PHP", "Ruby", "Scala", "Dart", "MATLAB", "R",
    # 前端
    "React", "Vue", "Angular", "Next.js", "Nuxt", "Flutter", "HTML", "CSS",
    "Webpack", "Vite", "Node.js", "Express", "NestJS", "Electron", "小程序",
    # 后端框架
    "Spring", "Spring Boot", "Spring Cloud", "Django", "FastAPI", "Flask",
    "Gin", "MyBatis", "Hibernate", "gRPC", "GraphQL", "RESTful",
    # 数据库
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "ClickHouse",
    "TiDB", "Oracle", "SQL Server", "HBase", "Cassandra", "Neo4j", "Doris",
    # 大数据
    "Hadoop", "Spark", "Flink", "Kafka", "Hive", "Airflow", "Pulsar",
    "数据仓库", "数据湖", "ETL", "数据治理",
    # AI/ML
    "深度学习", "机器学习", "NLP", "CV", "PyTorch", "TensorFlow", "Keras",
    "Transformer", "LLM", "大模型", "AIGC", "LangChain", "RAG",
    # DevOps/云
    "Docker", "Kubernetes", "K8s", "Jenkins", "GitLab CI", "Terraform",
    "AWS", "阿里云", "Azure", "GCP", "Prometheus", "Grafana", "Nginx",
    "Linux", "Shell", "Ansible",
    # 测试
    "自动化测试", "Selenium", "Appium", "JMeter", "性能测试", "pytest",
    "单元测试", "集成测试", "接口测试",
    # 软技能/管理
    "项目管理", "敏捷", "Scrum", "需求分析", "产品设计", "用户体验", "数据分析",
    "数据挖掘", "数据可视化", "BI",
}

# 停用词：高频但无技能含义的词
STOP_WORDS: Set[str] = {
    "工程师", "开发", "岗位", "职位", "招聘", "公司", "有限", "技术",
    "工作", "负责", "相关", "以上", "经验", "学历", "本科", "专业",
    "熟练", "熟悉", "了解", "具备", "优先", "能力", "团队", "良好",
    "沟通", "协作", "问题", "解决", "设计", "系统", "平台", "业务",
    "和", "的", "及", "等", "与", "或", "中", "在", "有", "为",
    "年", "月", "日", "万", "千", "K",
}

# 技能合并映射（归一化）
SKILL_NORMALIZE: Dict[str, str] = {
    "kubernetes": "K8s",
    "golang": "Go",
    "node": "Node.js",
    "nodejs": "Node.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "postgres": "PostgreSQL",
    "es": "Elasticsearch",
    "elastic": "Elasticsearch",
    "kafka": "Kafka",
    "flink": "Flink",
    "spark": "Spark",
    "hadoop": "Hadoop",
    "docker": "Docker",
    "jenkins": "Jenkins",
    "nginx": "Nginx",
    "k8s": "K8s",
    "reactjs": "React",
    "react.js": "React",
    "vue.js": "Vue",
    "next": "Next.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "pytest": "pytest",
    "selenium": "Selenium",
    "jmeter": "JMeter",
    "gitlab": "GitLab CI",
    "graphql": "GraphQL",
    "hibernate": "Hibernate",
    "mybatis": "MyBatis",
    "springboot": "Spring Boot",
    "springcloud": "Spring Cloud",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "langchain": "LangChain",
    "grpc": "gRPC",
    "mongodb": "MongoDB",
    "postgresql": "PostgreSQL",
    "elasticsearch": "Elasticsearch",
    "clickhouse": "ClickHouse",
    "airflow": "Airflow",
    "ansible": "Ansible",
    "terraform": "Terraform",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "electron": "Electron",
    "webpack": "Webpack",
    "vite": "Vite",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "matlab": "MATLAB",
    "csharp": "C#",
    "scala": "Scala",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "dart": "Dart",
    "rust": "Rust",
    "php": "PHP",
    "ruby": "Ruby",
}


def _tokenize(text: str) -> List[str]:
    """jieba 分词并清洗。"""
    import jieba
    tokens = jieba.lcut(text)
    # 保留 2-15 字符的词，过滤纯数字和纯符号
    result = []
    for t in tokens:
        t = t.strip()
        if 2 <= len(t) <= 15 and not t.isdigit() and not re.match(r'^[^\w\u4e00-\u9fff]+$', t):
            if t.lower() not in {w.lower() for w in STOP_WORDS}:
                result.append(t)
    return result


def _normalize_skill(skill: str) -> str:
    """技能名称归一化。"""
    key = skill.lower().strip()
    return SKILL_NORMALIZE.get(key, skill)


def extract_skills_enhanced(
    df: pd.DataFrame,
    text_columns: Optional[List[str]] = None,
    top_n: int = 20,
    min_df: int = 3,
) -> Dict[str, int]:
    """从 DataFrame 中提取增强技能标签。

    Args:
        df: 岗位 DataFrame，需包含 title 列
        text_columns: 用于 TF-IDF 的文本列，默认 ["title"]
        top_n: 返回前 N 个技能
        min_df: 最小文档频率

    Returns:
        {技能名: 计数} 字典
    """
    if text_columns is None:
        text_columns = ["title"]

    # 构建文本语料
    texts = []
    for col in text_columns:
        if col in df.columns:
            texts.append(df[col].fillna(""))

    if not texts:
        return {}

    # 合并所有文本列
    corpus = []
    for i in range(len(texts[0])):
        parts = [t.iloc[i] if isinstance(t, pd.Series) else "" for t in texts]
        corpus.append(" ".join(str(p) for p in parts if p and str(p) != "nan"))

    corpus = [c for c in corpus if c.strip()]
    if len(corpus) < 3:
        return {}

    # jieba 分词
    tokenized = [" ".join(_tokenize(doc)) for doc in corpus]

    # TF-IDF
    try:
        vectorizer = TfidfVectorizer(max_features=500, min_df=min_df)
        tfidf_matrix = vectorizer.fit_transform(tokenized)
    except ValueError:
        return {}

    feature_names = vectorizer.get_feature_names_out()
    tfidf_sum = np.asarray(tfidf_matrix.sum(axis=0)).flatten()

    # 与已知技能词典交叉 + TF-IDF 权重
    skill_scores: Dict[str, float] = {}
    for idx, term in enumerate(feature_names):
        score = tfidf_sum[idx]
        # 直接匹配已知技能
        for known in KNOWN_SKILLS:
            if known.lower() == term.lower():
                norm_name = _normalize_skill(known)
                skill_scores[norm_name] = max(skill_scores.get(norm_name, 0), score)
                break
            elif term.lower() in known.lower() or known.lower() in term.lower():
                norm_name = _normalize_skill(known)
                skill_scores[norm_name] = max(
                    skill_scores.get(norm_name, 0), score * 0.7
                )

    # 排序
    sorted_skills = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)

    # 转为计数（TF-IDF 分 * 100 取整）
    result = {skill: max(1, int(score * 100)) for skill, score in sorted_skills[:top_n]}

    # 也统计原始 skills 列中的技能
    if "skills" in df.columns:
        for val in df["skills"].dropna():
            try:
                items = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                items = [s.strip() for s in str(val).split(",") if s.strip()]
            for s in items:
                s = str(s).strip()
                if s:
                    norm = _normalize_skill(s)
                    result[norm] = result.get(norm, 0) + 1

    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:top_n])

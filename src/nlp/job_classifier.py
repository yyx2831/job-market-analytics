"""岗位自动分类器。

基于关键词规则 + TF-IDF 相似度，将岗位自动分为 7 大类：
后端 / 前端 / 算法AI / 数据分析 / 运维DevOps / 测试 / 产品管理
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional

import pandas as pd

# ── 分类定义：每类一组关键词 ──
CATEGORY_RULES: Dict[str, Dict[str, List[str]]] = {
    "算法/AI": {
        "high": [
            "算法工程师", "AI", "人工智能", "深度学习", "机器学习",
            "NLP", "CV", "视觉算法", "推荐算法", "大模型", "LLM",
            "AIGC", "自然语言", "图像", "语音", "感知", "自动驾驶",
            "数据科学家", "强化学习", "模型训练", "推理", "RAG",
            "PyTorch", "TensorFlow", "Transformer", "神经网络",
        ],
        "medium": [
            "算法", "模型", "训练", "智能", "预测", "识别",
            "生成", "分类", "检测", "跟踪",
        ],
    },
    "后端开发": {
        "high": [
            "Java开发", "Python开发", "Go开发", "后端开发", "服务端",
            "PHP开发", "C++开发", "Golang", "Rust开发",
            "Spring", "Django", "FastAPI", "微服务", "API",
            "数据库", "MySQL", "Redis", "PostgreSQL", "Kafka",
            "RPC", "gRPC", "分布式", "高并发",
            # 独立语言名（防止 "Java高级工程师" 漏判）
            " Java ", " Python ", " Go ", "PHP", "C++", "C#",
        ],
        "medium": [
            "后端", "服务器", "后台", "接口", "中间件",
            "Service", "存储", "缓存", "消息队列", "Java", "Python",
        ],
    },
    "前端开发": {
        "high": [
            "前端", "Web前端", "H5", "React", "Vue", "Angular",
            "HTML", "CSS", "JavaScript", "TypeScript", "小程序开发",
            "Flutter", "移动端", "iOS", "Android", "App开发",
            "微信小程序", "前端架构", "Node.js",
        ],
        "medium": [
            "前端", "页面", "UI开发", "客户端", "跨平台",
            "Web", "浏览器", "DOM", "渲染",
        ],
    },
    "数据分析": {
        "high": [
            "数据分析", "数据挖掘", "BI", "商业分析", "数据运营",
            "数据仓库", "数据治理", "ETL", "数仓", "报表", "指标体系",
            "AB测试", "增长分析", "用户研究",
        ],
        "medium": [
            "数据", "分析", "统计", "可视化", "报表",
            "Excel", "Tableau", "PowerBI", "SQL",
        ],
    },
    "运维/DevOps": {
        "high": [
            "运维", "SRE", "DevOps", "Docker", "Kubernetes", "K8s",
            "Jenkins", "CI/CD", "监控", "告警", "部署", "发布",
            "Linux", "Nginx", "安全", "网络", "云平台",
            "AWS", "阿里云", "Azure", "Terraform", "Ansible",
        ],
        "medium": [
            "运维", "部署", "监控", "容器", "集群", "日志",
            "防火墙", "VPN", "负载均衡", "CDN",
        ],
    },
    "测试": {
        "high": [
            "测试工程师", "QA", "自动化测试", "性能测试", "测试开发",
            "Selenium", "Appium", "JMeter", "pytest", "接口测试",
            "单元测试", "集成测试", "黑盒", "白盒",
        ],
        "medium": [
            "测试", "质量", "Bug", "用例", "验收", "回归",
        ],
    },
    "产品/管理": {
        "high": [
            "产品经理", "产品总监", "项目经理", "产品设计", "产品运营",
            "Scrum Master", "敏捷教练", "技术管理", "Team Leader",
            "技术总监", "CTO", "架构师", "解决方案",
        ],
        "medium": [
            "产品", "管理", "需求分析", "原型", "PRD",
            "项目管理", "敏捷", "迭代", "OKR", "协调",
        ],
    },
}


def classify_job(title: str, skills_text: Optional[str] = None) -> Tuple[str, float]:
    """对单个岗位进行分类。

    Args:
        title: 岗位标题
        skills_text: 技能标签文本（可选，用于增强匹配）

    Returns:
        (类别名, 置信度 0-1)
    """
    if not title or pd.isna(title):
        return "其他", 0.0

    text = f"{title} {skills_text or ''}".lower()

    best_category = "其他"
    best_score = 0.0

    for cat, rules in CATEGORY_RULES.items():
        score = 0.0
        # high 关键词权重 3
        for kw in rules["high"]:
            if kw.lower() in text:
                score += 3.0
        # medium 关键词权重 1
        for kw in rules["medium"]:
            if kw.lower() in text:
                score += 1.0

        if score > best_score:
            best_score = score
            best_category = cat

    # 归一化置信度（最高分 ~15-20）
    confidence = min(best_score / 15.0, 1.0)

    return best_category, confidence


def classify_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """对 DataFrame 中所有岗位进行分类，添加 category 和 category_confidence 列。

    Args:
        df: 岗位 DataFrame，需包含 title 列

    Returns:
        添加了 category 和 category_confidence 列的 DataFrame
    """
    result = df.copy()
    categories = []
    confidences = []

    for _, row in result.iterrows():
        title = row.get("title", "")
        skills = row.get("skills", "") if "skills" in result.columns else None
        cat, conf = classify_job(str(title), str(skills) if skills else None)
        categories.append(cat)
        confidences.append(round(conf, 2))

    result["category"] = categories
    result["category_confidence"] = confidences
    return result


def category_stats(df: pd.DataFrame) -> pd.DataFrame:
    """按类别统计岗位数、均薪、中位薪资。

    如果 df 尚未分类，先行分类。
    """
    if "category" not in df.columns:
        df = classify_dataframe(df)

    stats = df.groupby("category").agg(
        岗位数=("id", "count"),
        平均薪资=("salary_avg", "mean"),
        薪资中位=("salary_avg", "median"),
    ).reset_index()

    stats["平均薪资"] = stats["平均薪资"].round(1)
    stats["薪资中位"] = stats["薪资中位"].round(1)
    return stats.sort_values("岗位数", ascending=False)

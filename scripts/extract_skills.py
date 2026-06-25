#!/usr/bin/env python3
"""逐岗位技能提取脚本 — 对 title + description 做技能词典匹配，更新 SQLite skills 列。

用法:
  source .venv/bin/activate
  python3 scripts/extract_skills.py              # 全量
  python3 scripts/extract_skills.py --city 成都   # 仅成都
  python3 scripts/extract_skills.py --dry-run     # 预览不写入
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Set

# ── 技能词典（中英文混合） ──
SKILL_PATTERNS: dict[str, list[str]] = {
    # 编程语言
    "Python": ["python", "django", "flask", "fastapi", "tornado", "odoo", "pytorch", "tensorflow"],
    "Java": ["java", "spring", "springboot", "spring cloud", "mybatis", "hibernate", "jvm", "maven", "gradle"],
    "Go": ["golang", "go语言", "gin", "beego"],
    "C++": ["c\\+\\+", "cpp", "qt", "stl", "boost"],
    "JavaScript": ["javascript", "js", "node\\.?js", "nodejs", "es6", "es202"],
    "TypeScript": ["typescript", "ts"],
    "C#": ["c#", "csharp", "\\.net", "dotnet", "asp\\.net"],
    "Rust": ["rust", "cargo"],
    "Kotlin": ["kotlin"],
    "PHP": ["php", "laravel", "thinkphp"],
    "Swift": ["swift", "ios"],
    "Scala": ["scala"],
    "R语言": ["r语言", "r studio"],
    "MATLAB": ["matlab"],
    "Shell": ["shell", "bash", "shell脚本"],

    # 前端框架
    "React": ["react", "react\\.js", "reactjs", "react native", "redux", "next\\.?js"],
    "Vue": ["vue", "vue\\.js", "vuejs", "nuxt", "vue3"],
    "Angular": ["angular", "angularjs"],
    "Flutter": ["flutter", "dart"],
    "HTML/CSS": ["html", "css", "html5", "css3", "sass", "less", "bootstrap"],
    "Webpack": ["webpack", "vite", "rollup", "esbuild"],
    "小程序": ["小程序", "微信小程序", "uniapp", "taro"],

    # 后端框架
    "Spring": ["spring", "springboot", "spring boot", "spring cloud", "springcloud"],
    "Django": ["django", "django rest"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "MyBatis": ["mybatis", "mybatis-plus"],
    "微服务": ["微服务", "microservice", "springcloud", "spring cloud"],
    "gRPC": ["grpc", "protobuf", "proto"],
    "GraphQL": ["graphql"],
    "消息队列": ["rabbitmq", "kafka", "rocketmq", "消息队列", "mq", "pulsar", "activemq"],

    # 数据库
    "MySQL": ["mysql", "mariadb"],
    "PostgreSQL": ["postgresql", "postgres"],
    "Redis": ["redis", "缓存"],
    "MongoDB": ["mongodb", "mongo"],
    "Elasticsearch": ["elasticsearch", "es搜索"],
    "Oracle": ["oracle"],
    "SQL Server": ["sql server", "sqlserver", "mssql", "t-sql"],
    "SQLite": ["sqlite"],
    "ClickHouse": ["clickhouse"],
    "HBase": ["hbase"],
    "Neo4j": ["neo4j", "图数据库"],
    "TiDB": ["tidb"],
    "时序数据库": ["时序数据库", "influxdb", "timescaledb", "prometheus"],

    # 大数据
    "Hadoop": ["hadoop", "hdfs", "mapreduce"],
    "Spark": ["spark"],
    "Flink": ["flink", "流计算"],
    "Kafka": ["kafka"],
    "Hive": ["hive"],
    "Airflow": ["airflow"],
    "数据仓库": ["数据仓库", "数仓", "data warehouse", "etl", "数据治理", "数据湖"],
    "数据开发": ["数据开发", "数据平台", "数据管道"],

    # AI/ML
    "机器学习": ["机器学习", "machine learning", "ml", "sklearn", "scikit-learn"],
    "深度学习": ["深度学习", "deep learning", "神经网络", "cnn", "rnn", "lstm"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow", "keras"],
    "NLP": ["nlp", "自然语言处理", "自然语言"],
    "CV": ["计算机视觉", "cv", "图像识别", "图像处理", "目标检测"],
    "大模型": ["大模型", "llm", "大语言模型", "chatgpt", "gpt", "预训练", "transformer", "bert", "lora"],
    "AIGC": ["aigc", "生成式", "stable diffusion", "sora", "midjourney"],
    "LangChain": ["langchain", "langgraph"],
    "RAG": ["rag", "知识检索", "向量检索", "知识图谱"],
    "推荐系统": ["推荐系统", "推荐算法", "协同过滤", "精排", "粗排"],
    "强化学习": ["强化学习", "reinforcement learning", "rl"],
    "语音识别": ["语音识别", "asr", "语音合成", "tts", "声纹"],

    # DevOps/云原生
    "Docker": ["docker", "容器化", "容器"],
    "Kubernetes": ["kubernetes", "k8s", "k3s"],
    "CI/CD": ["ci/cd", "cicd", "jenkins", "gitlab ci", "github actions", "持续集成", "持续部署"],
    "Linux": ["linux", "linux系统", "shell"],
    "Nginx": ["nginx", "反向代理"],
    "AWS": ["aws", "亚马逊云"],
    "阿里云": ["阿里云", "aliyun", "ack", "oss", "ecs"],
    "Azure": ["azure", "微软云"],
    "监控": ["prometheus", "grafana", "zabbix", "监控", "可观测", "elk", "alertmanager"],
    "Terraform": ["terraform", "iac", "基础设施"],
    "Ansible": ["ansible"],

    # 测试
    "自动化测试": ["自动化测试", "selenium", "appium", "pytest", "unittest", "接口测试", "性能测试", "jmeter"],
    "测试": ["测试", "软件测试", "测试用例", "测试计划", "qa", "质量保证", "白盒", "黑盒"],

    # 通用开发
    "Git": ["git", "版本控制", "gitlab", "github", "svn"],
    "REST API": ["restful", "rest api", "api开发", "接口开发"],
    "SQL": ["sql", "sql语句", "sql优化"],
    "数据结构": ["数据结构", "算法", "leetcode"],
    "系统设计": ["系统设计", "架构设计", "架构"],
    "高并发": ["高并发", "分布式", "并发", "多线程"],
    "设计模式": ["设计模式", "design pattern"],

    # 游戏
    "Unity": ["unity", "unity3d", "u3d"],
    "Unreal": ["unreal", "ue4", "ue5", "虚幻引擎"],
    "游戏引擎": ["游戏引擎", "渲染引擎", "cocos", "godot"],
    "Cocos": ["cocos", "cocos2d"],

    # 安全
    "网络安全": ["网络安全", "安全", "渗透", "漏洞", "owasp", "waf", "加密", "安全审计"],
    "信息安全": ["信息安全", "等保", "合规", "数据安全"],

    # 产品/管理
    "项目管理": ["项目管理", "scrum", "敏捷", "agile", "kanban", "看板", "pmp", "项目落地", "项目推进"],
    "数据分析": ["数据分析", "数据可视化", "tableau", "power bi", "excel", "pandas", "numpy", "数据驱动", "数据洞察", "ab测试", "a/b测试"],
    "用户研究": ["用户研究", "用户调研", "ux", "用户体验", "可用性", "用户画像", "用户旅程", "ux研究"],
    "产品经理": ["产品经理", "产品策划", "产品规划", "产品设计", "需求分析", "prd", "需求文档", "产品迭代", "产品生命周期"],
    "产品运营": ["产品运营", "用户运营", "内容运营", "活动运营", "社群运营", "运营策略", "增长运营", "精细化运营"],
    "数据运营": ["数据运营", "业务分析", "经营分析", "商业分析", "bi分析", "数据报表"],
    "市场推广": ["市场推广", "品牌营销", "数字营销", "sem", "seo", "广告投放", "增长黑客", "私域流量", "裂变"],
    "UI/UX设计": ["ui设计", "ux设计", "交互设计", "视觉设计", "figma", "sketch", "photoshop", "illustrator", "设计规范", "design system"],
    "财务/审计": ["财务", "审计", "会计", "税务", "报销", "预算", "成本控制", "财务报表"],
    "HR/招聘": ["人力资源", "hr", "招聘", "薪酬", "绩效考核", "组织发展", "员工关系", "人才发展"],
    "法务/合规": ["法务", "合规", "合同", "知识产权", "法律", "风险控制"],
    "公关/媒介": ["公关", "媒介", "品牌传播", "舆情", "危机公关", "媒体关系"],
    "供应链": ["供应链", "采购", "物流", "仓储", "库存管理", "供应商管理", "s&op"],
    "半导体/芯片": ["芯片", "半导体", "集成电路", "verilog", "dv", "设计验证", "封装", "risc-v", "arm", "asic", "fpga", "数字电路", "模拟电路"],

    # 业务领域
    "金融": ["金融", "银行", "证券", "保险", "支付", "风控", "借贷", "信用卡", "反欺诈"],
    "电商": ["电商", "交易", "订单", "供应链", "crm", "erp", "选品", "商品运营"],
    "医疗": ["医疗", "医药", "医院", "his", "健康", "临床", "药品"],
    "教育": ["教育", "教学", "培训", "学习平台", "在线教育", "k12"],
    "IOT": ["物联网", "iot", "嵌入式", "单片机", "stm32", "arm", "rtos"],
    "企业服务": ["企业服务", "saas", "paas", "iaas", "b2b", "云计算"],
    "智能制造": ["智能制造", "工业互联网", "mes", "plc", "工业4.0", "自动化产线"],
}

# 预处理成正则
_COMPILED: dict[str, re.Pattern] = {}
for _skill, _keywords in SKILL_PATTERNS.items():
    _COMPILED[_skill] = re.compile(
        "|".join(f"(?:{kw})" for kw in _keywords),
        re.IGNORECASE,
    )

# 普通文本的简单匹配（不离散分词，直接 regex）
def extract_skills(text: str) -> list[str]:
    """从文本中提取技能标签。"""
    if not text or len(text) < 5:
        return []
    found = []
    for skill, pattern in _COMPILED.items():
        if pattern.search(text):
            found.append(skill)
    return found


def update_db(db_path: Path, city: str | None = None, dry_run: bool = False):
    """批量提取并更新数据库。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where = "WHERE city = ?" if city else ""
    params = (city,) if city else ()

    cur.execute(f"SELECT id, title, description FROM jobs {where}", params)
    rows = cur.fetchall()

    stats = Counter()
    updates = []
    for row in rows:
        jid, title, desc = row["id"], row["title"] or "", row["description"] or ""
        text = f"{title} {desc[:3000]}"  # 用 title + 前 3000 字
        skills = extract_skills(text)
        stats["total"] += 1
        if skills:
            stats["has_skills"] += 1
            stats["avg_skills"] += len(skills)
            if not dry_run:
                updates.append((json.dumps(skills, ensure_ascii=False), jid))
        else:
            stats["no_skills"] += 1

    if not dry_run and updates:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.executemany("UPDATE jobs SET skills = ? WHERE id = ?", updates)
        conn.commit()

    conn.close()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}处理完成:")
    print(f"  总岗位: {stats['total']}")
    print(f"  有技能: {stats['has_skills']} ({stats['has_skills']/stats['total']*100:.1f}%)")
    if stats["has_skills"] > 0:
        print(f"  均技能数: {stats['avg_skills']/stats['has_skills']:.1f}")
    print(f"  无技能: {stats['no_skills']}")

    # TOP 技能分布
    if not dry_run and city == "成都":
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT skills FROM jobs WHERE city='成都' AND skills IS NOT NULL AND skills != '[]'")
        counter = Counter()
        for (s,) in cur.fetchall():
            try:
                for sk in json.loads(s):
                    counter[sk] += 1
            except:
                pass
        print(f"\n  成都技能 TOP 20:")
        for s, c in counter.most_common(20):
            print(f"    {s}: {c}")
        conn.close()

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, default="成都")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = Path(__file__).resolve().parent.parent / "data" / "processed" / "jobs.db"
    update_db(db, city=args.city, dry_run=args.dry_run)

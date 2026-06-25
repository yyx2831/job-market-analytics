"""技能深度学习路线指南。

为每个高 ROI 技能提供：市场数据、学习路径、子技能拆解、时间估算。
数据来源：job-market-analytics 真实招聘数据。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class SkillSubItem:
    """技能子项。"""
    name: str
    level: str  # 入门 / 进阶 / 精通
    desc: str
    hours: int  # 预估学习小时数


@dataclass
class SkillGuide:
    """单个技能的学习路线指南。"""
    skill: str
    category: str  # 编程语言 / 数据库 / 运维 / 管理 / 数据
    summary: str
    why_learn: str
    market_data: Dict  # demand, median_salary, roi_score
    co_skills: List[str]  # 共现技能
    typical_roles: List[str]
    subs: List[SkillSubItem]
    total_hours: int
    difficulty: str  # 入门 / 中等 / 较难 / 专家
    resources_hint: str


# ── 基于真实数据的技能指南 ──

SKILL_GUIDES: Dict[str, SkillGuide] = {
    "Python": SkillGuide(
        skill="Python",
        category="编程语言",
        summary="全栈通用语言，Web 后端、数据分析、AI、自动化测试全覆盖。成都 257 个岗位要求 Python，需求排第 1。",
        why_learn=(
            "Python 是成都技术岗需求最高的技能（257 个岗位），覆盖面极广。"
            "从 Web 后端到 AI 算法到自动化测试，几乎所有技术方向都需要。"
            "学习曲线平缓，适合作为第一语言或第二语言。"
        ),
        market_data={"demand": 257, "median_salary": "13K", "roi_score": 69},
        co_skills=["SQL", "Java", "Go", "C++", "Linux", "Docker"],
        typical_roles=["Python开发工程师", "后端开发", "AI工程师", "数据分析师", "自动化测试"],
        subs=[
            SkillSubItem("语法基础", "入门", "变量、数据类型、控制流、函数、类", 40),
            SkillSubItem("标准库", "入门", "os/sys/json/datetime/collections/itertools", 30),
            SkillSubItem("Web框架", "进阶", "FastAPI(主推)/Django/Flask，RESTful API设计", 60),
            SkillSubItem("数据库交互", "进阶", "SQLAlchemy ORM，MySQL/PostgreSQL/Redis 操作", 40),
            SkillSubItem("异步编程", "进阶", "async/await，asyncio，并发模型", 30),
            SkillSubItem("测试与部署", "进阶", "pytest，Docker，CI/CD，uv/poetry 包管理", 30),
            SkillSubItem("AI生态", "精通", "NumPy/Pandas，PyTorch/TensorFlow，LangChain", 80),
        ],
        total_hours=310,
        difficulty="入门友好",
        resources_hint="官方文档 + 《Fluent Python》 + fastapi.tiangolo.com",
    ),
    "SQL": SkillGuide(
        skill="SQL",
        category="数据库",
        summary="数据操作通用语言，251 个岗位要求，与 Python/Java 强绑定。不是可选项，是必备项。",
        why_learn=(
            "SQL 需求排第 2（251 个岗位），几乎每份技术岗 JD 都要求。"
            "后端、数据分析、产品经理都需要。最简单的「高杠杆」技能——投入少，回报高。"
        ),
        market_data={"demand": 251, "median_salary": "12.5K", "roi_score": 67},
        co_skills=["Java", "MySQL", "Python", "Redis", "需求分析"],
        typical_roles=["Java开发", "Python开发", "数据分析师", "DBA", "后端开发"],
        subs=[
            SkillSubItem("基础查询", "入门", "SELECT/WHERE/JOIN/GROUP BY/ORDER BY/HAVING", 20),
            SkillSubItem("子查询与窗口函数", "入门", "子查询，ROW_NUMBER/RANK/LAG/LEAD", 20),
            SkillSubItem("表设计与索引", "进阶", "范式设计，B+树索引，执行计划 EXPLAIN", 30),
            SkillSubItem("事务与锁", "进阶", "ACID，隔离级别，MVCC，死锁排查", 20),
            SkillSubItem("性能优化", "精通", "慢查询分析，分库分表，读写分离，Redis 缓存策略", 30),
        ],
        total_hours=120,
        difficulty="入门友好",
        resources_hint="《SQL必知必会》+ LeetCode SQL题库 + MySQL官方文档",
    ),
    "Java": SkillGuide(
        skill="Java",
        category="编程语言",
        summary="企业级后端霸主，成都 204 个岗位，大量国企/银行/政企采用。稳定高薪。",
        why_learn=(
            "Java 岗位数排第 3（204 个），在国企、银行、政企市场不可替代。"
            "生态成熟、岗位稳定。虽然学习曲线比 Python 陡，但回报稳定持久。"
        ),
        market_data={"demand": 204, "median_salary": "13K", "roi_score": 60},
        co_skills=["Go", "Python", "SQL", "Linux", "需求分析"],
        typical_roles=["Java开发工程师", "后端架构师", "大数据工程师", "Android开发"],
        subs=[
            SkillSubItem("核心语法", "入门", "OOP，集合框架，异常处理，IO流，泛型", 60),
            SkillSubItem("Spring生态", "进阶", "Spring Boot/Spring Cloud/Spring Security，MVC架构", 80),
            SkillSubItem("中间件", "进阶", "MyBatis/JPA，Redis，RabbitMQ/Kafka，Nacos", 60),
            SkillSubItem("JVM", "精通", "内存模型，GC调优，类加载机制，性能诊断", 50),
            SkillSubItem("微服务架构", "精通", "分布式事务，服务治理，容器化部署，K8s", 60),
        ],
        total_hours=310,
        difficulty="中等",
        resources_hint="《Java核心技术》+ Spring官方文档 + 《深入理解Java虚拟机》",
    ),
    "Redis": SkillGuide(
        skill="Redis",
        category="数据库",
        summary="高性能缓存中间件，104 个岗位要求，几乎每家中大型后端团队标配。小而精的高价值技能。",
        why_learn=(
            "Redis 是后端开发必问技能。掌握缓存策略、分布式锁、消息队列，面试和工作中高频用到。"
            "学习周期短（约 60 小时），但面试权重极高。"
        ),
        market_data={"demand": 104, "median_salary": "13.5K", "roi_score": 43},
        co_skills=["SQL", "MySQL", "Java", "需求分析", "Docker"],
        typical_roles=["Java开发", "Python后端", "Go后端", "架构师", "DevOps"],
        subs=[
            SkillSubItem("数据结构", "入门", "String/Hash/List/Set/Sorted Set 使用场景", 15),
            SkillSubItem("高级特性", "进阶", "Pipeline，Lua脚本，Pub/Sub，Stream", 15),
            SkillSubItem("实战模式", "进阶", "缓存穿透/击穿/雪崩，分布式锁，延时队列，布隆过滤器", 20),
            SkillSubItem("集群与持久化", "精通", "RDB/AOF，主从+哨兵，Cluster分片，一致性保证", 15),
        ],
        total_hours=65,
        difficulty="入门友好",
        resources_hint="《Redis设计与实现》+ redis.io 官方文档 + 实际项目操练",
    ),
    "C++": SkillGuide(
        skill="C++",
        category="编程语言",
        summary="系统级语言，AI推理引擎、嵌入式、量化交易核心语言。需求 56 个岗位，中位薪资 17.5K，高薪导向。",
        why_learn=(
            "C++ 岗位虽少（56个），但薪资高（中位 17.5K）。在 AI 推理、自动驾驶、嵌入式、量化交易领域不可替代。"
            "门槛高但护城河深，越老越吃香。"
        ),
        market_data={"demand": 56, "median_salary": "17.5K", "roi_score": 42},
        co_skills=["Python", "深度学习", "机器学习", "Java", "Go"],
        typical_roles=["算法工程师", "嵌入式开发", "量化开发", "游戏引擎开发", "AI推理工程师"],
        subs=[
            SkillSubItem("C++基础", "入门", "指针/引用，内存管理，STL容器和算法，RAII", 80),
            SkillSubItem("现代C++", "进阶", "C++11/14/17/20 新特性，智能指针，移动语义，lambda", 60),
            SkillSubItem("并发编程", "进阶", "thread/mutex/condition_variable，无锁编程，内存模型", 50),
            SkillSubItem("系统编程", "精通", "操作系统原理，内存映射，网络编程，性能优化", 80),
        ],
        total_hours=270,
        difficulty="较难",
        resources_hint="《C++ Primer》+ cppreference.com + 《Effective Modern C++》",
    ),
    "Linux": SkillGuide(
        skill="Linux",
        category="运维/基础",
        summary="服务器操作系统基石，124 个岗位要求。运维部署、后端开发必备基础技能。",
        why_learn=(
            "Linux 是后端开发的「空气技能」——需不需要都写在了 JD 里（124 个岗位）。"
            "不会 Linux，就无法独立部署、排查问题。投入低，必须学。"
        ),
        market_data={"demand": 124, "median_salary": "11.5K", "roi_score": 43},
        co_skills=["Python", "SQL", "Java", "Docker", "MySQL"],
        typical_roles=["后端开发", "运维/SRE", "DevOps", "嵌入式开发"],
        subs=[
            SkillSubItem("基础操作", "入门", "文件系统，权限，管道，vim，Shell脚本", 30),
            SkillSubItem("系统管理", "入门", "进程/内存/磁盘管理，systemd服务，日志查看", 20),
            SkillSubItem("网络与安全", "进阶", "iptables/firewalld，SSH，SSL/TLS，DNS配置", 20),
            SkillSubItem("性能与排错", "进阶", "top/htop/strace/perf，内核参数调优，故障排查方法论", 30),
        ],
        total_hours=100,
        difficulty="入门友好",
        resources_hint="《鸟哥的Linux私房菜》+ Linux命令行实战，装个虚拟机练习",
    ),
    "Docker": SkillGuide(
        skill="Docker",
        category="运维/DevOps",
        summary="容器化标配，88 个岗位要求。一键部署、环境隔离、微服务基石。中位薪资 14K。",
        why_learn=(
            "Docker 是现代化部署的基础设施。不管是面哪个后端岗，Docker 都是加分项。"
            "从学会 Dockerfile 到 docker-compose 编排，投入 60 小时即可覆盖 90% 日常工作。"
        ),
        market_data={"demand": 88, "median_salary": "14K", "roi_score": 41},
        co_skills=["SQL", "Python", "Redis", "Java", "Linux"],
        typical_roles=["Python后端", "Java后端", "DevOps", "架构师"],
        subs=[
            SkillSubItem("核心概念", "入门", "Image/Container/Volume/Network，Dockerfile 编写", 20),
            SkillSubItem("多容器编排", "进阶", "docker-compose，服务依赖，环境变量，健康检查", 15),
            SkillSubItem("镜像优化", "进阶", "多阶段构建，Alpine基础镜像，层缓存策略，安全扫描", 15),
            SkillSubItem("生产实践", "精通", "Registry管理，日志收集，监控，配合 K8s 基础概念", 15),
        ],
        total_hours=65,
        difficulty="入门友好",
        resources_hint="Docker官方文档 + 《Docker——从入门到实践》+ 用 Docker 部署一个完整项目",
    ),
    "数据分析": SkillGuide(
        skill="数据分析",
        category="数据",
        summary="跨行业必备能力，116 个岗位。Python/SQL + 业务洞察 = 数据驱动决策。",
        why_learn=(
            "数据分析是「非技术岗转技术」的最佳跳板。116 个岗位，覆盖面从互联网到制造业。"
            "核心技能栈（SQL+Python+可视化）可复用性极高。"
        ),
        market_data={"demand": 116, "median_salary": "11K", "roi_score": 40},
        co_skills=["Python", "SQL", "深度学习", "Excel", "机器学习"],
        typical_roles=["数据分析师", "商业分析师", "BI工程师", "数据运营"],
        subs=[
            SkillSubItem("分析思维", "入门", "指标体系搭建，漏斗分析，A/B测试，可视化原则", 30),
            SkillSubItem("工具链", "入门", "SQL进阶查询，Pandas数据处理，Matplotlib/Plotly可视化", 40),
            SkillSubItem("统计学", "进阶", "描述统计，假设检验，回归分析，时间序列", 40),
            SkillSubItem("BI与报表", "进阶", "Power BI/Tableau/Superset 仪表盘搭建", 30),
            SkillSubItem("机器学习入门", "精通", "sklearn分类/聚类，特征工程，模型评估", 50),
        ],
        total_hours=190,
        difficulty="中等",
        resources_hint="《利用Python进行数据分析》+ Kaggle入门赛 + Power BI官方学习路径",
    ),
    "MySQL": SkillGuide(
        skill="MySQL",
        category="数据库",
        summary="关系数据库之王，130 个岗位要求。后端开发、数据分析必备，与 SQL 强绑定。",
        why_learn=(
            "MySQL 是后端开发最常见的关系型数据库（130 个岗位）。"
            "掌握索引优化、事务隔离、主从复制，面试高频且日常工作必备。"
        ),
        market_data={"demand": 130, "median_salary": "12.5K", "roi_score": 46},
        co_skills=["SQL", "Java", "Redis", "Linux", "Docker"],
        typical_roles=["Java开发", "Python开发", "Go开发", "DBA"],
        subs=[
            SkillSubItem("基础操作", "入门", "DDL/DML，CHAR vs VARCHAR，外键约束，基础查询", 20),
            SkillSubItem("索引与优化", "进阶", "B+树原理，覆盖索引，最左前缀，慢查询优化", 30),
            SkillSubItem("事务与锁", "进阶", "ACID，MVCC，行锁/间隙锁，死锁分析和避免", 25),
            SkillSubItem("高可用架构", "精通", "主从复制，MGR，分库分表，读写分离，备份恢复", 25),
        ],
        total_hours=100,
        difficulty="中等",
        resources_hint="《高性能MySQL》+ MySQL官方文档 + 在项目中实际优化慢查询",
    ),
    "产品经理": SkillGuide(
        skill="产品经理",
        category="管理/产品",
        summary="技术转管理的最优路径。29 个岗位但中位薪资高达 22.5K，ROI 排第 5。",
        why_learn=(
            "产品经理是「技术+业务」的交叉角色。虽然岗位量少于纯技术岗（29个），"
            "但薪资上限极高（中位 22.5K），适合有技术背景想往业务方向发展的同学。"
        ),
        market_data={"demand": 29, "median_salary": "22.5K", "roi_score": 46},
        co_skills=["需求分析", "项目管理", "数据分析", "UI设计", "运营"],
        typical_roles=["产品经理", "产品总监", "增长产品", "AI产品经理"],
        subs=[
            SkillSubItem("产品思维", "入门", "用户研究，需求分析，竞品分析，MVP方法论", 40),
            SkillSubItem("工具与流程", "入门", "Axure/Figma原型，PRD文档，敏捷/Scrum流程", 30),
            SkillSubItem("数据分析", "进阶", "数据驱动决策，埋点体系，A/B测试设计", 30),
            SkillSubItem("商业与策略", "进阶", "商业模式画布，定价策略，增长黑客，OKR", 30),
            SkillSubItem("AI产品", "精通", "大模型产品设计，Prompt工程，AI产品伦理", 40),
        ],
        total_hours=170,
        difficulty="中等（需技术背景）",
        resources_hint="《启示录》+ 《俞军产品方法论》+ 实际从0到1做一个小产品",
    ),
}


def get_guide(skill_name: str) -> Optional[SkillGuide]:
    """获取指定技能的学习指南。"""
    return SKILL_GUIDES.get(skill_name)


def get_all_guides() -> List[SkillGuide]:
    """获取所有技能指南。"""
    return list(SKILL_GUIDES.values())


def get_learning_path_summary(top_n: int = 10) -> str:
    """生成综合学习路径建议。"""
    guides = get_all_guides()
    # 按 ROI 排序
    sorted_guides = sorted(guides, key=lambda g: g.market_data.get("roi_score", 0), reverse=True)
    top = sorted_guides[:top_n]

    lines = [
        "# 📚 成都技术岗技能学习路线图",
        "",
        "> 基于 **3,265 条真实招聘数据**，综合需求频率 × 薪资水平 计算 ROI。",
        "",
        "## 🎯 核心结论",
        "",
        "### 必学三件套（几乎每个技术岗都要）",
        "1. **Python** — 257 个岗位，GitHub AI 生态全在 Python 上，不学就落后",
        "2. **SQL** — 251 个岗位，不管你写什么后端，数据都得查",
        "3. **Linux** — 124 个岗位，不会 Linux 等于不会部署",
        "",
        "### 高性价比进阶（投入少，回报高）",
        "- **Redis**（60小时 → 面试高频 + 日常工作必备）",
        "- **Docker**（65小时 → 一键部署，告别「我这能跑啊」）",
        "- **MySQL**（100小时 → SQL + MySQL 组合拳，后端面试必考）",
        "",
        "### 高薪赛道（难度高但薪资天花板高）",
        "- **C++**（17.5K中位 → AI推理/自动驾驶/量化交易）",
        "- **产品经理**（22.5K中位 → 技术转管理的桥梁）",
        "",
        "## 📊 技能对比总览",
        "",
        "| 技能 | 需求 | 中位薪资 | 难度 | 学习时长 | ROI |",
        "|------|------|----------|------|----------|-----|",
    ]

    for g in sorted_guides[:top_n]:
        lines.append(
            f"| {g.skill} | {g.market_data['demand']} | {g.market_data['median_salary']} | "
            f"{g.difficulty} | {g.total_hours}h | {g.market_data['roi_score']} |"
        )

    lines += [
        "",
        "## 🗺️ 推荐学习顺序",
        "",
        "```",
        "第1个月: Python(40h) + SQL(20h) + Linux基础(30h)  → 打好基础",
        "第2个月: SQL进阶(30h) + MySQL(50h) + Docker(40h)   → 后端基建",
        "第3个月: Web框架(60h) + Redis(40h)                  → 能做项目",
        "第4-6月: FastAPI实战 + 测试 + CI/CD + 刷题            → 找工作中",
        "",
        "高薪方向（有基础后选一条）:",
        "  数据方向: 数据分析(190h) → 机器学习 → AI工程",
        "  底层方向: C++(270h) → 系统编程 → 量化/自动驾驶",
        "  管理方向: 技术2年+ → 产品思维(100h) → 产品经理",
        "```",
        "",
    ]

    return "\n".join(lines)

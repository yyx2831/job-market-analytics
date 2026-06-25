"""
JD 自然语言深度分析 — 对岗位描述（description）做结构化提取。

提取维度：
  - 核心职责 (responsibilities): 分离出来的职责列表
  - 技术要求 (requirements): 硬性技能要求列表
  - 加分项 (preferred): 优先/加分条件
  - 福利待遇 (benefits): 提取的福利描述
  - 技术关键词密度 (tech_density): 技术词频/描述长度比值
  - JD 结构完整性 (structure_score): 是否有职/要/福等章节
  - 职能分类 (function_category): 研发/数据/产品/运维/管理等
  - 目标画像 (candidate_profile): 经验/学历/语言等隐含要求
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from collections import Counter


# ═══════════════════════════════════════
# 章节切分模式
# ═══════════════════════════════════════

SECTION_MARKERS = {
    'responsibilities': [
        r'岗位职责[：:]', r'工作职责[：:]', r'职责描述[：:]',
        r'工作内容[：:]', r'主要职责[：:]', r'Responsibilities',
        r'Job\s*Description', r'主要工作[：:]', r'岗位描述[：:]',
    ],
    'requirements': [
        r'任职要求[：:]', r'岗位要求[：:]', r'职位要求[：:]',
        r'招聘要求[：:]', r'技能要求[：:]', r'Requirements',
        r'Qualifications', r'任职资格[：:]', r'能力要求[：:]',
    ],
    'preferred': [
        r'优先条件[：:]', r'加分项[：:]', r'优先考虑[：:]',
        r'Preferred', r'有以下经验者优先', r'加分条件[：:]',
        r'具有以下条件.*优先', r'Nice\s*to\s*Have',
    ],
    'benefits': [
        r'福利待遇[：:]', r'公司福利[：:]', r'薪酬福利[：:]',
        r'Benefits', r'我们提供[：:]', r'你将获得[：:]',
        r'薪资福利[：:]', r'待遇[：:]', r'工作福利[：:]',
        r'五险一金', r'年终奖', r'带薪年假',
    ],
    'about_company': [
        r'公司介绍[：:]', r'关于我们[：:]', r'企业简介[：:]',
        r'About\s*Us', r'公司简介[：:]', r'集团介绍[：:]',
    ],
}


def split_sections(text: str) -> Dict[str, str]:
    """
    按章节切分 JD 文本。
    返回 {section_name: content} 字典。
    """
    if not text:
        return {}

    sections: Dict[str, str] = {}
    text_normalized = text.replace('\r\n', '\n').replace('\r', '\n')

    # 统一合并连续空行
    text_normalized = re.sub(r'\n{3,}', '\n\n', text_normalized)

    # 找所有章节标记位置
    markers: List[Tuple[str, int, int]] = []  # (section_name, start, end)
    for section_name, patterns in SECTION_MARKERS.items():
        for pat in patterns:
            for m in re.finditer(pat, text_normalized, re.IGNORECASE):
                markers.append((section_name, m.start(), m.end()))

    if not markers:
        # 没有明确章节标记，尝试按自然段划分
        sections['_full'] = text_normalized
        return sections

    # 按位置排序
    markers.sort(key=lambda x: x[1])

    # 提取每个章节内容
    for i, (name, start, end) in enumerate(markers):
        # 找到下一个章节标记的位置
        next_start = len(text_normalized)
        for j in range(i + 1, len(markers)):
            if markers[j][1] > end:
                next_start = markers[j][1]
                break

        content = text_normalized[end:next_start].strip()
        # 去除内容开头的标点符号和空白
        content = re.sub(r'^[：:，,\s]+', '', content)

        if name not in sections:
            sections[name] = content
        else:
            sections[name] += '\n' + content

    return sections


# ═══════════════════════════════════════
# 技术关键词密度分析
# ═══════════════════════════════════════

TECH_KEYWORDS_WEIGHTS = {
    # 语言/框架
    'Python': 1, 'Java': 1, 'Go': 1, 'Golang': 1, 'Rust': 1,
    'C\+\+': 1, 'C#': 1, 'JavaScript': 1, 'TypeScript': 1, 'Kotlin': 1,
    'Scala': 1, 'Swift': 1, 'Shell': 1, 'Bash': 1,
    'Spring': 1, 'SpringBoot': 1, 'SpringCloud': 1,
    'Django': 1, 'Flask': 1, 'FastAPI': 1,
    'React': 1, 'Vue': 1, 'Angular': 1, 'Node\.js': 1,
    'PyTorch': 1, 'TensorFlow': 1, 'Keras': 1,
    # 中文框架
    '微服务': 1, '分布式': 1.5, '高并发': 1.5, '多线程': 1,
    # 基础设施
    'Kubernetes': 1.5, 'K8s': 1.5, 'Docker': 1.5,
    'Terraform': 1.5, 'Helm': 1.5, 'Ansible': 1.5,
    'MySQL': 1, 'PostgreSQL': 1, 'MongoDB': 1, 'Redis': 1,
    'Kafka': 1.5, 'RabbitMQ': 1, 'Elasticsearch': 1.5,
    'Spark': 1.5, 'Flink': 1.5, 'Hadoop': 1,
    'Nginx': 1, 'Tomcat': 1, 'Jenkins': 1, 'GitLab': 1,
    'Zookeeper': 1, 'Etcd': 1, 'Consul': 1,
    # 中文基础设施
    '容器': 1, '容器化': 1.5, '云原生': 1.5,
    '消息队列': 1, '缓存': 1, '数据库': 1,
    '负载均衡': 1, '服务发现': 1, '配置中心': 1,
    '持续集成': 1, '持续部署': 1, '灰度发布': 1,
    # AI/ML
    'AI': 2, '人工智能': 2, 'LLM': 2, '大模型': 2,
    'LangChain': 2, 'LlamaIndex': 2,
    'RAG': 2, 'Agent': 2, 'Transformer': 2, 'BERT': 2,
    'GPT': 2, 'ChatGPT': 2,
    '深度学习': 2, '机器学习': 2, '模型训练': 2,
    'NLP': 2, '自然语言处理': 2, 'CV': 2, '计算机视觉': 2,
    '推荐系统': 2, '强化学习': 2, '强化': 2,
    'MLOps': 2, 'CUDA': 2, 'ONNX': 2, 'TensorRT': 2,
    '微调': 2, '预训练': 2, '向量数据库': 2,
    '生成式': 2, 'GAN': 2, 'Diffusion': 2,
    'AIGC': 2, '多模态': 2, '视觉': 1,
    # 中文AI
    '算法': 2, '推理': 1.5, '模型压缩': 1.5, '量化': 1.5,
    # 云/大数据
    'AWS': 1, 'Azure': 1, 'GCP': 1, '阿里云': 1, '腾讯云': 1,
    '华为云': 1, 'Serverless': 1,
    'CI.*CD': 1, 'DevOps': 1, 'SRE': 1,
    '数据湖': 1.5, '数据仓库': 1.5, '数仓': 1.5,
    '流计算': 1.5, '实时计算': 1.5, '离线数仓': 1,
    'Hive': 1, 'HBase': 1, 'Presto': 1, 'ClickHouse': 1.5,
    'Doris': 1, 'StarRocks': 1, 'TiDB': 1,
    # 测试/QA
    '自动化测试': 1, 'Selenium': 1, 'JMeter': 1,
    'Appium': 1, 'Pytest': 1, 'JUnit': 1,
}


def compute_tech_density(text: str) -> Dict:
    """
    计算技术关键词密度。
    返回 {density, keywords_found, unique_count, total_weight}。
    """
    if not text:
        return {'density': 0, 'keywords_found': {}, 'unique_count': 0, 'total_weight': 0}

    text_lower = text.lower()
    keywords_found: Dict[str, int] = {}
    total_weight = 0.0

    for keyword, weight in TECH_KEYWORDS_WEIGHTS.items():
        kw_lower = keyword.lower()
        # 对纯英文关键词使用 word boundary，中英文混合不使用
        if re.match(r'^[a-zA-Z]', kw_lower):
            count = len(re.findall(r'(?i)\b' + re.escape(kw_lower) + r'\b', text))
        else:
            count = len(re.findall(re.escape(kw_lower), text_lower))
        if count > 0:
            keywords_found[keyword] = count
            total_weight += count * weight

    # 密度 = 加权总分 / (文本字符数/1000)，标准化到每千字
    density = total_weight / (max(len(text), 100) / 1000)

    return {
        'density': round(density, 2),
        'keywords_found': keywords_found,
        'unique_count': len(keywords_found),
        'total_weight': round(total_weight, 1),
    }


# ═══════════════════════════════════════
# 职能分类
# ═══════════════════════════════════════

FUNCTION_PATTERNS = {
    'AI/算法': [
        r'\b(算法|机器学习|深度学习|AI|LLM|NLP|CV|大模型|Agent|RAG|PyTorch|TensorFlow)\b',
        r'\b(数据科学|Data\s*Scientist|人工智能|Computer\s*Vision)\b',
    ],
    '数据': [
        r'\b(数据分析|数据工程师|数据仓库|ETL|BI|商业智能|数仓)\b',
        r'\b(Data\s*Engineer|Data\s*Analyst|大数据)\b',
    ],
    '后端开发': [
        r'\b(后端|服务端|Java\s*开发|Python\s*开发|Go\s*开发|C\+\+\s*开发)\b',
        r'\b(Backend|Server|Spring|Django|FastAPI|微服务)\b',
    ],
    '前端/客户端': [
        r'\b(前端|Web\s*前端|React|Vue|Angular|小程序|iOS|Android|Flutter)\b',
        r'\b(移动端|客户端|H5|网页)\b',
    ],
    '测试': [
        r'\b(测试|QA|质量|自动化测试|性能测试|安全测试)\b',
    ],
    '运维/DevOps': [
        r'\b(运维|DevOps|SRE|Kubernetes|Docker|CI|CD|云平台)\b',
        r'\b(系统管理|网络工程师|安全工程师)\b',
    ],
    '产品': [
        r'\b(产品经理|产品设计|产品运营|Product\s*Manager|PO)\b',
    ],
    '管理': [
        r'\b(技术经理|项目经理|Team\s*Lead|技术总监|CTO|架构师)\b',
        r'\b(项目主管|研发经理|部门经理)\b',
    ],
    '嵌入式/硬件': [
        r'\b(嵌入式|单片机|ARM|FPGA|硬件|IoT|物联网|驱动)\b',
    ],
    '其他': [],
}


def classify_function(title: str, description: Optional[str]) -> Tuple[str, float]:
    """
    根据标题（主信号）和描述（辅信号）分类职能方向。
    返回 (category, confidence)。
    """
    title_lower = (title or '').lower()
    desc_lower = (description or '').lower()

    # 标题权重 > 描述权重
    scores: Dict[str, float] = {}

    for category, patterns in FUNCTION_PATTERNS.items():
        if category == '其他':
            continue
        score = 0.0
        for pat in patterns:
            # 标题匹配权重 ×3
            title_matches = len(re.findall(pat, title_lower))
            score += title_matches * 3
            # 描述匹配权重 ×1
            desc_matches = len(re.findall(pat, desc_lower))
            score += desc_matches * 1
        if score > 0:
            scores[category] = score

    if not scores:
        # 兜底：基于标题关键词
        simple_patterns = {
            'AI/算法': r'(算法|AI|机器学习|深度学习|大模型|NLP|CV|视觉|语音)',
            '数据': r'(数据|数仓|BI|ETL|报表)',
            '后端开发': r'(后端|服务端|java|python|golang|go\s|C\+\+|php|ruby|\.net)',
            '前端/客户端': r'(前端|web|react|vue|angular|ios|android|小程序|H5|flutter)',
            '测试': r'(测试|QA|质量)',
            '运维/DevOps': r'(运维|devops|sre|平台|基础设施|安全)',
            '产品': r'(产品经理|产品设计|产品|PO)',
            '管理': r'(经理|主管|总监|Lead|team\s*lead|负责人)',
            '嵌入式/硬件': r'(嵌入式|单片机|arm|fpga|硬件|IoT|驱动|firmware)',
        }
        for cat, pat in simple_patterns.items():
            if re.search(pat, title_lower):
                return cat, 0.6
        return '其他', 0.0

    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = scores[best] / total if total > 0 else 0

    return best, round(confidence, 2)


# ═══════════════════════════════════════
# 目标画像提取
# ═══════════════════════════════════════


def extract_candidate_profile(description: str) -> Dict[str, Optional[str]]:
    """
    从 JD 描述中提取目标候选人画像。
    """
    if not description:
        return {}

    profile: Dict[str, Optional[str]] = {}

    # 学历
    edu_patterns = [
        (r'(硕士|研究生|博士)', '硕士及以上'),
        (r'本[科科学]', '本科'),
        (r'大专|专科', '大专'),
        (r'(学历不限|无学历)', '不限'),
    ]
    for pat, level in edu_patterns:
        if re.search(pat, description):
            profile['expected_education'] = level
            break
    if 'expected_education' not in profile:
        profile['expected_education'] = '未明确'

    # 经验年限
    exp_matches = re.findall(r'(\d+)[-~至到]*(\d+)?\s*年(以上|经验|工作)', description)
    if exp_matches:
        years = []
        for m in exp_matches:
            if m[1]:
                years.append((int(m[0]) + int(m[1])) / 2)
            else:
                years.append(float(m[0]))
        profile['expected_experience_years'] = f'{min(years):.0f}-{max(years):.0f}年'
    else:
        if re.search(r'(应届|毕业生|无需经验|不限经验)', description):
            profile['expected_experience_years'] = '应届/不限'
        else:
            profile['expected_experience_years'] = '未明确'

    # 英语要求
    if re.search(r'(英语|英文|CET[- ]?[46]|雅思|托福|TEM[- ]?[48])', description):
        profile['english_required'] = '是'
    else:
        profile['english_required'] = '否'

    # 团队管理
    if re.search(r'(带团队|管理团队|团队管理|管理经验|带队)', description):
        profile['management_required'] = '是'
    else:
        profile['management_required'] = '否'

    # 开源/社区
    if re.search(r'(开源|GitHub|社区|技术博客|技术分享|演讲)', description):
        profile['oss_participation'] = '加分'
    else:
        profile['oss_participation'] = '未提及'

    return profile


# ═══════════════════════════════════════
# JD 结构完整性评分
# ═══════════════════════════════════════


def score_jd_structure(sections: Dict[str, str], description: str) -> int:
    """
    评估 JD 文档结构完整性 (1-10)。
    """
    score = 3  # 基准

    section_weights = {
        'responsibilities': 2,
        'requirements': 2,
        'benefits': 1.5,
        'preferred': 1,
        'about_company': 0.5,
    }

    for section, weight in section_weights.items():
        if section in sections and len(sections[section]) > 30:
            score += weight

    if description:
        # 字数奖励
        if len(description) > 3000:
            score += 1.5
        elif len(description) > 1500:
            score += 1
        elif len(description) > 800:
            score += 0.5

    return min(10, round(score))


# ═══════════════════════════════════════
# 全量分析入口
# ═══════════════════════════════════════

from dataclasses import dataclass, field, asdict


@dataclass
class JDAnalysisResult:
    """单条 JD 深度分析结果。"""
    job_id: int
    function_category: str
    function_confidence: float
    tech_density: float
    tech_keywords_count: int
    top_tech_keywords: str  # JSON: {kw: count}
    jd_structure_score: int
    expected_education: str
    expected_experience: str
    english_required: str
    management_required: str
    oss_participation: str
    has_responsibilities: bool
    has_requirements: bool
    has_benefits: bool
    has_preferred: bool
    # 职责/要求的数量估计
    responsibility_count: int
    requirement_count: int


def analyze_jd(job_id: int, title: str, description: Optional[str]) -> Optional[JDAnalysisResult]:
    """
    对单条 JD 做深度 NLP 分析。
    仅对有足够描述内容的岗位进行分析。
    """
    if not description or len(description) < 50:
        return None

    # 章节切分
    sections = split_sections(description)

    # 职能分类
    func_cat, func_conf = classify_function(title, description)

    # 技术密度
    tech_info = compute_tech_density(description)

    # JD 结构评分
    structure_score = score_jd_structure(sections, description)

    # 目标画像
    profile = extract_candidate_profile(description)

    # 计数职责/要求条目（按行或编号分割）
    req_text = sections.get('requirements', '')
    resp_text = sections.get('responsibilities', '')

    resp_count = max(
        len(re.findall(r'[（(]?\d+[）).、]', resp_text)),
        len([l for l in resp_text.split('\n') if len(l.strip()) > 10])
    )

    req_count = max(
        len(re.findall(r'[（(]?\d+[）).、]', req_text)),
        len([l for l in req_text.split('\n') if len(l.strip()) > 10])
    )

    # Top tech keywords (top 10 by count)
    top_kw = sorted(tech_info['keywords_found'].items(), key=lambda x: -x[1])[:10]
    top_kw_str = ','.join(f'{k}:{v}' for k, v in top_kw)

    return JDAnalysisResult(
        job_id=job_id,
        function_category=func_cat,
        function_confidence=func_conf,
        tech_density=tech_info['density'],
        tech_keywords_count=tech_info['unique_count'],
        top_tech_keywords=top_kw_str,
        jd_structure_score=structure_score,
        expected_education=profile.get('expected_education', '未明确'),
        expected_experience=profile.get('expected_experience_years', '未明确'),
        english_required=profile.get('english_required', '否'),
        management_required=profile.get('management_required', '否'),
        oss_participation=profile.get('oss_participation', '未提及'),
        has_responsibilities=bool(resp_count),
        has_requirements=bool(req_count),
        has_benefits='benefits' in sections,
        has_preferred='preferred' in sections,
        responsibility_count=resp_count,
        requirement_count=req_count,
    )


def batch_analyze_jd(conn, limit: Optional[int] = None) -> List[JDAnalysisResult]:
    """批量分析有描述的岗位。"""
    query = "SELECT id, title, description FROM jobs WHERE description IS NOT NULL AND length(description) > 50"
    if limit:
        query += f" LIMIT {limit}"

    cur = conn.execute(query)
    results = []
    for row in cur:
        result = analyze_jd(row[0], row[1], row[2])
        if result:
            results.append(result)

    return results


def create_jd_analysis_table(conn) -> None:
    """创建 JD 深度分析表。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jd_deep_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            function_category TEXT,
            function_confidence REAL,
            tech_density REAL,
            tech_keywords_count INTEGER,
            top_tech_keywords TEXT,
            jd_structure_score INTEGER,
            expected_education TEXT,
            expected_experience TEXT,
            english_required TEXT,
            management_required TEXT,
            oss_participation TEXT,
            has_responsibilities BOOLEAN,
            has_requirements BOOLEAN,
            has_benefits BOOLEAN,
            has_preferred BOOLEAN,
            responsibility_count INTEGER,
            requirement_count INTEGER,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jd_analysis_job ON jd_deep_analysis(job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jd_analysis_func ON jd_deep_analysis(function_category)")
    conn.commit()


def insert_jd_analysis(conn, results: List[JDAnalysisResult]) -> int:
    """批量插入 JD 分析结果。"""
    rows = [
        (
            r.job_id, r.function_category, r.function_confidence,
            r.tech_density, r.tech_keywords_count, r.top_tech_keywords,
            r.jd_structure_score, r.expected_education, r.expected_experience,
            r.english_required, r.management_required, r.oss_participation,
            r.has_responsibilities, r.has_requirements, r.has_benefits,
            r.has_preferred, r.responsibility_count, r.requirement_count,
        )
        for r in results
    ]

    conn.executemany("""
        INSERT OR REPLACE INTO jd_deep_analysis (
            job_id, function_category, function_confidence,
            tech_density, tech_keywords_count, top_tech_keywords,
            jd_structure_score, expected_education, expected_experience,
            english_required, management_required, oss_participation,
            has_responsibilities, has_requirements, has_benefits,
            has_preferred, responsibility_count, requirement_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)

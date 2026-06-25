"""
LLM 增强分析引擎 — 编码 AI 专家判断规则，批量结构化评估岗位。

分析维度：
  - position_level: 职级推断
  - tech_relevance: 技术栈现代程度 (1-10)
  - salary_competitiveness: 薪资竞争力 (low/medium/high)
  - growth_potential: 成长潜力 (1-10)
  - role_clarity: JD 描述质量 (1-10)
  - recommendation_score: 综合推荐指数 (1-10)
  - one_line_comment: AI 生成的评估摘要
"""

from __future__ import annotations

import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any


# ═══════════════════════════════════════
# 职级推断规则 — 精细化版本 (IC + 管理双轨制)
# ═══════════════════════════════════════

# 管理轨道职级（M 系列）
MGMT_PATTERNS: Dict[int, List[Tuple[str, int]]] = {
    8: [  # C-Level / VP
        (r'\b(CEO|CTO|CIO|CDO|CSO|COO|CFO)\b', 10),
        (r'\b(VP|副总裁|首席\s*\S+官|首席科学家)\b', 9),
        (r'\b(合伙人|Partner|执行董事|Managing\s*Director)\b', 9),
    ],
    7: [  # 总监/Head
        (r'\b(Director|总监|部门总经理)\b', 8),
        (r'\b(Head\s+of|负责人\(部门\)|研发总经理)\b', 7),
        (r'\b(技术委员会|技术VP)\b', 8),
    ],
    6: [  # 经理/Team Lead
        (r'\b(Manager|经理)\b', 6),
        (r'\b(Tech\s*Lead|Team\s*Lead|技术组长|研发组长)\b', 5),
        (r'\b(项目主管|主管工程师|Engineering\s*Manager)\b', 6),
    ],
}

# 技术轨道职级（IC 系列）
IC_PATTERNS: Dict[int, List[Tuple[str, int]]] = {
    7: [  # 首席/杰出
        (r'\b(Distinguished\s*Engineer|Fellow|首席工程师)\b', 10),
        (r'\b(Principal\s*Engineer|首席架构师)\b', 10),
    ],
    6: [  # 资深/Staff
        (r'\b(Staff\s*Engineer|Staff\s*Scientist)\b', 8),
        (r'\b(Architect|架构师|技术专家)\b', 8),
        (r'\b(Senior\s*Lead|Sr\.?\s*Lead)\b', 7),
    ],
    5: [  # 高级工程师
        (r'\b(Senior|Sr\.?)\b(?!\s*Lead|\s*Manager)', 5),
        (r'\b(高级工程师|高级开发|高级算法|高级数据)\b', 5),
        (r'\b(Expert\s*Engineer|资深工程师|资深开发)\b', 6),
    ],
    4: [  # 中级工程师 (full)
        (r'\b(Engineer\s*[ⅡⅢ]|Engineer\s*[23])\b', 4),
        (r'\b(中级工程师|中级开发)\b', 4),
    ],
    3: [  # 初级工程师
        (r'\b(Engineer|Developer|Analyst|Scientist|Consultant|DevOps|SRE)\b', 3),
        (r'\b(工程师|开发工程师|程序员|算法工程师|数据工程师)\b', 3),
        (r'\b(Full\s*Stack|Backend|Frontend|Data\s+Engineer|AI\s+Engineer)\b', 3),
        (r'\b(产品经理|运营专员|UI设计师)\b', 3),
    ],
    2: [  # 助理/初级
        (r'\b(Junior|Associate|Jr\.?)\b', 2),
        (r'\b(初级工程师|助理工程师|实习工程师)\b', 2),
    ],
    1: [  # 实习/培训
        (r'\b(Intern|Trainee|Graduate)\b', 1),
        (r'\b(实习生|培训生|应届生|校招)\b', 1),
    ],
}

# 职级名称映射
LEVEL_NAMES: Dict[int, str] = {
    8: 'C-Level/VP',
    7: '总监/Staff',
    6: '经理/架构师',
    5: '高级工程师',
    4: '中级工程师(高阶)',
    3: '初中级工程师',
    2: '初级/助理',
    1: '实习/应届',
    0: '未分类',
}

LEVEL_TRACKS: Dict[int, str] = {
    8: '管理', 7: '管理/技术', 6: '管理/技术',
    5: '技术', 4: '技术', 3: '技术', 2: '技术', 1: '技术',
    0: '未知',
}


def infer_position_level(title: str, experience: Optional[str] = None) -> int:
    """
    从职位名称和经验要求推断精细化职级 (1-8)。
    双轨制: 管理轨道 (M) vs 技术轨道 (IC)。
    """
    if not title:
        return 0

    title_lower = title.lower()
    best_level = 0
    best_confidence = 0

    # 先查管理轨道
    for level, patterns in MGMT_PATTERNS.items():
        for pat, conf in patterns:
            if re.search(pat, title_lower):
                if conf > best_confidence:
                    best_level = level
                    best_confidence = conf

    # 再查技术轨道（IC 优先时可能覆盖）
    for level, patterns in IC_PATTERNS.items():
        for pat, conf in patterns:
            if re.search(pat, title_lower):
                if conf >= best_confidence:  # IC 优先级略高于管理（大部分是IC岗位）
                    best_level = level
                    best_confidence = conf

    if best_level == 0:
        best_level = 3  # 默认初中级

    # 经验年限校正
    years = extract_experience_years(experience) if experience else 0
    if years > 0:
        if years >= 10 and best_level < 7:
            best_level = max(best_level, 6)
        elif years >= 8 and best_level < 6:
            best_level = max(best_level, 5)
        elif years >= 5 and best_level < 5:
            best_level = max(best_level, 4)
        elif years >= 3 and best_level < 4:
            best_level = max(best_level, 3)
        elif years >= 1 and best_level < 3:
            best_level = max(best_level, 2)

    return best_level


def extract_experience_years(exp_text: Optional[str]) -> float:
    """从经验文本提取年数。"""
    if not exp_text:
        return 0
    m = re.search(r'(\d+)[-~至到]*(\d+)?\s*年', str(exp_text))
    if m:
        if m.group(2):
            return (int(m.group(1)) + int(m.group(2))) / 2
        return float(m.group(1))
    # "无需经验" / "应届生"
    if re.search(r'(无需|不限|应届)', str(exp_text)):
        return 0
    return 0


# ═══════════════════════════════════════
# 技术现代度评分
# ═══════════════════════════════════════

CUTTING_EDGE_TECH = {
    r'\b(LLM|大模型|GPT|ChatGPT|Claude|Gemini|生成式)\b': 3,
    r'\b(Agent|Agentic|RAG|向量数据库|Vector\s*DB|LangChain|LlamaIndex)\b': 3,
    r'\b(TensorFlow|PyTorch|JAX|DeepSpeed|CUDA)\b': 3,
    r'\b(Kubernetes|K8s|Docker|Terraform|Helm)\b': 2,
    r'\b(Go|Golang|Rust|TypeScript)\b': 2,
    r'\b(Microservice|微服务|Service\s*Mesh|Istio|gRPC)\b': 2,
    r'\b(React|Vue\.?js|Next\.?js|Svelte|Tailwind)\b': 2,
    r'\b(Real[\s-]*time|WebSocket|流式|Streaming)\b': 2,
    r'\b(MCP|工具调用|Function\s*Calling)\b': 3,
    r'\b(MLOps|Kubeflow|MLflow|Feature\s*Store)\b': 2,
    r'\b(具身智能|Embodied|机器人|Robotics|ROS)\b': 3,
    r'\b(自动驾驶|Autonomous|Perception|点云|LiDAR)\b': 2,
}

MODERN_TECH = {
    r'\b(Python|FastAPI|Django|Flask)\b': 1,
    r'\b(Java|Spring\s*Boot|Spring\s*Cloud|MyBatis)\b': 1,
    r'\b(Redis|MongoDB|PostgreSQL|Kafka|RabbitMQ|Elasticsearch)\b': 1,
    r'\b(Linux|Git|CI\s*/\s*CD|Jenkins|GitHub\s*Actions)\b': 1,
    r'\b(AWS|Azure|GCP|阿里云|腾讯云|华为云)\b': 1,
    r'\b(AI|人工智能|机器学习|深度学习|数据科学|Data\s*Science)\b': 1,
    r'\b(Angular|Flutter|React\s*Native|小程序)\b': 1,
    r'\b(Spark|Hadoop|Flink|数仓|Data\s*Lake)\b': 1,
    r'\b(Cyber[\s-]*Security|安全|渗透|零信任)\b': 1,
    r'\b(区块链|Web3|Solidity|智能合约)\b': 1,
}

LEGACY_TECH = {
    r'\b(jQuery|PHP|ASP\.?NET|VB\.?NET)\b': -2,
    r'\b(Struts|Hibernate[^a-zA-Z]|JSP)\b': -2,
    r'\b(COBOL|Delphi|FoxPro|VB6)\b': -3,
    r'\b(IIS|Tomcat[^a-zA-Z]|WebLogic)\b': -1,
}


def score_tech_relevance(title: str, skills: Optional[str], description: Optional[str]) -> int:
    """
    评估技术栈现代度和市场需求热度。
    返回 1-10 分。
    """
    score = 5  # 基准分
    text = f"{title or ''} {skills or ''} {description or ''}".lower()

    for pattern, points in CUTTING_EDGE_TECH.items():
        if re.search(pattern, text):
            score += points

    for pattern, points in MODERN_TECH.items():
        if re.search(pattern, text):
            score += points

    for pattern, points in LEGACY_TECH.items():
        if re.search(pattern, text):
            score += points

    # 技能数量 bonus
    if skills:
        skill_count = len([s.strip() for s in skills.split(',') if s.strip()])
        if skill_count >= 8:
            score += 1
        elif skill_count >= 5:
            score += 0.5

    # 有AI/ML方向额外加权
    ai_keywords = r'\b(AI|Agent|LLM|大模型|RAG|机器学习|深度学习|NLP|CV|PyTorch|TensorFlow)\b'
    if re.search(ai_keywords, text):
        score += 1

    return max(1, min(10, round(score)))


# ═══════════════════════════════════════
# 薪资竞争力评估
# ═══════════════════════════════════════

# 各城市基准月薪（中级水平，单位：元）
CITY_BASELINE: Dict[str, float] = {
    '北京': 25000, '上海': 28000, '深圳': 26000, '广州': 20000,
    '杭州': 22000, '成都': 16000, '南京': 18000, '武汉': 15000,
    '西安': 14000, '重庆': 14000, '苏州': 18000, '长沙': 14000,
    '天津': 16000, '合肥': 15000, '厦门': 16000, '福州': 14000,
    '济南': 13000, '青岛': 14000, '郑州': 12000, '大连': 13000,
}

# 职级薪资倍率
LEVEL_MULTIPLIER = {5: 2.5, 4: 1.8, 3: 1.0, 2: 0.6, 1: 1.0}

# 公司类型薪资因子（更新以匹配精细化分类）
COMPANY_TYPE_FACTOR: Dict[str, float] = {
    '互联网大厂': 1.5, '知名外企': 1.4, '独角兽/明星创业': 1.3,
    '国企/央企': 0.9, '超大型企业': 1.2, '大型上市公司': 1.2,
    '大型企业(5000+)': 1.1, '大型企业(1000+)': 1.05, '大型成长企业(1000+)': 1.2,
    '大型上市公司(1000+)': 1.15,
    '中大型创业(500+,后期)': 1.1, '中型创业(500+,融资中)': 1.05,
    '中型上市公司(500+)': 1.0, '中型企业(500+)': 0.95,
    '成长型创业(100-500,后期)': 1.0, '早期创业(100-500,融资中)': 0.95,
    '中小企业(100-500)': 0.85,
    '初创公司(<100,有融资)': 0.9, '微型企业(<100)': 0.7,
    '金融上市公司': 1.1, '科技上市公司': 1.15, '医药上市公司': 1.1, '制造上市公司': 0.95,
    '上市公司': 1.05, '创业公司(后期融资)': 1.0, '成长型创业': 0.95,
    'AI创业(后期)': 1.15,
    '金融企业': 1.0, '教育/培训机构': 0.75, '医疗/医药企业': 0.95,
    '制造企业': 0.85, '房地产/建筑': 0.8, '外包/咨询公司': 0.7,
    '零售/电商': 0.85, '科技中小企业': 0.9,
    '中型企业': 0.85, '中小企业': 0.75, '未知': 1.0,
}


def infer_company_type(company_name: str, company_size: Optional[str],
                       financing_stage: Optional[str], industry: Optional[str]) -> str:
    """
    多信号公司类型推断（精细化版本）。

    信号优先级: company_name 关键词 > company_size 数值 > financing_stage > industry

    分类体系:
      - 互联网大厂 (BAT/HW/Bytedance/一线)
      - 知名外企 (Fortune 500/知名科技外企)
      - 独角兽/明星创业 (已知高估值创业公司)
      - 国企/央企
      - 超大型企业 (10000+)
      - 大型企业 (1000+)
      - 中型企业 (500+)
      - 中小企业 (100+)
      - 初创公司 (<100)
      - 上市公司/金融/制造等行业细分
    """
    if not company_name:
        return '未知'

    name = company_name.strip()

    # ── 一级信号: 公司名关键词匹配 ──

    big_tech = re.search(
        r'(华为|腾讯|阿里|百度|字节|美团|京东|网易|拼多多|小米|vivo|OPPO'
        r'|蚂蚁|滴滴|快手|哔哩哔哩|B站|携程|贝壳|小红书|得物|SHEIN'
        r'|理想汽车|蔚来|小鹏|比亚迪|大疆|商汤|旷视|依图|第四范式'
        r'|寒武纪|海康威视|深信服|奇安信|360)', name
    )
    if big_tech:
        return '互联网大厂'

    foreign_big = re.search(
        r'(微软|谷歌|Apple|苹果|IBM|Intel|SAP|Oracle|Cisco|Amazon'
        r'|HP|Dell|VMware|Red\.?Hat|SUSE|Canonical'
        r'|西门子|博世|大众|奔驰|宝马|奥迪|特斯拉|Toyota'
        r'|三星|索尼|松下|爱立信|诺基亚|Nokia|Ericsson'
        r'|高通|NVIDIA|AMD|ARM|Synopsys|Cadence'
        r'|辉瑞|罗氏|诺华|拜耳|强生|默克|GSK|赛诺菲'
        r'|埃森哲|McKinsey|BCG|Bain|Deloitte|PwC|KPMG|EY'
        r'|摩根|高盛|花旗|汇丰|HSBC|渣打|Standard\s*Chartered'
        r'|PayPal|Stripe|Shopify|Atlassian|Spotify'
        r'|霍尼韦尔|施耐德|ABB|GE|飞利浦|Philips)', name
    )
    if foreign_big:
        return '知名外企'

    unicorn = re.search(
        r'(米哈游|莉莉丝|鹰角|叠纸|库洛|FunPlus|沐瞳'
        r'|壁仞|摩尔线程|燧原|瀚博|天数智芯|昆仑芯'
        r'|智谱|月之暗面|Minimax|百川|零一万物|阶跃星辰'
        r'|Dark\s*Side|深度求索|面壁智能|生数科技'
        r'|元戎启行|文远知行|小马智行|Momenta|地平线'
        r'|禾赛|速腾|图森|千挂|安途|轻舟'
        r'|智元|宇树|傅利叶|达闼|银河通用'
        r'|黑芝麻|芯驰|芯擎|奕斯伟|长江存储|长鑫存储'
        r'|极氪|阿维塔|集度|禾多|Nullmax)', name
    )
    if unicorn:
        return '独角兽/明星创业'

    state_owned = re.search(
        r'(中国\s*(移动|联通|电信|石油|石化|海油|烟草|铁路|航天'
        r'|兵器|船舶|电子|核工业|建筑|中车|中铁|中交|中化|中粮'
        r'|国电|华能|大唐|华电|国家电网|南方电网|国家能源'
        r'|工商银行|建设银行|农业银行|中国银行|交通银行|邮储银行'
        r'|中国人寿|中国人保|中信|光大|招商局'
        r'|中科院|航天科工|航天科技|电子科技|中国电科'
        r'|中航|中国商飞|航空工业))', name
    )
    state_suffix = re.search(r'(研究所|研究院|集团).*(有限公司|有限责任)', name)
    if state_owned:
        return '国企/央企'
    if state_suffix and industry and re.search(r'(航天|航空|军工|国防|能源|电力|通信|铁路)', industry):
        return '国企/央企'

    listed = bool(re.search(r'(股份|控股|上市|股份有限)', name))

    # ── 二级信号: 公司规模数值解析 ──
    employee_count = 0
    if company_size:
        size_matches = [
            (r'(\d+)\s*万\s*人以上', lambda m: int(m.group(1)) * 10000),
            (r'(\d{3,5})\s*[-~至]\s*(\d{3,5})\s*人', lambda m: (int(m.group(1)) + int(m.group(2))) // 2),
            (r'(\d+)\s*[-~至]\s*(\d+)\s*人', lambda m: (int(m.group(1)) + int(m.group(2))) // 2),
            (r'(\d+)\s*人以上', lambda m: int(m.group(1)) * 1.5),
            (r'少于\s*(\d+)\s*人', lambda m: int(m.group(1)) // 2),
        ]
        for pattern, extractor in size_matches:
            m = re.search(pattern, company_size)
            if m:
                employee_count = extractor(m)
                break

    # ── 三级信号: 融资阶段 ──
    has_funding = False
    late_stage = False
    if financing_stage:
        fs = financing_stage.strip()
        if fs and fs not in ('不需要融资', '未融资'):
            has_funding = True
            if re.search(r'(D轮|E轮|F轮|Pre[-\s]*IPO|战略投资|IPO)', fs):
                late_stage = True

    # ── 综合判断 ──
    if employee_count >= 10000:
        cls = '大型上市公司' if listed else '超大型企业'
        return cls

    if employee_count >= 5000:
        return '大型企业(5000+)'

    if employee_count >= 1000:
        if has_funding:
            return '大型成长企业(1000+)'
        if listed:
            return '大型上市公司(1000+)'
        return '大型企业(1000+)'

    if employee_count >= 500:
        if late_stage:
            return '中大型创业(500+,后期)'
        if has_funding:
            return '中型创业(500+,融资中)'
        if listed:
            return '中型上市公司(500+)'
        return '中型企业(500+)'

    if employee_count >= 100:
        if late_stage:
            return '成长型创业(100-500,后期)'
        if has_funding:
            return '早期创业(100-500,融资中)'
        return '中小企业(100-500)'

    if employee_count > 0:
        if has_funding:
            return '初创公司(<100,有融资)'
        return '微型企业(<100)'

    # 无员工数时的推断
    if listed:
        if industry:
            for kw, label in [('金融|银行|保险|证券', '金融上市公司'),
                               ('互联网|软件|IT|科技|信息', '科技上市公司'),
                               ('制药|医药|生物|医疗器械', '医药上市公司'),
                               ('制造|汽车|电子|半导体', '制造上市公司')]:
                if re.search(kw, industry):
                    return label
        return '上市公司'

    if late_stage:
        return 'AI创业(后期)' if (industry and re.search(r'(AI|人工智能|大模型)', industry)) else '创业公司(后期融资)'
    if has_funding:
        return '成长型创业'

    if industry:
        for kw, label in [('金融|银行|保险|证券', '金融企业'),
                           ('教育|培训', '教育/培训机构'),
                           ('医疗|医药|生物|医院', '医疗/医药企业'),
                           ('制造|汽车|机械|电子', '制造企业'),
                           ('房地产|物业|建筑', '房地产/建筑'),
                           ('外包|人力资源|咨询', '外包/咨询公司'),
                           ('零售|电商|贸易', '零售/电商'),
                           ('互联网|软件|IT|科技|信息', '科技中小企业')]:
            if re.search(kw, industry):
                return label

    return '中型企业' if len(name) > 15 else '中小企业'


def score_salary_competitiveness(salary_avg: Optional[float], city: str,
                                  level: int, company_type: str,
                                  salary_months: Optional[int]) -> Tuple[str, str]:
    """
    评估薪资竞争力。
    返回 (low/medium/high, 理由)。
    """
    if not salary_avg or salary_avg <= 0 or not city:
        return 'low', '薪资数据缺失或异常，无法评估竞争力'

    baseline = CITY_BASELINE.get(city, 16000)
    expected = baseline * LEVEL_MULTIPLIER.get(level, 1.0)
    company_factor = COMPANY_TYPE_FACTOR.get(company_type, 1.0)
    expected *= company_factor

    # 年化月薪（考虑月份数）
    effective_salary = salary_avg
    if salary_months and salary_months > 12:
        effective_salary = salary_avg * salary_months / 12

    ratio = effective_salary / expected if expected > 0 else 0

    if ratio > 1.5:
        return 'high', f'月薪¥{effective_salary:,.0f}远超{city}{company_type}同级别预期¥{expected:,.0f}（{ratio:.1f}倍）'
    elif ratio > 1.15:
        return 'high', f'月薪¥{effective_salary:,.0f}高于{city}市场水平¥{expected:,.0f}（+{int((ratio-1)*100)}%）'
    elif ratio >= 0.85:
        return 'medium', f'月薪¥{effective_salary:,.0f}处于{city}合理区间（基准¥{expected:,.0f}）'
    elif ratio >= 0.7:
        return 'medium', f'月薪¥{effective_salary:,.0f}略低于{city}水平¥{expected:,.0f}，但仍在可接受范围'
    else:
        return 'low', f'月薪¥{effective_salary:,.0f}明显低于{city}市场水平¥{expected:,.0f}（-{int((1-ratio)*100)}%）'


# ═══════════════════════════════════════
# 成长潜力评估
# ═══════════════════════════════════════


def score_growth_potential(title: str, skills: Optional[str], industry: Optional[str],
                            company_type: str, description: Optional[str]) -> int:
    """
    评估岗位的成长潜力 (1-10)。
    """
    score = 5
    text = f"{title or ''} {skills or ''} {industry or ''} {description or ''}".lower()

    # AI/前沿技术方向
    if re.search(r'\b(AI|Agent|LLM|大模型|RAG|机器学习|深度学习|生成式|NLP|CV|PyTorch|LangChain)\b', text):
        score += 2

    # 赛道溢价
    hot_industries = [
        (r'(人工智能|AI|机器学习|大数据)', 2),
        (r'(新能源|光伏|储能|电池|电动汽车)', 1.5),
        (r'(半导体|芯片|集成电路|EDA)', 2),
        (r'(量子|航天|卫星|低空)', 2),
        (r'(金融科技|量化|Fintech)', 1.5),
        (r'(生物医药|基因|药物|CXO)', 1.5),
        (r'(自动驾驶|智能驾驶|ADAS)', 2),
        (r'(机器人|具身智能|自动化)', 2),
        (r'(云原生|SaaS|云计算|边缘计算)', 1),
        (r'(网络安全|信息安全|数据安全)', 1),
    ]
    for pattern, points in hot_industries:
        if re.search(pattern, text):
            score += points
            break  # 只取最高

    # 公司类型
    if company_type == '初创':
        score += 1  # 股权潜力
    elif company_type == '互联网大厂':
        score += 0.5

    # 管理/架构角色
    if re.search(r'(Lead|Manager|管理|架构|Architect|负责人|总监|Team\s*Lead)', title.lower() if title else ''):
        score += 0.5

    return max(1, min(10, round(score)))


# ═══════════════════════════════════════
# JD 描述质量
# ═══════════════════════════════════════


def score_role_clarity(description: Optional[str], skills: Optional[str]) -> int:
    """评估 JD 描述质量和完整度 (1-10)。"""
    score = 3  # 基准

    if description and len(description) > 50:
        desc_len = len(description)
        if desc_len > 2000:
            score += 3
        elif desc_len > 1000:
            score += 2
        elif desc_len > 500:
            score += 1.5
        elif desc_len > 200:
            score += 1

        # 职责描述完整性
        if re.search(r'(职责|Responsibilit|负责|岗位职责|Job\s*Description)', description):
            score += 1
        if re.search(r'(要求|Require|Qualification|任职|技能)', description):
            score += 1
        if re.search(r'(团队|Team|福利|Benefit|发展|晋升)', description):
            score += 0.5

    if skills and len(skills) > 10:
        score += 1

    return max(1, min(10, round(score)))


# ═══════════════════════════════════════
# 综合推荐指数
# ═══════════════════════════════════════


def compute_recommendation(tech_score: int, salary_level: str,
                            growth_score: int, clarity_score: int) -> int:
    """加权综合推荐指数 (1-10)。"""
    salary_weight = {'high': 3, 'medium': 2, 'low': 1}

    raw = (
        tech_score * 0.30 +
        salary_weight.get(salary_level, 2) * 0.30 * 3.33 +  # 映射到 1-10
        growth_score * 0.25 +
        clarity_score * 0.15
    )
    return max(1, min(10, round(raw)))


# ═══════════════════════════════════════
# AI 一句话评价生成
# ═══════════════════════════════════════


def generate_one_line_comment(title: str, company_name: str, city: str,
                               level: int, tech_score: int, salary_level: str,
                               growth_score: int, company_type: str,
                               skills: Optional[str]) -> str:
    """
    基于多维度分析结果，生成自然语言评价。
    """
    level_name = LEVEL_NAMES.get(level, '未分类')
    tech_tier = '前沿' if tech_score >= 8 else '现代' if tech_score >= 6 else '传统' if tech_score >= 4 else '过时'

    # 技能摘要
    skill_summary = ''
    if skills:
        top_skills = [s.strip() for s in skills.split(',') if s.strip()][:3]
        if top_skills:
            skill_summary = f"主打{'+'.join(top_skills[:2])}"

    # 薪资评价
    salary_desc = {
        'high': f'薪资在{city}具有极强竞争力',
        'medium': f'薪资处于{city}合理水平',
        'low': f'薪资低于{city}市场水平',
    }.get(salary_level, '薪资待评估')

    # 成长评价
    if growth_score >= 8:
        growth_desc = '成长潜力极高'
    elif growth_score >= 6:
        growth_desc = '有较好发展空间'
    elif growth_score >= 4:
        growth_desc = '发展空间一般'
    else:
        growth_desc = '成长天花板明显'

    # 综合评价
    if tech_score >= 8 and salary_level == 'high':
        verdict = '强烈推荐，高薪+前沿技术'
    elif tech_score >= 7 and salary_level in ('high', 'medium'):
        verdict = '推荐，技术方向良好+薪资合理'
    elif tech_score >= 6:
        verdict = '中规中矩，适合稳定发展'
    elif tech_score >= 4:
        verdict = '性价比较低，仅作过渡选择'
    else:
        verdict = '技术栈过时，谨慎考虑'

    comment = f"{city}·{company_type}·{level_name}·{tech_tier}技术栈。{skill_summary}。{salary_desc}，{growth_desc}。{verdict}"
    return comment


# ═══════════════════════════════════════
# 批量分析引擎
# ═══════════════════════════════════════


@dataclass
@dataclass
class AnalysisResult:
    """单条分析结果。"""
    job_id: int
    position_level: int
    position_level_name: str
    position_track: str  # '管理' / '技术' / '未知'
    tech_relevance: int
    salary_competitiveness: str
    salary_competitiveness_reason: str
    company_type: str
    growth_potential: int
    role_clarity: int
    recommendation_score: int
    one_line_comment: str
    salary_baseline: float
    salary_ratio: float


def analyze_job(job: Dict[str, Any], city_baselines: Optional[Dict[str, float]] = None) -> AnalysisResult:
    """
    对单条岗位数据进行全方位分析。
    """
    if city_baselines:
        global CITY_BASELINE
        CITY_BASELINE.update(city_baselines)

    job_id = job['id']
    title = job.get('title', '') or ''
    company_name = job.get('company_name', '') or ''
    city = job.get('city', '') or ''
    salary_avg = job.get('salary_avg')
    salary_months = job.get('salary_months')
    experience = job.get('experience')
    skills = job.get('skills')
    description = job.get('description')
    industry = job.get('industry')
    company_size = job.get('company_size')
    financing_stage = job.get('financing_stage')

    # 逐个维度分析
    level = infer_position_level(title, experience)
    tech_score = score_tech_relevance(title, skills, description)
    company_type = infer_company_type(company_name, company_size, financing_stage, industry)
    salary_level, salary_reason = score_salary_competitiveness(
        salary_avg, city, level, company_type, salary_months
    )
    growth_score = score_growth_potential(title, skills, industry, company_type, description)
    clarity_score = score_role_clarity(description, skills)
    rec_score = compute_recommendation(tech_score, salary_level, growth_score, clarity_score)
    comment = generate_one_line_comment(
        title, company_name, city, level, tech_score,
        salary_level, growth_score, company_type, skills
    )

    baseline = CITY_BASELINE.get(city, 16000) * LEVEL_MULTIPLIER.get(level, 1.0)
    ratio = salary_avg / baseline if salary_avg and salary_avg > 0 and baseline > 0 else 0

    track = LEVEL_TRACKS.get(level, '未知')

    return AnalysisResult(
        job_id=job_id,
        position_level=level,
        position_level_name=LEVEL_NAMES.get(level, '未分类'),
        position_track=track,
        tech_relevance=tech_score,
        salary_competitiveness=salary_level,
        salary_competitiveness_reason=salary_reason,
        company_type=company_type,
        growth_potential=growth_score,
        role_clarity=clarity_score,
        recommendation_score=rec_score,
        one_line_comment=comment,
        salary_baseline=round(baseline, 0),
        salary_ratio=round(ratio, 3),
    )


def batch_analyze(conn: sqlite3.Connection, limit: Optional[int] = None,
                   city_filter: Optional[str] = None) -> List[AnalysisResult]:
    """
    批量分析数据库中所有岗位（或指定数量）。
    """
    query = "SELECT * FROM jobs WHERE 1=1"
    params: List[Any] = []

    if city_filter:
        query += " AND city = ?"
        params.append(city_filter)

    if limit:
        query += f" LIMIT {limit}"

    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, params)

    results = []
    count = 0
    for row in cursor:
        try:
            job = dict(row)
            result = analyze_job(job)
            results.append(result)
            count += 1
            if count % 500 == 0:
                print(f"    已分析 {count} 条...")
        except Exception as e:
            print(f"  ⚠  job_id={row['id']} 分析失败: {e}")

    conn.row_factory = None
    return results


def create_analysis_table(conn: sqlite3.Connection) -> None:
    """创建分析结果表。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_analysis_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            position_level INTEGER,
            position_level_name TEXT,
            position_track TEXT,
            tech_relevance INTEGER,
            salary_competitiveness TEXT,
            salary_competitiveness_reason TEXT,
            company_type TEXT,
            growth_potential INTEGER,
            role_clarity INTEGER,
            recommendation_score INTEGER,
            one_line_comment TEXT,
            salary_baseline REAL,
            salary_ratio REAL,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_job_id ON llm_analysis_batch(job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_city ON llm_analysis_batch(company_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_rec ON llm_analysis_batch(recommendation_score)")
    conn.commit()


def insert_results(conn: sqlite3.Connection, results: List[AnalysisResult]) -> int:
    """批量插入分析结果（REPLACE 避免重复）。"""
    rows = [
        (
            r.job_id, r.position_level, r.position_level_name,
            r.position_track,
            r.tech_relevance, r.salary_competitiveness,
            r.salary_competitiveness_reason, r.company_type,
            r.growth_potential, r.role_clarity,
            r.recommendation_score, r.one_line_comment,
            r.salary_baseline, r.salary_ratio,
        )
        for r in results
    ]

    conn.executemany("""
        INSERT OR REPLACE INTO llm_analysis_batch (
            job_id, position_level, position_level_name,
            position_track,
            tech_relevance, salary_competitiveness,
            salary_competitiveness_reason, company_type,
            growth_potential, role_clarity,
            recommendation_score, one_line_comment,
            salary_baseline, salary_ratio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    return len(rows)

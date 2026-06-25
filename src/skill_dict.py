"""技能关键词字典 — 子串匹配用。

extract_skills() 遍历此列表，在岗位标题 / 技能标签 / 描述文本中做子串匹配。
匹配时大小写不敏感（.lower() 后匹配）。

添加新技能：直接在列表末尾追加字符串即可。
"""

SKILL_KEYWORDS = [
    "Python",
    "Java",
    "Go",
    "C++",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Node.js",
    "Spring Boot",
    "Django",
    "FastAPI",
    "Flask",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "MongoDB",
    "Docker",
    "Kubernetes",
    "Linux",
    "SQL",
    "Excel",
    "Power BI",
    "Tableau",
    "机器学习",
    "深度学习",
    "数据分析",
    "数据可视化",
    "A/B测试",
    "用户增长",
    "电商运营",
    "内容运营",
    "项目管理",
    "需求分析",
    "原型设计",
    "Figma",
    "Photoshop",
    "销售",
    "客户沟通",
    "渠道拓展",
]


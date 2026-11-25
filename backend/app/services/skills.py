"""Skill taxonomy used for normalization, heuristic extraction and heuristic matching."""

import re

# canonical name -> (category, aliases). Aliases are matched with word boundaries, case-insensitive.
SKILLS: dict[str, tuple[str, list[str]]] = {
    "Python": ("language", ["python", "بايثون"]),
    "JavaScript": ("language", ["javascript", "js", "ecmascript", "جافاسكربت"]),
    "TypeScript": ("language", ["typescript", "ts"]),
    "Java": ("language", ["java", "جافا"]),
    "C#": ("language", ["c#", "csharp"]),
    "C++": ("language", ["c++", "cpp"]),
    "Go": ("language", ["golang"]),
    "Kotlin": ("language", ["kotlin"]),
    "PHP": ("language", ["php"]),
    "SQL": ("data", ["sql", "t-sql", "pl/sql"]),
    "HTML": ("frontend", ["html", "html5"]),
    "CSS": ("frontend", ["css", "css3"]),
    "React": ("frontend", ["react", "react.js", "reactjs"]),
    "Next.js": ("frontend", ["next.js", "nextjs", "next js"]),
    "Angular": ("frontend", ["angular"]),
    "Vue.js": ("frontend", ["vue", "vue.js", "vuejs"]),
    "Tailwind CSS": ("frontend", ["tailwind", "tailwindcss", "tailwind css"]),
    "Node.js": ("backend", ["node.js", "nodejs", "node js"]),
    "Express": ("backend", ["express.js", "expressjs"]),
    "FastAPI": ("backend", ["fastapi"]),
    "Django": ("backend", ["django"]),
    "Flask": ("backend", ["flask"]),
    "Spring Boot": ("backend", ["spring boot", "spring"]),
    ".NET": ("backend", [".net", "asp.net", "dotnet"]),
    "REST APIs": ("backend", ["rest", "restful", "rest api", "rest apis", "restful api", "restful apis"]),
    "GraphQL": ("backend", ["graphql"]),
    "Microservices": ("backend", ["microservices", "micro-services"]),
    "Backend Development": ("backend", ["backend", "back-end", "back end", "server-side"]),
    "PostgreSQL": ("data", ["postgresql", "postgres"]),
    "MySQL": ("data", ["mysql"]),
    "SQL Server": ("data", ["sql server", "mssql"]),
    "Oracle Database": ("data", ["oracle database", "oracle db"]),
    "MongoDB": ("data", ["mongodb", "mongo"]),
    "Redis": ("data", ["redis"]),
    "Data Engineering": ("data", ["data engineering", "data pipelines", "data pipeline", "هندسة البيانات"]),
    "ETL": ("data", ["etl", "elt"]),
    "Data Analysis": ("data", ["data analysis", "data analytics", "تحليل البيانات"]),
    "Data Warehousing": ("data", ["data warehouse", "data warehousing", "snowflake", "bigquery", "redshift"]),
    "Apache Airflow": ("data", ["airflow"]),
    "Apache Spark": ("data", ["spark", "pyspark"]),
    "Kafka": ("data", ["kafka"]),
    "dbt": ("data", ["dbt"]),
    "Pandas": ("data", ["pandas"]),
    "NumPy": ("data", ["numpy"]),
    "Power BI": ("data", ["power bi", "powerbi"]),
    "Tableau": ("data", ["tableau"]),
    "Excel": ("tool", ["excel", "ms excel"]),
    "Statistics": ("data", ["statistics", "statistical"]),
    "Machine Learning": ("ai", ["machine learning", "ml", "تعلم الآلة"]),
    "Deep Learning": ("ai", ["deep learning"]),
    "NLP": ("ai", ["nlp", "natural language processing"]),
    "Computer Vision": ("ai", ["computer vision"]),
    "LLMs": ("ai", ["llm", "llms", "large language model", "large language models", "gpt", "generative ai", "genai"]),
    "AI Agents": ("ai", ["ai agents", "ai agent", "agentic", "autonomous agents"]),
    "AI Integration": ("ai", ["ai integration", "ai integrations", "openai api", "openai"]),
    "Artificial Intelligence": ("ai", ["artificial intelligence", "ai", "الذكاء الاصطناعي", "ذكاء اصطناعي"]),
    "LangChain": ("ai", ["langchain", "llamaindex"]),
    "RAG": ("ai", ["rag", "retrieval augmented generation", "retrieval-augmented generation"]),
    "PyTorch": ("ai", ["pytorch"]),
    "TensorFlow": ("ai", ["tensorflow", "keras"]),
    "scikit-learn": ("ai", ["scikit-learn", "sklearn"]),
    "MLOps": ("ai", ["mlops"]),
    "Docker": ("devops", ["docker", "containers"]),
    "Kubernetes": ("devops", ["kubernetes", "k8s"]),
    "AWS": ("devops", ["aws", "amazon web services"]),
    "Azure": ("devops", ["azure"]),
    "GCP": ("devops", ["gcp", "google cloud"]),
    "CI/CD": ("devops", ["ci/cd", "cicd", "continuous integration"]),
    "Git": ("tool", ["git", "github", "gitlab"]),
    "Linux": ("devops", ["linux", "unix"]),
    "ERP": ("business", ["erp", "enterprise resource planning", "تخطيط موارد المؤسسات"]),
    "SAP": ("business", ["sap", "s/4hana", "sap s/4hana"]),
    "Oracle ERP": ("business", ["oracle erp", "oracle fusion", "oracle ebs"]),
    "Odoo": ("business", ["odoo"]),
    "Microsoft Dynamics": ("business", ["dynamics 365", "microsoft dynamics", "d365"]),
    "Salesforce": ("business", ["salesforce", "crm"]),
    "Product Management": ("product", ["product management", "إدارة المنتجات", "ادارة المنتجات"]),
    "Product Roadmapping": ("product", ["roadmap", "roadmaps", "roadmapping"]),
    "User Research": ("product", ["user research", "customer research", "user interviews"]),
    "A/B Testing": ("product", ["a/b testing", "ab testing", "experimentation"]),
    "Product Analytics": ("product", ["product analytics", "mixpanel", "amplitude", "google analytics"]),
    "Agile": ("product", ["agile", "أجايل"]),
    "Scrum": ("product", ["scrum"]),
    "Jira": ("tool", ["jira", "confluence"]),
    "Figma": ("tool", ["figma"]),
    "Business Analysis": ("business", ["business analysis", "تحليل الأعمال"]),
    "Requirements Gathering": ("business", ["requirements gathering", "requirement gathering", "requirements analysis", "brd", "user stories"]),
    "Project Management": ("business", ["project management", "إدارة المشاريع", "pmp"]),
    "Digital Transformation": ("business", ["digital transformation", "التحول الرقمي"]),
    "Technical Consulting": ("business", ["technical consulting", "it consulting", "consulting"]),
    "Stakeholder Management": ("soft", ["stakeholder management", "stakeholders"]),
    "Communication": ("soft", ["communication skills", "communication"]),
    "Problem Solving": ("soft", ["problem solving", "problem-solving"]),
    "Teamwork": ("soft", ["teamwork", "collaboration"]),
    "Arabic": ("spoken_language", ["arabic", "العربية"]),
    "English": ("spoken_language", ["english", "الإنجليزية", "الانجليزية"]),
}

_ALIAS_INDEX: dict[str, str] = {}
for canon, (_, aliases) in SKILLS.items():
    _ALIAS_INDEX[canon.lower()] = canon
    for a in aliases:
        _ALIAS_INDEX[a.lower()] = canon

# Aliases that are too ambiguous for free-text scanning (still accepted for normalization)
_SCAN_EXCLUDE = {"js", "ts", "ai", "ml", "rest", "spring", "consulting", "communication", "crm", "containers", "git"}


def _pattern(alias: str) -> re.Pattern:
    return re.compile(r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])", re.IGNORECASE)


_SCAN_PATTERNS: list[tuple[re.Pattern, str]] = sorted(
    [(_pattern(a), c) for a, c in _ALIAS_INDEX.items() if a not in _SCAN_EXCLUDE],
    key=lambda pc: -len(pc[0].pattern),
)


def normalize_skill(name: str) -> str:
    """Return canonical skill name if known, else a cleaned version of the input."""
    key = re.sub(r"\s+", " ", name.strip()).lower()
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    return re.sub(r"\s+", " ", name.strip())


def normalized_key(name: str) -> str:
    return normalize_skill(name).lower()


def skill_category(name: str) -> str:
    canon = normalize_skill(name)
    return SKILLS.get(canon, ("technical", []))[0]


def extract_skills(text: str) -> list[str]:
    """Find known skills mentioned in free text (deterministic, no hallucination)."""
    if not text:
        return []
    found: dict[str, None] = {}
    for pat, canon in _SCAN_PATTERNS:
        if canon not in found and pat.search(text):
            found[canon] = None
    # 'Artificial Intelligence' via the plain token "AI" (uppercase only, to avoid noise)
    if "Artificial Intelligence" not in found and re.search(r"\bAI\b", text):
        found["Artificial Intelligence"] = None
    if "Machine Learning" not in found and re.search(r"\bML\b", text):
        found["Machine Learning"] = None
    return list(found)


def skill_in_text(skill: str, text: str) -> bool:
    """True if the skill (or one of its aliases) literally appears in the text."""
    if not text:
        return False
    canon = normalize_skill(skill)
    aliases = {skill.lower(), canon.lower()}
    if canon in SKILLS:
        aliases.update(a.lower() for a in SKILLS[canon][1])
    low = text.lower()
    for a in aliases:
        if len(a) <= 3:
            if re.search(r"(?<![\w+#.])" + re.escape(a) + r"(?![\w+#])", low):
                return True
        elif a in low:
            return True
    return False


# Skills that are close enough to count as transferable for heuristic matching.
RELATED: dict[str, set[str]] = {
    "PostgreSQL": {"MySQL", "SQL Server", "SQL", "Oracle Database"},
    "MySQL": {"PostgreSQL", "SQL", "SQL Server"},
    "SQL Server": {"PostgreSQL", "MySQL", "SQL"},
    "FastAPI": {"Django", "Flask", "REST APIs"},
    "Django": {"FastAPI", "Flask"},
    "Flask": {"FastAPI", "Django"},
    "React": {"Next.js", "Vue.js", "Angular"},
    "Next.js": {"React"},
    "Vue.js": {"React"},
    "Angular": {"React", "TypeScript"},
    "TypeScript": {"JavaScript"},
    "JavaScript": {"TypeScript"},
    "Node.js": {"JavaScript", "TypeScript", "Express"},
    "LLMs": {"AI Integration", "AI Agents", "NLP"},
    "AI Agents": {"LLMs", "AI Integration"},
    "Machine Learning": {"Data Analysis", "Python", "scikit-learn"},
    "Data Engineering": {"ETL", "SQL", "Python"},
    "ETL": {"Data Engineering"},
    "Power BI": {"Tableau", "Data Analysis"},
    "Tableau": {"Power BI", "Data Analysis"},
    "AWS": {"Azure", "GCP"},
    "Azure": {"AWS", "GCP"},
    "GCP": {"AWS", "Azure"},
    "Scrum": {"Agile"},
    "Agile": {"Scrum"},
    "Business Analysis": {"Requirements Gathering", "Data Analysis"},
    "Product Management": {"Product Roadmapping", "User Research", "Agile"},
    "SAP": {"ERP"},
    "Odoo": {"ERP"},
    "Oracle ERP": {"ERP"},
    "Microsoft Dynamics": {"ERP"},
    "Java": {"Kotlin", "C#"},
    "C#": {"Java", ".NET"},
    "Spring Boot": {"Java"},
}

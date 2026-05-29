# MedKB-AI API接口文档

> 版本: v1.0 | 更新日期: 2025-05-29

本文档定义MedKB-AI系统内部各模块间的数据接口格式，以及Python API的使用说明。

---

## 1. 数据接口规范

### 1.1 原始语料格式 (Corpus Input)

**路径**: `data/raw/*.json`

```json
[
  {
    "doc_id": "string (必需, 文档唯一标识)",
    "title": "string (必需, 文档标题)",
    "source_type": "string (NMPA药品说明书|PubMed文献摘要|临床诊疗指南|其他)",
    "url": "string (可选, 来源URL)",
    "language": "string (默认: zh)",
    "content": "string (必需, 原始文本内容)",
    "content_hash": "string (自动生成, SHA256前16位)",
    "word_count": "integer (自动计算, 字数)",
    "fetch_date": "string (自动填充, 采集日期 YYYY-MM-DD)"
  }
]
```

### 1.2 清洗后数据格式 (Cleaned Output)

**路径**: `data/cleaned/*.json`

```json
[
  {
    "doc_id": "string",
    "title": "string",
    "source_type": "string",
    "original_content": "string (清洗前的原始文本)",
    "content": "string (清洗后的规范文本)",
    "sentence_count": "integer (分句数量)",
    "sentences": ["string array (分句列表)"],
    "original_words": "integer",
    "cleaned_words": "integer",
    "words_removed": "integer",
    "cleaning_ratio": "string (如: '2.5%')",
    "quality_issues": ["string array (质量问题列表)"],
    "quality_score": "string (A|B|C)",
    "cleaned_at": "string (ISO datetime)"
  }
]
```

### 1.3 标注结果格式 (Annotation Output)

**路径**: `data/annotated/*.json`

```json
[
  {
    "doc_id": "string",
    "title": "string",
    "content": "string",
    "annotation": {
      "entities": {
        "drugs": [
          {
            "name": "string (药品标准通用名)",
            "english_name": "string",
            "category": "string (药品药理分类)",
            "mention_in_text": "string (原文中的原文表述)",
            "is_active_ingredient": "boolean"
          }
        ],
        "diseases": [
          {
            "name": "string (疾病标准名)",
            "english_name": "string",
            "category": "string (疾病分类或'症状')",
            "is_symptom": "boolean"
          }
        ],
        "adverse_effects": [
          {
            "name": "string (不良反应名称)",
            "body_system": "string (受累系统/器官)",
            "severity": "string (轻度|中度|重度)"
          }
        ],
        "contraindications": [
          {
            "condition": "string (禁忌条件)",
            "population": "string (禁忌人群)",
            "is_absolute": "boolean (是否绝对禁忌)"
          }
        ]
      },
      "relations": {
        "relations": [
          {
            "type": "string (indication|adverse_effect|contraindication|drug_interaction)",
            "from": "string (源实体名称)",
            "to": "string (目标实体名称)",
            "evidence": "string (原文证据句)",
            "confidence": "number (0.0-1.0)",
            "evidence_level": "string (A|B|C|D, 仅indication类型)",
            "is_first_line": "boolean (仅indication类型)"
          }
        ]
      },
      "metadata": {
        "strategy": "string (Few-shot|Chain-of-Thought|结构化JSON输出)",
        "strategy_key": "string (few_shot|cot|structured_json)",
        "model": "string (标注模型名称)",
        "api_success": "boolean",
        "mock_mode": "boolean",
        "tokens_in": "integer",
        "tokens_out": "integer",
        "duration_sec": "number",
        "annotated_at": "string (ISO datetime)"
      }
    }
  }
]
```

### 1.4 知识库查询接口

#### 药品查询
```
输入:  药品名称 (string, 支持模糊匹配)
输出:  {
  found: boolean,
  name: string,
  generic_name: string,
  category: string,
  indications: [{disease_name, evidence_level, is_first_line, usage_note}],
  adverse_effects: [{effect_name, frequency, severity, body_system}],
  drug_interactions: [{drug_b_name, interaction_type, mechanism, severity_level}]
}
```

#### 疾病查询
```
输入:  疾病名称 (string, 支持模糊匹配)
输出:  {
  found: boolean,
  name: string,
  category: string,
  drugs: [{drug_name, category, evidence_level, is_first_line}]
}
```

#### 相互作用查询
```
输入:  drug_a (string), drug_b (string)
输出:  {
  found: boolean,
  drug_a: string,
  drug_b: string,
  has_interaction: boolean,
  interaction: {interaction_type, mechanism, severity_level}
}
```

#### 全文搜索
```
输入:  keyword (string)
输出:  {
  keyword: string,
  drugs: [{name, category, description}],
  diseases: [{name, category, description}],
  adverse_effects: [{effect_name, drug_name}],
  total: integer
}
```

---

## 2. Python API

### 2.1 TextCleaner

```python
from cleaner import TextCleaner

# 初始化
cleaner = TextCleaner()

# 清洗文本
cleaned = cleaner.normalize_whitespace(text)
cleaned = cleaner.normalize_punctuation(cleaned)
cleaned = cleaner.remove_artifacts(cleaned)
cleaned = cleaner.normalize_medical_terms(cleaned)

# 分句
sentences = cleaner.split_sentences(cleaned)

# 质量检测
issues = cleaner.detect_quality_issues(cleaned)
```

### 2.2 AnnotationEngine

```python
from annotator import LLMClient, AnnotationEngine

# 初始化客户端
client = LLMClient(model="claude", api_key="sk-ant-xxx")

# 创建标注引擎
engine = AnnotationEngine(client=client, strategy="structured_json")

# 标注文档
result = engine.annotate_document(cleaned_doc)
```

### 2.3 KnowledgeBaseBuilder

```python
from kb_builder import KnowledgeBaseBuilder

builder = KnowledgeBaseBuilder(db_path="db/medkb.db")
builder.connect()
builder.init_schema()

# 从结构化数据构建
stats = builder.build_from_structured(data_dir="data/raw")

# 获取统计
db_stats = builder.get_statistics()

builder.close()
```

### 2.4 QueryEngine

```python
from query_engine import QueryEngine

engine = QueryEngine(db_path="db/medkb.db")
engine.connect()

# 查询药品
drug = engine.search_drug("阿司匹林")

# 查询疾病
disease = engine.search_disease("冠心病")

# 检查相互作用
interaction = engine.check_interaction("阿司匹林", "华法林")

# 全文搜索
results = engine.full_text_search("肝毒性")

# 统计
stats = engine.get_statistics()

engine.close()
```

### 2.5 QualityValidator

```python
from validator import QualityValidator

validator = QualityValidator(db_path="db/medkb.db")
validator.connect()

issues = validator.run_all_checks()
report = validator.generate_report()
validator.save_issues_to_db()

validator.close()
```

---

## 3. 命令行接口 (CLI) 完整参考

| 模块 | 命令 | 说明 |
|------|------|------|
| scraper | `python src/scraper.py [--source sample\|pubmed\|nmpa] [--output PATH]` | 语料采集 |
| cleaner | `python src/cleaner.py [--input PATH] [--output PATH]` | 数据清洗 |
| annotator | `python src/annotator.py [--model claude\|gpt\|mock] [--strategy few_shot\|cot\|structured_json] [--api-key KEY] [--max-docs N]` | LLM标注 |
| kb_builder | `python src/kb_builder.py [--input PATH\|--from-structured] [--db PATH]` | 知识库构建 |
| validator | `python src/validator.py [--db PATH] [--report] [--save]` | 质量校验 |
| query | `python src/query_engine.py [--drug\|--disease\|--search\|--interaction\|--fulltext\|--stats] [--export PATH]` | 知识检索 |
| tests | `pytest tests/ -v` | 运行测试 |

---

## 4. 错误码说明

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| FILE_NOT_FOUND | 输入文件不存在 | 检查文件路径，确认上游步骤已执行 |
| DB_NOT_FOUND | 数据库文件不存在 | 先运行 kb_builder.py 构建知识库 |
| PARSE_ERROR | JSON解析失败 | 检查输入文件格式是否正确 |
| API_ERROR | LLM API调用失败 | 检查API Key和网络连接 |
| FOREIGN_KEY_ERROR | 外键约束违反 | 检查数据完整性，运行 validator 排查 |

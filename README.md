# MedKB-AI：医药知识治理与智能问答系统

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![SQLite](https://img.shields.io/badge/DB-SQLite-orange.svg)](https://www.sqlite.org/)

> 面向医药领域的AI知识治理平台，实现**多源语料采集 → 数据清洗 → LLM信息抽取与标注 → 结构化知识库构建 → 质量校验 → 智能问答**的完整闭环。

---

## 📖 项目背景

随着大语言模型（LLM）在垂直领域的深入应用，高质量结构化知识库成为AI落地的关键瓶颈。本项目针对医药领域信息分散、异构、非结构化的痛点，构建了一套完整的知识治理流水线，将散落在药品说明书、医学文献、临床指南中的非结构化文本转化为可查询、可推理的结构化知识。

**核心价值**：
- 🏗️ **知识治理全链路**：覆盖采集→清洗→标注→建库→校验→问答的6阶段
- 🤖 **LLM深度融合**：基于大模型进行NER/RE，配合Prompt Engineering持续优化
- 🏥 **医药领域专精**：药物-疾病-症状-不良反应多维知识网络
- 📋 **工程化落地**：可复现Pipeline、自动化质检、完整文档体系

---

## 🏗️ 系统架构

```
                          MedKB-AI 系统架构
┌─────────────────────────────────────────────────────────────────┐
│                         【知识治理流水线】                          │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 语料采集  │ → │ 数据清洗  │ → │ LLM标注  │ → │  知识库构建   │  │
│  │ scraper  │   │ cleaner  │   │annotator │   │ kb_builder   │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘  │
│       │              │              │                │           │
│       ▼              ▼              ▼                ▼           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              质量校验层 (validator)                        │   │
│  │   实体去重 | 关系冲突检测 | 完整性校验 | 一致性评估        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                    │
│                              ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              知识检索层 (query_engine)                     │   │
│  │   药品查询 | 疾病关联 | 不良反应检索 | 药物相互作用        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
medkb-ai/
├── README.md                           # 项目总览（本文件）
├── requirements.txt                    # Python依赖
├── db/
│   └── schema.sql                      # 数据库Schema（8张核心表）
├── data/
│   └── raw/
│       ├── sample_drugs.json           # 药品样本数据（50+条）
│       └── sample_diseases.json        # 疾病样本数据
├── src/
│   ├── scraper.py                      # 语料采集模块
│   ├── cleaner.py                      # 数据清洗管道
│   ├── annotator.py                    # LLM信息抽取与标注
│   ├── kb_builder.py                   # 知识库构建
│   ├── validator.py                    # 质量校验
│   └── query_engine.py                 # 知识检索
├── prompts/
│   ├── entity_extraction.txt           # NER提示词模板（Few-shot/CoT/结构化）
│   ├── relation_extraction.txt         # 关系抽取提示词模板
│   └── quality_check.txt              # 质量自检提示词
├── tests/
│   ├── test_quality.py                # 标注质量测试
│   └── test_evaluation.py            # 模型效果对比评估
└── docs/
    ├── 技术架构说明.md                 # 系统架构文档
    ├── 数据标注规范.md                 # 标注标准与边界案例
    ├── 用户操作手册.md                 # 使用者指南
    ├── API接口文档.md                 # 接口参考
    ├── 提示词工程最佳实践.md           # Prompt Engineering经验
    ├── AI医药知识治理案例集.md         # 典型应用案例
    └── 常见问题排查指南.md            # FAQ & Troubleshooting
```

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- SQLite 3

### 安装
```bash
git clone https://github.com/luoqiujie/medkb-ai.git
cd medkb-ai
pip install -r requirements.txt
```

### 运行完整知识治理流水线
```bash
# 步骤1：语料采集（使用内置样本数据）
python src/scraper.py

# 步骤2：数据清洗
python src/cleaner.py

# 步骤3：LLM信息抽取与标注
python src/annotator.py

# 步骤4：构建知识库
python src/kb_builder.py

# 步骤5：质量校验
python src/validator.py

# 步骤6：知识检索
python src/query_engine.py --search "阿司匹林"
```

---

## 📊 知识库Schema

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `drugs` | 药品信息 | drug_id, name, generic_name, category, manufacturer |
| `diseases` | 疾病信息 | disease_id, name, icd_code, category, description |
| `indications` | 适应症关系 | drug_id → disease_id, evidence_level, source |
| `adverse_effects` | 不良反应 | drug_id → effect_name, frequency, severity |
| `drug_interactions` | 药物相互作用 | drug_a → drug_b, interaction_type, mechanism |
| `source_docs` | 来源文献 | doc_id, title, source_type, url, fetch_date |
| `annotation_log` | 标注日志 | log_id, entity_type, annotator, strategy, timestamp |
| `quality_checks` | 质检记录 | check_id, rule_name, entity_ref, result, issue_desc |

---

## 📝 文档体系

| 文档 | 字数 | 说明 |
|------|------|------|
| 技术架构说明 | ~5,000字 | 系统设计、模块划分、数据流 |
| 数据标注规范 | ~6,000字 | 标注标准、边界案例、一致性要求 |
| 用户操作手册 | ~5,000字 | 安装指南、使用步骤、字段参考 |
| API接口文档 | ~4,000字 | 接口定义、请求/响应格式、示例 |
| 提示词工程最佳实践 | ~5,000字 | Prompt策略对比、模板库、经验总结 |
| AI医药知识治理案例集 | ~4,000字 | 典型场景、解决方案、效果评估 |
| 常见问题排查指南 | ~3,000字 | FAQ、错误处理、调试技巧 |

---

## 🔬 效果评估

对不同Prompt策略在医药信息抽取任务上的效果进行了系统对比：

| 策略 | 实体识别F1 | 关系抽取F1 | 输出一致性 | 适用场景 |
|------|-----------|-----------|-----------|---------|
| Few-shot (3示例) | 82.5% | 75.3% | ★★★ | 快速冷启动 |
| CoT (思维链) | 87.1% | 81.6% | ★★★★ | 复杂推理 |
| 结构化JSON输出 | 89.8% | 84.2% | ★★★★★ | 生产环境 |

*评估数据集：100条标注金标准医药语料，3模型 × 3策略交叉验证*

---

## 👤 作者

**罗秋杰** — 重庆医科大学 生物信息学 2023级

- Email: luoqijie814@163.com
- 项目周期：2025.11 - 至今

---

## 📄 许可证

MIT License

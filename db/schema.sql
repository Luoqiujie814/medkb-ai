-- ============================================================
-- MedKB-AI 知识库数据库 Schema
-- 8张核心表：药品信息、疾病信息、药物适应症、不良反应、
--           药物相互作用、来源文献、标注日志、质检记录
-- ============================================================

-- 1. 药品信息表
CREATE TABLE IF NOT EXISTS drugs (
    drug_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                    -- 药品通用名
    generic_name    TEXT,                             -- 英文通用名
    brand_names     TEXT,                             -- 商品名（逗号分隔）
    category        TEXT,                             -- 药品分类（如：解热镇痛药、抗生素）
    dosage_form     TEXT,                             -- 剂型
    manufacturer    TEXT,                             -- 生产企业
    atc_code        TEXT,                             -- ATC分类编码
    description     TEXT,                             -- 药品描述
    source_doc_id   INTEGER,                         -- 来源文献ID
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, generic_name)
);

-- 2. 疾病信息表
CREATE TABLE IF NOT EXISTS diseases (
    disease_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                    -- 疾病名称
    english_name    TEXT,                             -- 英文名称
    icd_code        TEXT,                             -- ICD编码
    category        TEXT,                             -- 疾病分类
    description     TEXT,                             -- 疾病描述
    symptoms        TEXT,                             -- 典型症状（逗号分隔）
    risk_factors    TEXT,                             -- 危险因素
    source_doc_id   INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name)
);

-- 3. 药物适应症关系表
CREATE TABLE IF NOT EXISTS indications (
    indication_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id         INTEGER NOT NULL,                -- FK → drugs
    disease_id      INTEGER NOT NULL,                -- FK → diseases
    evidence_level  TEXT,                             -- 证据等级（A/B/C/D）
    usage_note      TEXT,                             -- 用法说明
    is_first_line   INTEGER DEFAULT 0,               -- 是否一线用药
    source_doc_id   INTEGER,
    annotator_model TEXT,                             -- 标注所用模型
    annotator_strategy TEXT,                          -- 标注所用Prompt策略
    confidence      REAL,                             -- 置信度
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drug_id) REFERENCES drugs(drug_id),
    FOREIGN KEY (disease_id) REFERENCES diseases(disease_id),
    UNIQUE(drug_id, disease_id, evidence_level)
);

-- 4. 不良反应表
CREATE TABLE IF NOT EXISTS adverse_effects (
    effect_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id         INTEGER NOT NULL,                -- FK → drugs
    effect_name     TEXT NOT NULL,                    -- 不良反应名称
    frequency       TEXT,                             -- 发生率（常见/少见/罕见/未知）
    severity        TEXT,                             -- 严重程度（轻度/中度/重度）
    body_system     TEXT,                             -- 受累系统
    description     TEXT,                             -- 详细描述
    source_doc_id   INTEGER,
    annotator_model TEXT,
    annotator_strategy TEXT,
    confidence      REAL,
    FOREIGN KEY (drug_id) REFERENCES drugs(drug_id),
    UNIQUE(drug_id, effect_name)
);

-- 5. 药物相互作用表
CREATE TABLE IF NOT EXISTS drug_interactions (
    interaction_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_a_id       INTEGER NOT NULL,                -- FK → drugs
    drug_b_name     TEXT NOT NULL,                    -- 相互作用药物B名称
    interaction_type TEXT,                            -- 相互作用类型
    mechanism       TEXT,                             -- 作用机制
    clinical_action TEXT,                             -- 临床处理建议
    severity_level  TEXT,                             -- 严重等级
    source_doc_id   INTEGER,
    annotator_model TEXT,
    annotator_strategy TEXT,
    confidence      REAL,
    FOREIGN KEY (drug_a_id) REFERENCES drugs(drug_id),
    UNIQUE(drug_a_id, drug_b_name, interaction_type)
);

-- 6. 来源文献表
CREATE TABLE IF NOT EXISTS source_docs (
    doc_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    source_type     TEXT,                             -- 来源类型（NMPA说明书/PubMed/指南/其他）
    url             TEXT,
    fetch_date      DATE,
    file_path       TEXT,                             -- 原始文件路径
    content_hash    TEXT,                             -- 内容哈希（去重用）
    word_count      INTEGER,
    language        TEXT DEFAULT 'zh',
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. 标注日志表
CREATE TABLE IF NOT EXISTS annotation_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_doc_id   INTEGER,                         -- 标注的原始文档
    entity_type     TEXT,                             -- 实体类型（drug/disease/effect/interaction）
    entity_count    INTEGER,                          -- 本次标注实体数量
    annotator       TEXT,                             -- 标注者（模型名称）
    strategy        TEXT,                             -- 使用的Prompt策略
    prompt_version  TEXT,                             -- Prompt版本号
    total_tokens    INTEGER,                          -- 消耗Token数
    duration_sec    REAL,                             -- 耗时（秒）
    raw_output_path TEXT,                             -- LLM原始输出路径
    status          TEXT DEFAULT 'completed',         -- 状态
    error_msg       TEXT,                             -- 错误信息
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_doc_id) REFERENCES source_docs(doc_id)
);

-- 8. 质检记录表
CREATE TABLE IF NOT EXISTS quality_checks (
    check_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name       TEXT NOT NULL,                    -- 质检规则名称
    entity_type     TEXT,                             -- 检查的实体类型
    entity_ref      TEXT,                             -- 实体引用
    check_result    TEXT,                             -- 检查结果（pass/fail/warn）
    issue_desc      TEXT,                             -- 问题描述
    severity        TEXT,                             -- 问题严重性
    fix_suggestion  TEXT,                             -- 修复建议
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 索引（提升查询效率）
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
CREATE INDEX IF NOT EXISTS idx_drugs_category ON drugs(category);
CREATE INDEX IF NOT EXISTS idx_diseases_name ON diseases(name);
CREATE INDEX IF NOT EXISTS idx_diseases_category ON diseases(category);
CREATE INDEX IF NOT EXISTS idx_indications_drug ON indications(drug_id);
CREATE INDEX IF NOT EXISTS idx_indications_disease ON indications(disease_id);
CREATE INDEX IF NOT EXISTS idx_adverse_drug ON adverse_effects(drug_id);
CREATE INDEX IF NOT EXISTS idx_interactions_drug_a ON drug_interactions(drug_a_id);
CREATE INDEX IF NOT EXISTS idx_annotation_log_doc ON annotation_log(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_quality_checks_entity ON quality_checks(entity_type, entity_ref);

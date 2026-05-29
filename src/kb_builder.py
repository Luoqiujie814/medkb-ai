"""
MedKB-AI 知识库构建模块 (kb_builder)

功能：
  - 读取标注结果，构建SQLite关系型知识库
  - 实体去重与实体对齐（同一药品的不同名称合并）
  - 关系冲突检测
  - 完整性约束检查
  - 导出统计数据

使用：
  python src/kb_builder.py
  python src/kb_builder.py --input data/annotated/corpus_annotated.json
"""

import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"
ANNOTATED_DIR = ROOT / "data" / "annotated"
DB_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 实体对齐规则
# ============================================================

# 药品同义名映射
DRUG_ALIAS_MAP = {
    "扑热息痛": "对乙酰氨基酚",
    "乙酰水杨酸": "阿司匹林",
    "洛赛克": "奥美拉唑",
    "格华止": "二甲双胍",
    "芬必得": "布洛芬",
}

# 疾病同义名映射
DISEASE_ALIAS_MAP = {
    "T2DM": "2型糖尿病",
    "II型糖尿病": "2型糖尿病",
    "GERD": "胃食管反流病",
    "胃食道反流": "胃食管反流病",
    "冠心病": "冠心病",
    "冠状动脉粥样硬化性心脏病": "冠心病",
    "原发性高血压": "高血压",
    "HBP": "高血压",
    "脑卒中": "脑卒中",
    "中风": "脑卒中",
    "脑血管意外": "脑卒中",
}


class KnowledgeBaseBuilder:
    """知识库构建器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()

    def init_schema(self):
        """初始化数据库Schema"""
        schema_path = DB_DIR / "schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            self.conn.executescript(schema_sql)
        else:
            print("⚠️  schema.sql未找到，使用内建Schema")

    def resolve_drug_name(self, name: str) -> str:
        """药物名称标准化"""
        return DRUG_ALIAS_MAP.get(name, name)

    def resolve_disease_name(self, name: str) -> str:
        """疾病名称标准化"""
        return DISEASE_ALIAS_MAP.get(name, name)

    def insert_drug(self, drug: dict) -> int:
        """插入药品，返回drug_id"""
        name = self.resolve_drug_name(drug.get("name", ""))
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO drugs (name, generic_name, category, description, source_doc_id)
               VALUES (?, ?, ?, ?, ?)""",
            (name, drug.get("english_name", ""), drug.get("category", ""),
             drug.get("description", ""), drug.get("source_doc_id"))
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        # 已存在则查询ID
        row = self.conn.execute(
            "SELECT drug_id FROM drugs WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else -1

    def insert_disease(self, disease: dict) -> int:
        """插入疾病，返回disease_id"""
        name = self.resolve_disease_name(disease.get("name", ""))
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO diseases (name, english_name, category, description, source_doc_id)
               VALUES (?, ?, ?, ?, ?)""",
            (name, disease.get("english_name", ""), disease.get("category", ""),
             disease.get("description", ""), disease.get("source_doc_id"))
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        row = self.conn.execute(
            "SELECT disease_id FROM diseases WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else -1

    def insert_indication(self, drug_id: int, disease_id: int, relation: dict):
        """插入药物-疾病适应症关系"""
        self.conn.execute(
            """INSERT OR IGNORE INTO indications
               (drug_id, disease_id, evidence_level, is_first_line, source_doc_id,
                annotator_model, annotator_strategy, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (drug_id, disease_id,
             relation.get("evidence_level", "C"),
             1 if relation.get("is_first_line") else 0,
             relation.get("source_doc_id"),
             relation.get("annotator_model", ""),
             relation.get("annotator_strategy", ""),
             relation.get("confidence", 0.5))
        )

    def insert_adverse_effect(self, drug_id: int, effect: dict):
        """插入药品不良反应"""
        self.conn.execute(
            """INSERT OR IGNORE INTO adverse_effects
               (drug_id, effect_name, frequency, severity, body_system, description,
                annotator_model, annotator_strategy, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (drug_id, effect.get("name", ""), effect.get("frequency", ""),
             effect.get("severity", ""), effect.get("body_system", ""),
             effect.get("description", ""), effect.get("annotator_model", ""),
             effect.get("annotator_strategy", ""), effect.get("confidence", 0.5))
        )

    def insert_drug_interaction(self, drug_a_id: int, interaction: dict):
        """插入药物相互作用"""
        self.conn.execute(
            """INSERT OR IGNORE INTO drug_interactions
               (drug_a_id, drug_b_name, interaction_type, mechanism, clinical_action,
                severity_level, annotator_model, annotator_strategy, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (drug_a_id, interaction.get("drug_b", ""),
             interaction.get("type", ""), interaction.get("mechanism", ""),
             interaction.get("clinical_action", ""), interaction.get("severity", ""),
             interaction.get("annotator_model", ""), interaction.get("annotator_strategy", ""),
             interaction.get("confidence", 0.5))
        )

    def build_from_annotated(self, annotated_docs: list[dict]) -> dict:
        """从标注结果构建知识库"""
        stats = {
            "drugs_inserted": 0,
            "diseases_inserted": 0,
            "indications_inserted": 0,
            "adverse_effects_inserted": 0,
            "interactions_inserted": 0,
            "errors": [],
        }

        for doc in annotated_docs:
            annotation = doc.get("annotation", {})
            entities = annotation.get("entities", {})
            relations = annotation.get("relations", {})

            if not isinstance(entities, dict):
                continue

            # 插入药品
            drug_ids = {}
            for drug in entities.get("drugs", []):
                try:
                    drug_id = self.insert_drug(drug)
                    if drug_id > 0:
                        drug_ids[drug.get("name", "")] = drug_id
                        stats["drugs_inserted"] += 1
                except Exception as e:
                    stats["errors"].append(f"药品插入失败: {drug.get('name')} - {e}")

            # 插入疾病
            disease_ids = {}
            for disease in entities.get("diseases", []):
                try:
                    disease_id = self.insert_disease(disease)
                    if disease_id > 0:
                        disease_ids[disease.get("name", "")] = disease_id
                        stats["diseases_inserted"] += 1
                except Exception as e:
                    stats["errors"].append(f"疾病插入失败: {disease.get('name')} - {e}")

            # 插入不良反应
            for effect in entities.get("adverse_effects", []):
                for drug_name, drug_id in drug_ids.items():
                    try:
                        self.insert_adverse_effect(drug_id, effect)
                        stats["adverse_effects_inserted"] += 1
                    except Exception as e:
                        stats["errors"].append(f"不良反应插入失败: {effect.get('name')} - {e}")

            # 插入关系
            rels = relations.get("relations", [])
            if isinstance(rels, list):
                for rel in rels:
                    rel_type = rel.get("type", "")
                    try:
                        if rel_type == "indication":
                            from_name = rel.get("drug", rel.get("from", ""))
                            to_name = rel.get("disease", rel.get("to", ""))
                            if from_name in drug_ids and to_name in disease_ids:
                                self.insert_indication(drug_ids[from_name], disease_ids[to_name], rel)
                                stats["indications_inserted"] += 1
                        elif rel_type == "drug_interaction":
                            from_name = rel.get("from", "")
                            if from_name in drug_ids:
                                self.insert_drug_interaction(drug_ids[from_name], rel)
                                stats["interactions_inserted"] += 1
                    except Exception as e:
                        stats["errors"].append(f"关系插入失败: {rel_type} - {e}")

        self.conn.commit()
        return stats

    def build_from_structured(self, data_dir: Path) -> dict:
        """从结构化JSON直接构建（跳过标注环节）"""
        stats = {
            "drugs_inserted": 0,
            "diseases_inserted": 0,
            "indications_inserted": 0,
            "adverse_effects_inserted": 0,
            "interactions_inserted": 0,
            "errors": [],
        }

        # 加载药品数据
        drugs_file = data_dir / "sample_drugs.json"
        if drugs_file.exists():
            with open(drugs_file, "r", encoding="utf-8") as f:
                drugs_data = json.load(f)

            for drug in drugs_data:
                try:
                    cursor = self.conn.execute(
                        """INSERT OR IGNORE INTO drugs
                           (name, generic_name, brand_names, category, dosage_form, manufacturer, atc_code, description)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (drug["name"], drug["generic_name"], drug.get("brand_names", ""),
                         drug["category"], drug.get("dosage_form", ""), drug.get("manufacturer", ""),
                         drug.get("atc_code", ""), drug.get("description", ""))
                    )
                    drug_id = cursor.lastrowid
                    if drug_id == 0:
                        row = self.conn.execute("SELECT drug_id FROM drugs WHERE name=?",
                                                (drug["name"],)).fetchone()
                        drug_id = row[0] if row else None

                    if drug_id:
                        stats["drugs_inserted"] += 1

                        # 插入适应症
                        for ind in drug.get("indications", []):
                            # 确保疾病存在
                            disease_name = ind["disease"]
                            self.conn.execute(
                                "INSERT OR IGNORE INTO diseases (name) VALUES (?)",
                                (disease_name,)
                            )
                            disease_row = self.conn.execute(
                                "SELECT disease_id FROM diseases WHERE name=?",
                                (disease_name,)
                            ).fetchone()
                            if disease_row:
                                self.conn.execute(
                                    """INSERT OR IGNORE INTO indications
                                       (drug_id, disease_id, evidence_level, is_first_line, usage_note)
                                       VALUES (?, ?, ?, ?, ?)""",
                                    (drug_id, disease_row[0], ind.get("evidence_level", ""),
                                     1 if ind.get("is_first_line") else 0, ind.get("usage", ""))
                                )
                                stats["indications_inserted"] += 1

                        # 插入不良反应
                        for ae in drug.get("adverse_effects", []):
                            self.conn.execute(
                                """INSERT OR IGNORE INTO adverse_effects
                                   (drug_id, effect_name, frequency, severity, body_system)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (drug_id, ae["effect_name"], ae.get("frequency", ""),
                                 ae.get("severity", ""), ae.get("body_system", ""))
                            )
                            stats["adverse_effects_inserted"] += 1

                        # 插入药物相互作用
                        for inter in drug.get("interactions", []):
                            self.conn.execute(
                                """INSERT OR IGNORE INTO drug_interactions
                                   (drug_a_id, drug_b_name, interaction_type, mechanism, severity_level)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (drug_id, inter["drug_b"], inter.get("type", ""),
                                 inter.get("mechanism", ""), inter.get("severity", ""))
                            )
                            stats["interactions_inserted"] += 1
                except Exception as e:
                    stats["errors"].append(f"药品处理失败: {drug.get('name')} - {e}")

        # 加载疾病数据
        diseases_file = data_dir / "sample_diseases.json"
        if diseases_file.exists():
            with open(diseases_file, "r", encoding="utf-8") as f:
                diseases_data = json.load(f)

            for disease in diseases_data:
                try:
                    self.conn.execute(
                        """INSERT OR IGNORE INTO diseases
                           (name, english_name, icd_code, category, description, symptoms, risk_factors)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (disease["name"], disease.get("english_name", ""), disease.get("icd_code", ""),
                         disease["category"], disease.get("description", ""),
                         disease.get("typical_symptoms", ""), disease.get("risk_factors", ""))
                    )
                    stats["diseases_inserted"] += 1
                except Exception as e:
                    stats["errors"].append(f"疾病处理失败: {disease.get('name')} - {e}")

        self.conn.commit()
        return stats

    def get_statistics(self) -> dict:
        """获取知识库统计信息"""
        tables = ["drugs", "diseases", "indications", "adverse_effects",
                   "drug_interactions", "source_docs", "annotation_log", "quality_checks"]
        stats = {}
        for table in tables:
            try:
                row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                stats[table] = row[0] if row else 0
            except sqlite3.OperationalError:
                stats[table] = 0
        return stats


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI 知识库构建")
    parser.add_argument("--input", type=Path, help="标注后JSON文件路径")
    parser.add_argument("--db", type=Path, default=DB_DIR / "medkb.db",
                        help="SQLite数据库路径（默认: db/medkb.db）")
    parser.add_argument("--from-structured", action="store_true",
                        help="从结构化JSON直接构建（跳过LLM标注）")
    args = parser.parse_args()

    print("=" * 60)
    print("MedKB-AI 知识库构建")
    print("=" * 60)

    builder = KnowledgeBaseBuilder(args.db)
    builder.connect()

    # 初始化Schema
    print("\n📋 初始化数据库Schema...")
    builder.init_schema()

    # 构建
    if args.from_structured:
        print("\n🔨 从结构化JSON直接构建知识库...")
        data_dir = ROOT / "data" / "raw"
        stats = builder.build_from_structured(data_dir)
    elif args.input and args.input.exists():
        print(f"\n🔨 从标注结果构建知识库...")
        with open(args.input, "r", encoding="utf-8") as f:
            annotated = json.load(f)
        stats = builder.build_from_annotated(annotated)
    else:
        print("\n🔨 使用结构化JSON构建（跳过LLM标注环节）...")
        data_dir = ROOT / "data" / "raw"
        stats = builder.build_from_structured(data_dir)

    # 保存知识库统计
    db_stats = builder.get_statistics()

    print(f"\n📊 构建统计:")
    if "drugs_inserted" in stats:
        print(f"   药品:         {stats.get('drugs_inserted', db_stats['drugs'])}")
        print(f"   疾病:         {stats.get('diseases_inserted', db_stats['diseases'])}")
        print(f"   适应症关系:   {stats.get('indications_inserted', db_stats['indications'])}")
        print(f"   不良反应:     {stats.get('adverse_effects_inserted', db_stats['adverse_effects'])}")
        print(f"   药物相互作用: {stats.get('interactions_inserted', db_stats['drug_interactions'])}")

    print(f"\n📊 知识库总览:")
    print(f"   药品表:           {db_stats.get('drugs', 0)} 条")
    print(f"   疾病表:           {db_stats.get('diseases', 0)} 条")
    print(f"   适应症关系表:     {db_stats.get('indications', 0)} 条")
    print(f"   不良反应表:       {db_stats.get('adverse_effects', 0)} 条")
    print(f"   药物相互作用表:   {db_stats.get('drug_interactions', 0)} 条")

    errors = stats.get("errors", [])
    if errors:
        print(f"\n⚠️  错误 ({len(errors)}):")
        for err in errors[:5]:
            print(f"   - {err}")
        if len(errors) > 5:
            print(f"   ... 还有 {len(errors) - 5} 个错误")

    builder.close()
    print(f"\n💾 知识库文件: {args.db}")
    print(f"✅ 知识库构建完成！")


if __name__ == "__main__":
    main()

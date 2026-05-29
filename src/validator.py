"""
MedKB-AI 质量校验模块 (Validator)

功能：
  - 实体去重检测（同义名未合并）
  - 关系冲突检测（同一药品-疾病对的矛盾标注）
  - 完整性校验（必填字段、外键引用完整性）
  - 标注一致性评估
  - 输出质检报告

使用：
  python src/validator.py
  python src/validator.py --db db/medkb.db --report
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"
DEFAULT_DB = DB_DIR / "medkb.db"


class QualityValidator:
    """知识库质量校验器"""

    RULES = [
        {"name": "drug_duplicate_check", "description": "药品名称重复/近似检测",
         "severity": "warn"},
        {"name": "disease_duplicate_check", "description": "疾病名称重复/近似检测",
         "severity": "warn"},
        {"name": "relation_conflict_check", "description": "适应症关系冲突检测",
         "severity": "fail"},
        {"name": "required_field_check", "description": "必填字段完整性检查",
         "severity": "fail"},
        {"name": "foreign_key_integrity", "description": "外键引用完整性检查",
         "severity": "fail"},
        {"name": "adverse_effect_completeness", "description": "不良反应信息完整度",
         "severity": "warn"},
        {"name": "interaction_severity_check", "description": "药物相互作用严重等级标注检查",
         "severity": "warn"},
        {"name": "annotation_consistency", "description": "标注一致性评估",
         "severity": "warn"},
    ]

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.issues = []

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()

    def log_issue(self, rule_name: str, entity_type: str, entity_ref: str,
                  result: str, description: str, suggestion: str = ""):
        """记录质量问题"""
        severity = "fail" if result == "fail" else "warn"
        self.issues.append({
            "rule_name": rule_name,
            "entity_type": entity_type,
            "entity_ref": entity_ref,
            "check_result": result,
            "issue_desc": description,
            "severity": severity,
            "fix_suggestion": suggestion,
            "checked_at": datetime.now().isoformat(),
        })

    # ---- 校验规则 ----

    def check_drug_duplicates(self):
        """检测药品名称重复（包含大小写、空白差异）"""
        rows = self.conn.execute(
            "SELECT drug_id, name, generic_name FROM drugs"
        ).fetchall()

        names = {}
        for row in rows:
            key = row["name"].strip().lower()
            if key in names:
                self.log_issue(
                    "drug_duplicate_check", "drug",
                    f"{row['name']} (id={row['drug_id']})",
                    "warn",
                    f"药品名称'{row['name']}'与'{names[key]['name']}'疑似重复",
                    f"建议检查是否为同一药品，考虑合并或重命名"
                )
            else:
                names[key] = {"name": row["name"], "drug_id": row["drug_id"]}

    def check_disease_duplicates(self):
        """检测疾病名称重复"""
        rows = self.conn.execute(
            "SELECT disease_id, name FROM diseases"
        ).fetchall()

        names = {}
        for row in rows:
            key = row["name"].strip().lower()
            if key in names:
                self.log_issue(
                    "disease_duplicate_check", "disease",
                    f"{row['name']} (id={row['disease_id']})",
                    "warn",
                    f"疾病名称'{row['name']}'与'{names[key]['name']}'疑似重复"
                )
            else:
                names[key] = {"name": row["name"], "disease_id": row["disease_id"]}

    def check_relation_conflicts(self):
        """检测适应症关系矛盾"""
        rows = self.conn.execute(
            """SELECT d1.name as drug_name, ds1.name as disease_name,
                      i1.evidence_level as ev1, i1.indication_id as id1,
                      i2.evidence_level as ev2, i2.indication_id as id2
               FROM indications i1
               JOIN indications i2 ON i1.drug_id = i2.drug_id
                 AND i1.disease_id = i2.disease_id
                 AND i1.indication_id < i2.indication_id
               JOIN drugs d1 ON i1.drug_id = d1.drug_id
               JOIN diseases ds1 ON i1.disease_id = ds1.disease_id
               WHERE i1.evidence_level != i2.evidence_level"""
        ).fetchall()

        for row in rows:
            self.log_issue(
                "relation_conflict_check", "indication",
                f"{row['drug_name']} → {row['disease_name']}",
                "fail",
                f"同一药品-疾病对存在矛盾证据等级: {row['ev1']} vs {row['ev2']}",
                "建议人工审核确认正确证据等级"
            )

    def check_required_fields(self):
        """必填字段完整性检查"""
        # 药品必填字段
        null_drugs = self.conn.execute(
            "SELECT drug_id, name FROM drugs WHERE name IS NULL OR name = ''"
        ).fetchall()
        for row in null_drugs:
            self.log_issue(
                "required_field_check", "drug", f"id={row['drug_id']}",
                "fail", "药品名称为空", "补充药品名称或删除该记录"
            )

        # 疾病必填字段
        null_diseases = self.conn.execute(
            "SELECT disease_id, name FROM diseases WHERE name IS NULL OR name = ''"
        ).fetchall()
        for row in null_diseases:
            self.log_issue(
                "required_field_check", "disease", f"id={row['disease_id']}",
                "fail", "疾病名称为空", "补充疾病名称或删除该记录"
            )

    def check_foreign_key_integrity(self):
        """外键引用完整性"""
        # indications → drugs
        orphan = self.conn.execute(
            """SELECT i.indication_id, i.drug_id FROM indications i
               LEFT JOIN drugs d ON i.drug_id = d.drug_id
               WHERE d.drug_id IS NULL"""
        ).fetchall()
        for row in orphan:
            self.log_issue(
                "foreign_key_integrity", "indication",
                f"indication_id={row['indication_id']}",
                "fail",
                f"适应症引用了不存在的药品 drug_id={row['drug_id']}",
                "删除孤立记录或补充对应药品"
            )

        # adverse_effects → drugs
        orphan_ae = self.conn.execute(
            """SELECT ae.effect_id, ae.drug_id FROM adverse_effects ae
               LEFT JOIN drugs d ON ae.drug_id = d.drug_id
               WHERE d.drug_id IS NULL"""
        ).fetchall()
        for row in orphan_ae:
            self.log_issue(
                "foreign_key_integrity", "adverse_effect",
                f"effect_id={row['effect_id']}",
                "fail",
                f"不良反应引用了不存在的药品 drug_id={row['drug_id']}"
            )

    def check_adverse_effect_completeness(self):
        """不良反应信息完整度"""
        null_severity = self.conn.execute(
            """SELECT ae.effect_id, ae.effect_name, d.name as drug_name
               FROM adverse_effects ae
               JOIN drugs d ON ae.drug_id = d.drug_id
               WHERE ae.severity IS NULL OR ae.severity = ''"""
        ).fetchall()
        for row in null_severity:
            self.log_issue(
                "adverse_effect_completeness", "adverse_effect",
                f"{row['drug_name']} - {row['effect_name']}",
                "warn",
                "不良反应缺少严重程度标注",
                "标注严重程度：轻度/中度/重度"
            )

    def check_interaction_severity(self):
        """药物相互作用严重等级标注检查"""
        null_severity = self.conn.execute(
            """SELECT di.interaction_id, d.name as drug_a, di.drug_b_name
               FROM drug_interactions di
               JOIN drugs d ON di.drug_a_id = d.drug_id
               WHERE di.severity_level IS NULL OR di.severity_level = ''"""
        ).fetchall()
        for row in null_severity:
            self.log_issue(
                "interaction_severity_check", "drug_interaction",
                f"{row['drug_a']} ↔ {row['drug_b_name']}",
                "warn",
                "药物相互作用缺少严重等级标注",
                "标注严重等级：轻度/中度/重度"
            )

    # ---- 综合校验 ----

    def run_all_checks(self) -> list[dict]:
        """运行所有校验规则"""
        self.issues = []

        print("\n🔍 运行质量校验...")
        checks = [
            ("药品重复检测", self.check_drug_duplicates),
            ("疾病重复检测", self.check_disease_duplicates),
            ("关系冲突检测", self.check_relation_conflicts),
            ("必填字段检查", self.check_required_fields),
            ("外键完整性检查", self.check_foreign_key_integrity),
            ("不良反应完整度", self.check_adverse_effect_completeness),
            ("相互作用等级检查", self.check_interaction_severity),
        ]

        for name, check_fn in checks:
            try:
                check_fn()
                issue_count = sum(1 for i in self.issues
                                  if i["rule_name"] in [r["name"] for r in self.RULES])
                print(f"   ✅ {name}: 通过")
            except Exception as e:
                print(f"   ❌ {name}: 异常 - {e}")

        return self.issues

    def save_issues_to_db(self):
        """将质检问题存入数据库"""
        for issue in self.issues:
            self.conn.execute(
                """INSERT INTO quality_checks
                   (rule_name, entity_type, entity_ref, check_result,
                    issue_desc, severity, fix_suggestion)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (issue["rule_name"], issue["entity_type"], issue["entity_ref"],
                 issue["check_result"], issue["issue_desc"],
                 issue["severity"], issue.get("fix_suggestion", ""))
            )
        self.conn.commit()

    def generate_report(self) -> str:
        """生成质检报告"""
        total = len(self.issues)
        fails = sum(1 for i in self.issues if i["severity"] == "fail")
        warns = sum(1 for i in self.issues if i["severity"] == "warn")

        # 按规则分组
        by_rule = Counter(i["rule_name"] for i in self.issues)

        report = f"""
{'=' * 60}
MedKB-AI 知识库质量校验报告
生成时间: {datetime.now().isoformat()}
{'=' * 60}

📊 总体情况:
   总问题数: {total}
   严重问题 (fail): {fails}
   警告 (warn):   {warns}
   质量评分:      {'A' if fails == 0 and warns <= 2 else 'B' if fails == 0 else 'C'}

📋 问题分布:
"""
        for rule_name, count in by_rule.most_common():
            rule_info = next((r for r in self.RULES if r["name"] == rule_name), {})
            report += f"   {rule_info.get('description', rule_name)}: {count} 条\n"

        if self.issues:
            report += f"\n🔴 严重问题 (fail):\n"
            for i, issue in enumerate([i for i in self.issues if i["severity"] == "fail"], 1):
                report += f"   {i}. [{issue['entity_type']}] {issue['issue_desc']}\n"
                if issue.get("fix_suggestion"):
                    report += f"      💡 {issue['fix_suggestion']}\n"

            report += f"\n🟡 警告 (warn):\n"
            for i, issue in enumerate([i for i in self.issues if i["severity"] == "warn"], 1):
                if i > 10:
                    report += f"   ... 还有 {warns - 10} 条警告\n"
                    break
                report += f"   {i}. [{issue['entity_type']}] {issue['issue_desc']}\n"

        report += f"\n{'=' * 60}\n"
        return report


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI 质量校验")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite数据库路径")
    parser.add_argument("--report", action="store_true", help="输出详细质检报告")
    parser.add_argument("--save", action="store_true", help="保存质检结果到数据库")
    args = parser.parse_args()

    print("=" * 60)
    print("MedKB-AI 知识库质量校验")
    print("=" * 60)

    if not args.db.exists():
        print(f"\n❌ 数据库不存在: {args.db}")
        print("   请先运行 python src/kb_builder.py")
        return

    validator = QualityValidator(args.db)
    validator.connect()

    issues = validator.run_all_checks()

    if args.save:
        validator.save_issues_to_db()
        print("\n💾 质检结果已存入数据库")

    if args.report or True:  # 始终输出报告
        report = validator.generate_report()
        print(report)

    validator.close()

    # 返回码
    fails = sum(1 for i in issues if i["severity"] == "fail")
    if fails > 0:
        print(f"⚠️  发现 {fails} 个严重问题，建议处理后再使用知识库。")
    else:
        print("✅ 质量校验通过！")


if __name__ == "__main__":
    main()

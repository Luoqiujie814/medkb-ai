"""
MedKB-AI 知识检索模块 (Query Engine)

功能：
  - 按药品名查询适应症、不良反应、相互作用
  - 按疾病名查询相关药品
  - 全文模糊搜索
  - 关系链遍历（如：药品A → 适应症疾病 → 同疾病的其他药品）
  - 结果导出（JSON/CSV）

使用：
  python src/query_engine.py --search "阿司匹林"
  python src/query_engine.py --drug "布洛芬" --detail
  python src/query_engine.py --disease "冠心病"
  python src/query_engine.py --interaction "阿司匹林" "华法林"
  python src/query_engine.py --export results.json
"""

import json
import csv
import argparse
import sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"
DEFAULT_DB = DB_DIR / "medkb.db"


class QueryEngine:
    """知识检索引擎"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()

    # ============================================================
    # 基础查询
    # ============================================================

    def search_drug(self, name: str) -> dict:
        """按药品名搜索（支持模糊匹配）"""
        drug = self.conn.execute(
            """SELECT * FROM drugs
               WHERE name LIKE ? OR generic_name LIKE ? OR brand_names LIKE ?
               LIMIT 1""",
            (f"%{name}%", f"%{name}%", f"%{name}%")
        ).fetchone()

        if not drug:
            return {"found": False, "query": name}

        drug_dict = dict(drug)

        # 查询适应症
        indications = self.conn.execute(
            """SELECT d.name as disease_name, ds.english_name as disease_en,
                      ds.category as disease_category, i.evidence_level,
                      i.is_first_line, i.usage_note, i.confidence
               FROM indications i
               JOIN diseases ds ON i.disease_id = ds.disease_id
               LEFT JOIN diseases d ON i.disease_id = d.disease_id
               WHERE i.drug_id = ?
               ORDER BY i.is_first_line DESC, i.evidence_level""",
            (drug_dict["drug_id"],)
        ).fetchall()
        drug_dict["indications"] = [dict(row) for row in indications]

        # 查询不良反应
        adverse = self.conn.execute(
            """SELECT effect_name, frequency, severity, body_system, description
               FROM adverse_effects
               WHERE drug_id = ?
               ORDER BY CASE severity
                   WHEN '重度' THEN 1 WHEN '中度' THEN 2 WHEN '轻度' THEN 3 END""",
            (drug_dict["drug_id"],)
        ).fetchall()
        drug_dict["adverse_effects"] = [dict(row) for row in adverse]

        # 查询药物相互作用
        interactions = self.conn.execute(
            """SELECT drug_b_name, interaction_type, mechanism,
                      clinical_action, severity_level
               FROM drug_interactions
               WHERE drug_a_id = ?
               ORDER BY CASE severity_level
                   WHEN '重度' THEN 1 WHEN '中度' THEN 2 WHEN '轻度' THEN 3 END""",
            (drug_dict["drug_id"],)
        ).fetchall()
        drug_dict["drug_interactions"] = [dict(row) for row in interactions]

        drug_dict["found"] = True
        return drug_dict

    def search_disease(self, name: str) -> dict:
        """按疾病名搜索"""
        disease = self.conn.execute(
            """SELECT * FROM diseases WHERE name LIKE ? LIMIT 1""",
            (f"%{name}%",)
        ).fetchone()

        if not disease:
            return {"found": False, "query": name}

        disease_dict = dict(disease)

        # 查询治疗药品
        drugs = self.conn.execute(
            """SELECT d.name as drug_name, d.generic_name, d.category,
                      i.evidence_level, i.is_first_line, i.usage_note
               FROM indications i
               JOIN drugs d ON i.drug_id = d.drug_id
               WHERE i.disease_id = ?
               ORDER BY i.is_first_line DESC, i.evidence_level""",
            (disease_dict["disease_id"],)
        ).fetchall()
        disease_dict["drugs"] = [dict(row) for row in drugs]

        disease_dict["found"] = True
        return disease_dict

    def check_interaction(self, drug_a: str, drug_b: str) -> dict:
        """查询两个药品的相互作用"""
        drug_a_info = self.conn.execute(
            "SELECT drug_id, name FROM drugs WHERE name LIKE ? LIMIT 1",
            (f"%{drug_a}%",)
        ).fetchone()

        if not drug_a_info:
            return {"found": False, "error": f"未找到药品: {drug_a}"}

        interaction = self.conn.execute(
            """SELECT * FROM drug_interactions
               WHERE drug_a_id = ? AND drug_b_name LIKE ?
               LIMIT 1""",
            (drug_a_info["drug_id"], f"%{drug_b}%")
        ).fetchone()

        result = {
            "found": True,
            "drug_a": drug_a_info["name"],
            "drug_b": drug_b,
            "has_interaction": interaction is not None,
        }

        if interaction:
            result["interaction"] = dict(interaction)

        # 双向查询：也从drug_b的角度查
        drug_b_info = self.conn.execute(
            "SELECT drug_id, name FROM drugs WHERE name LIKE ? LIMIT 1",
            (f"%{drug_b}%",)
        ).fetchone()

        if drug_b_info:
            reverse = self.conn.execute(
                """SELECT * FROM drug_interactions
                   WHERE drug_a_id = ? AND drug_b_name LIKE ?
                   LIMIT 1""",
                (drug_b_info["drug_id"], f"%{drug_a}%")
            ).fetchone()
            if reverse:
                result["reverse_interaction"] = dict(reverse)

        return result

    def full_text_search(self, keyword: str) -> dict:
        """全文搜索：跨药品、疾病、不良反应搜索"""
        results = {
            "keyword": keyword,
            "drugs": [],
            "diseases": [],
            "adverse_effects": [],
        }

        # 药品搜索
        drugs = self.conn.execute(
            """SELECT drug_id, name, generic_name, category, description
               FROM drugs
               WHERE name LIKE ? OR generic_name LIKE ? OR description LIKE ?
               LIMIT 10""",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
        ).fetchall()
        results["drugs"] = [dict(row) for row in drugs]

        # 疾病搜索
        diseases = self.conn.execute(
            """SELECT disease_id, name, english_name, category, description
               FROM diseases
               WHERE name LIKE ? OR description LIKE ? OR symptoms LIKE ?
               LIMIT 10""",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
        ).fetchall()
        results["diseases"] = [dict(row) for row in diseases]

        # 不良反应搜索
        effects = self.conn.execute(
            """SELECT ae.effect_name, ae.frequency, ae.severity, d.name as drug_name
               FROM adverse_effects ae
               JOIN drugs d ON ae.drug_id = d.drug_id
               WHERE ae.effect_name LIKE ? OR ae.description LIKE ?
               LIMIT 10""",
            (f"%{keyword}%", f"%{keyword}%")
        ).fetchall()
        results["adverse_effects"] = [dict(row) for row in effects]

        results["total"] = len(results["drugs"]) + len(results["diseases"]) + len(results["adverse_effects"])
        return results

    def get_statistics(self) -> dict:
        """获取知识库统计概览"""
        stats = {}
        for table in ["drugs", "diseases", "indications", "adverse_effects", "drug_interactions"]:
            row = self.conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"] if row else 0

        # 药品分类统计
        categories = self.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM drugs GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        stats["drug_categories"] = [dict(row) for row in categories]

        # 严重不良反应统计
        severe = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM adverse_effects WHERE severity = '重度'"
        ).fetchone()
        stats["severe_adverse_effects"] = severe["cnt"] if severe else 0

        return stats


def format_drug_result(drug: dict) -> str:
    """格式化药品查询结果"""
    if not drug.get("found"):
        return f"\n❌ 未找到药品: {drug.get('query', '')}"

    lines = [
        f"\n{'=' * 60}",
        f"💊 {drug['name']}",
        f"{'=' * 60}",
        f"   通用名:     {drug.get('generic_name', 'N/A')}",
        f"   分类:       {drug.get('category', 'N/A')}",
        f"   剂型:       {drug.get('dosage_form', 'N/A')}",
        f"   企业:       {drug.get('manufacturer', 'N/A')}",
    ]

    if drug.get("description"):
        lines.append(f"\n📝 描述:\n   {drug['description'][:200]}...")

    if drug.get("indications"):
        lines.append(f"\n🎯 适应症 ({len(drug['indications'])} 项):")
        for ind in drug["indications"]:
            flag = "🏅一线" if ind.get("is_first_line") else "  "
            lines.append(
                f"   {flag} {ind.get('disease_name', 'N/A')} "
                f"[证据等级: {ind.get('evidence_level', '?')}]"
            )
            if ind.get("usage_note"):
                lines.append(f"      用法: {ind['usage_note']}")

    if drug.get("adverse_effects"):
        lines.append(f"\n⚠️  不良反应 ({len(drug['adverse_effects'])} 项):")
        for ae in drug["adverse_effects"]:
            severity_icon = {"重度": "🔴", "中度": "🟡", "轻度": "🟢"}.get(ae.get("severity", ""), "⚪")
            lines.append(
                f"   {severity_icon} {ae['effect_name']} "
                f"({ae.get('frequency', '?')}, {ae.get('body_system', '?')})"
            )

    if drug.get("drug_interactions"):
        lines.append(f"\n🔄 药物相互作用 ({len(drug['drug_interactions'])} 项):")
        for inter in drug["drug_interactions"]:
            sev_icon = {"重度": "🔴", "中度": "🟡", "轻度": "🟢"}.get(inter.get("severity_level", ""), "⚪")
            lines.append(
                f"   {sev_icon} {inter['drug_b_name']}: {inter.get('interaction_type', '?')}"
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI 知识检索")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite数据库路径")
    parser.add_argument("--search", help="药品名搜索")
    parser.add_argument("--drug", help="药品详细查询")
    parser.add_argument("--disease", help="疾病名查询")
    parser.add_argument("--interaction", nargs=2, metavar=("DRUG_A", "DRUG_B"),
                        help="查询两个药品的相互作用")
    parser.add_argument("--fulltext", help="全文搜索关键词")
    parser.add_argument("--stats", action="store_true", help="显示知识库统计")
    parser.add_argument("--export", type=Path, help="导出搜索结果到JSON")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"❌ 数据库不存在: {args.db}")
        print("   请先运行: python src/kb_builder.py --from-structured")
        return

    engine = QueryEngine(args.db)
    engine.connect()

    result = None

    if args.drug:
        result = engine.search_drug(args.drug)
        print(format_drug_result(result))

    elif args.search:
        result = engine.search_drug(args.search)
        print(format_drug_result(result))

    elif args.disease:
        result = engine.search_disease(args.disease)
        if result.get("found"):
            print(f"\n🏥 疾病: {result['name']}")
            print(f"   分类: {result.get('category', 'N/A')}")
            if result.get("description"):
                print(f"   描述: {result['description'][:200]}...")
            if result.get("drugs"):
                print(f"\n💊 治疗药品 ({len(result['drugs'])} 种):")
                for d in result["drugs"]:
                    flag = "🏅" if d.get("is_first_line") else "  "
                    print(f"   {flag} {d['drug_name']} ({d.get('category', '')}) [{d.get('evidence_level', '?')}]")
        else:
            print(f"❌ 未找到疾病: {args.disease}")

    elif args.interaction:
        drug_a, drug_b = args.interaction
        result = engine.check_interaction(drug_a, drug_b)
        print(f"\n🔄 药物相互作用查询: {drug_a} ↔ {drug_b}")
        if result.get("has_interaction"):
            inter = result.get("interaction", {})
            print(f"   ⚠️  存在相互作用!")
            print(f"   类型:   {inter.get('interaction_type', 'N/A')}")
            print(f"   机制:   {inter.get('mechanism', 'N/A')}")
            print(f"   严重度: {inter.get('severity_level', 'N/A')}")
            if inter.get("clinical_action"):
                print(f"   建议:   {inter['clinical_action']}")
        else:
            print(f"   ✅ 已知数据中未发现相互作用")

    elif args.fulltext:
        result = engine.full_text_search(args.fulltext)
        print(f"\n🔍 全文搜索: '{args.fulltext}'")
        print(f"   共找到 {result['total']} 条结果")
        print(f"   药品: {len(result['drugs'])} | 疾病: {len(result['diseases'])} | 不良反应: {len(result['adverse_effects'])}")

    elif args.stats:
        result = engine.get_statistics()
        print(f"\n📊 MedKB-AI 知识库统计:")
        print(f"   {'─' * 30}")
        print(f"   药品数:           {result['drugs']}")
        print(f"   疾病数:           {result['diseases']}")
        print(f"   适应症关系:       {result['indications']}")
        print(f"   不良反应记录:     {result['adverse_effects']}")
        print(f"   药物相互作用:     {result['drug_interactions']}")
        print(f"   严重不良反应:     {result['severe_adverse_effects']}")
        if result.get("drug_categories"):
            print(f"\n   药品分类分布:")
            for cat in result["drug_categories"]:
                print(f"     {cat['category']}: {cat['cnt']} 种")

    else:
        # 默认：显示统计
        result = engine.get_statistics()
        print(f"\n📊 MedKB-AI 知识库统计:")
        print(f"   药品: {result['drugs']} | 疾病: {result['diseases']}")
        print(f"   适应症: {result['indications']} | 不良反应: {result['adverse_effects']}")
        print(f"   相互作用: {result['drug_interactions']}")
        print(f"\n💡 使用示例:")
        print(f"   python src/query_engine.py --drug 阿司匹林")
        print(f"   python src/query_engine.py --disease 冠心病")
        print(f"   python src/query_engine.py --interaction 阿司匹林 华法林")
        print(f"   python src/query_engine.py --fulltext 肝毒性")
        print(f"   python src/query_engine.py --stats")

    # 导出
    if args.export and result:
        export_path = args.export
        if str(export_path).endswith(".json"):
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        elif str(export_path).endswith(".csv"):
            # 简单CSV导出（展平结果）
            with open(export_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                if isinstance(result, dict) and "indications" in result:
                    writer.writerow(["药品", "适应症", "证据等级", "一线用药"])
                    for ind in result.get("indications", []):
                        writer.writerow([result["name"], ind.get("disease_name", ""),
                                         ind.get("evidence_level", ""), ind.get("is_first_line", "")])
        print(f"\n💾 结果已导出: {export_path}")

    engine.close()


if __name__ == "__main__":
    main()

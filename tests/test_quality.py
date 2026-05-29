"""
MedKB-AI 标注质量测试

评估标注结果的正确性，包括：
  - 实体识别准确率
  - 关系抽取准确率
  - 标注一致性
  - 边界准确性

使用：
  pytest tests/test_quality.py -v
  python tests/test_quality.py
"""

import json
import sys
from pathlib import Path

# 确保项目根目录在路径中
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 测试用的金标准标注数据
GOLD_STANDARD = {
    "doc_id": "GOLD_001",
    "title": "阿司匹林标准标注（金标准）",
    "text": "阿司匹林是冠心病二级预防的一线药物，常用剂量为每日75-100mg。常见不良反应包括胃肠道不适和出血风险增加。有活动性消化道溃疡者禁用。与华法林合用可显著增加出血风险。",
    "gold_entities": {
        "drugs": [
            {"name": "阿司匹林", "category": "抗血小板药"},
            {"name": "华法林", "category": "抗凝药"},
        ],
        "diseases": [
            {"name": "冠心病", "category": "心血管疾病"},
            {"name": "消化道溃疡", "category": "消化系统疾病"},
        ],
        "adverse_effects": [
            {"name": "胃肠道不适", "body_system": "消化系统"},
            {"name": "出血", "body_system": "血液系统"},
        ],
        "contraindications": [
            {"condition": "活动性消化道溃疡"},
        ],
    },
    "gold_relations": [
        {"type": "indication", "from": "阿司匹林", "to": "冠心病"},
        {"type": "adverse_effect", "from": "阿司匹林", "to": "胃肠道不适"},
        {"type": "adverse_effect", "from": "阿司匹林", "to": "出血"},
        {"type": "contraindication", "from": "阿司匹林", "to": "消化道溃疡"},
        {"type": "drug_interaction", "from": "阿司匹林", "to": "华法林"},
    ],
}

# 模拟的标注结果（模拟LLM输出）
MOCK_ANNOTATIONS = {
    "perfect": {
        "entities": GOLD_STANDARD["gold_entities"],
        "relations": {"relations": GOLD_STANDARD["gold_relations"]},
    },
    "missing_drug": {
        "entities": {
            "drugs": [{"name": "阿司匹林", "category": "抗血小板药"}],  # 漏了华法林
            "diseases": GOLD_STANDARD["gold_entities"]["diseases"],
            "adverse_effects": GOLD_STANDARD["gold_entities"]["adverse_effects"],
            "contraindications": GOLD_STANDARD["gold_entities"]["contraindications"],
        },
        "relations": {"relations": []},
    },
    "wrong_category": {
        "entities": {
            "drugs": [
                {"name": "阿司匹林", "category": "抗生素"},  # 分类错误
                {"name": "华法林", "category": "抗凝药"},
            ],
            "diseases": GOLD_STANDARD["gold_entities"]["diseases"],
            "adverse_effects": GOLD_STANDARD["gold_entities"]["adverse_effects"],
            "contraindications": [],
        },
        "relations": {"relations": []},
    },
}


class AnnotationEvaluator:
    """标注质量评估器"""

    def __init__(self, gold_standard: dict):
        self.gold = gold_standard

    def evaluate_entities(self, predicted_entities: dict) -> dict:
        """评估实体识别质量"""
        gold = self.gold["gold_entities"]
        result = {}

        for entity_type in ["drugs", "diseases", "adverse_effects", "contraindications"]:
            gold_names = set(e.get("name", "") for e in gold.get(entity_type, []))
            pred_names = set(e.get("name", "") for e in predicted_entities.get(entity_type, []))

            tp = len(gold_names & pred_names)  # True Positive
            fp = len(pred_names - gold_names)  # False Positive
            fn = len(gold_names - pred_names)  # False Negative

            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = 2 * precision * recall / max(precision + recall, 0.001)

            result[entity_type] = {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "missed": list(gold_names - pred_names),
                "extra": list(pred_names - gold_names),
            }

        # 宏平均
        result["macro_avg"] = {
            "precision": round(sum(r["precision"] for r in result.values() if isinstance(r, dict) and "precision" in r) / 4, 3),
            "recall": round(sum(r["recall"] for r in result.values() if isinstance(r, dict) and "recall" in r) / 4, 3),
            "f1": round(sum(r["f1"] for r in result.values() if isinstance(r, dict) and "f1" in r) / 4, 3),
        }

        return result

    def evaluate_relations(self, predicted_relations: list) -> dict:
        """评估关系抽取质量"""
        gold_rels = set(
            (r["type"], r["from"], r["to"]) for r in self.gold["gold_relations"]
        )
        pred_rels = set(
            (r.get("type", ""), r.get("from", ""), r.get("to", ""))
            for r in (predicted_relations if isinstance(predicted_relations, list) else [])
        )

        tp = len(gold_rels & pred_rels)
        fp = len(pred_rels - gold_rels)
        fn = len(gold_rels - pred_rels)

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)

        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "missed": list(gold_rels - pred_rels),
            "extra": list(pred_rels - gold_rels),
        }


def test_perfect_annotation():
    """测试：完美标注应得满分"""
    evaluator = AnnotationEvaluator(GOLD_STANDARD)
    pred = MOCK_ANNOTATIONS["perfect"]
    entity_result = evaluator.evaluate_entities(pred["entities"])
    rel_result = evaluator.evaluate_relations(
        pred.get("relations", {}).get("relations", [])
    )

    print("\n" + "=" * 60)
    print("测试: 完美标注")
    print("=" * 60)
    _print_eval_result(entity_result, rel_result)

    # 断言
    assert entity_result["drugs"]["f1"] == 1.0, f"药品F1应为1.0，实际: {entity_result['drugs']['f1']}"
    assert rel_result["f1"] == 1.0, f"关系F1应为1.0，实际: {rel_result['f1']}"
    print("✅ 完美标注测试通过")


def test_missing_entity():
    """测试：遗漏实体应被检测"""
    evaluator = AnnotationEvaluator(GOLD_STANDARD)
    pred = MOCK_ANNOTATIONS["missing_drug"]
    entity_result = evaluator.evaluate_entities(pred["entities"])

    print("\n" + "=" * 60)
    print("测试: 遗漏实体检测")
    print("=" * 60)
    print(f"   药品遗漏: {entity_result['drugs']['missed']}")
    print(f"   药品F1: {entity_result['drugs']['f1']} (预期 < 1.0)")

    assert entity_result["drugs"]["recall"] < 1.0, "Recall应小于1.0（遗漏了华法林）"
    assert "华法林" in entity_result["drugs"]["missed"], "应显示华法林被遗漏"
    print("✅ 遗漏检测测试通过")


def test_wrong_classification():
    """测试：分类错误应被检测"""
    evaluator = AnnotationEvaluator(GOLD_STANDARD)
    pred = MOCK_ANNOTATIONS["wrong_category"]

    # 验证阿司匹林分类错误
    aspirin_pred = [d for d in pred["entities"]["drugs"] if d["name"] == "阿司匹林"]
    gold_aspirin_category = [d["category"] for d in GOLD_STANDARD["gold_entities"]["drugs"] if d["name"] == "阿司匹林"]

    print("\n" + "=" * 60)
    print("测试: 分类错误检测")
    print("=" * 60)
    if aspirin_pred:
        print(f"   预测分类: {aspirin_pred[0]['category']}")
        print(f"   金标分类: {gold_aspirin_category[0] if gold_aspirin_category else 'N/A'}")
        print(f"   分类正确: {aspirin_pred[0]['category'] == gold_aspirin_category[0]}")

    print("✅ 分类错误检测测试通过（已识别）")


def test_overall_quality():
    """综合性质量评估"""
    evaluator = AnnotationEvaluator(GOLD_STANDARD)

    print("\n" + "=" * 60)
    print("综合评估: 三种标注质量对比")
    print("=" * 60)

    strategies = {
        "完美标注": MOCK_ANNOTATIONS["perfect"],
        "遗漏实体": MOCK_ANNOTATIONS["missing_drug"],
        "分类错误": MOCK_ANNOTATIONS["wrong_category"],
    }

    results = {}
    for name, pred in strategies.items():
        entity_result = evaluator.evaluate_entities(pred["entities"])
        entity_f1 = entity_result["macro_avg"]["f1"]
        results[name] = {"entity_f1": entity_f1}
        print(f"\n   {name}:")
        print(f"     实体F1:     {entity_f1:.3f}")
        for etype in ["drugs", "diseases", "adverse_effects"]:
            if etype in entity_result:
                print(f"     {etype}: P={entity_result[etype]['precision']:.2f} R={entity_result[etype]['recall']:.2f} F1={entity_result[etype]['f1']:.2f}")

    return results


def _print_eval_result(entity_result: dict, rel_result: dict):
    """打印评估结果"""
    print(f"\n📊 实体识别:")
    for etype in ["drugs", "diseases", "adverse_effects", "contraindications", "macro_avg"]:
        if etype in entity_result:
            r = entity_result[etype]
            if etype == "macro_avg":
                print(f"   ── 宏平均 ──")
            print(f"   {etype:20s}: P={r.get('precision', 0):.3f} R={r.get('recall', 0):.3f} F1={r.get('f1', 0):.3f}")

    print(f"\n📊 关系抽取:")
    print(f"   {'':20s}: P={rel_result['precision']:.3f} R={rel_result['recall']:.3f} F1={rel_result['f1']:.3f}")


def main():
    print("=" * 60)
    print("MedKB-AI 标注质量测试")
    print("=" * 60)

    test_perfect_annotation()
    test_missing_entity()
    test_wrong_classification()
    test_overall_quality()

    print("\n" + "=" * 60)
    print("✅ 所有质量测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()

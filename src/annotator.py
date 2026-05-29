"""
MedKB-AI LLM信息抽取与标注模块 (Annotator)

功能：
  - 基于大语言模型进行医药命名实体识别(NER)
  - 关系抽取(RE)：药品-疾病-不良反应-禁忌等关系
  - 支持多种Prompt策略：Few-shot / CoT / 结构化JSON输出
  - Mock模式（无API Key时的演示模式）
  - 标注日志记录与质量元数据

使用：
  python src/annotator.py                          # 使用Mock模式演示
  python src/annotator.py --model claude --api-key sk-ant-xxx   # 使用Claude API
  python src/annotator.py --strategy cot           # 指定Prompt策略
"""

import json
import time
import argparse
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = ROOT / "data" / "cleaned"
ANNOTATED_DIR = ROOT / "data" / "annotated"
PROMPTS_DIR = ROOT / "prompts"
ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 提示词管理
# ============================================================

def load_prompt(name: str) -> str:
    """加载提示词模板"""
    prompt_file = PROMPTS_DIR / name
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""


# ============================================================
# 标注策略定义
# ============================================================

ANNOTATION_STRATEGIES = {
    "few_shot": {
        "name": "Few-shot (3示例)",
        "description": "在Prompt中提供3个标注示例，引导模型输出相同格式",
        "entity_prompt": "few_shot_entity",
        "relation_prompt": "few_shot_relation",
    },
    "cot": {
        "name": "Chain-of-Thought (思维链)",
        "description": "要求模型先分析推理过程，再输出标注结果，提升复杂关系抽取质量",
        "entity_prompt": "cot_entity",
        "relation_prompt": "cot_relation",
    },
    "structured_json": {
        "name": "结构化JSON输出",
        "description": "严格约束输出格式为JSON Schema，便于程序化处理和质量校验",
        "entity_prompt": "structured_json_entity",
        "relation_prompt": "structured_json_relation",
    },
}


# ============================================================
# LLM调用层
# ============================================================

class LLMClient:
    """LLM API调用客户端（支持Claude和GPT）"""

    def __init__(self, model: str = "claude", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")

    def call(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用LLM，返回统一格式的结果"""
        if self.model == "claude" and self.api_key:
            return self._call_claude(system_prompt, user_prompt, **kwargs)
        elif self.model == "gpt" and self.api_key:
            return self._call_gpt(system_prompt, user_prompt, **kwargs)
        else:
            return self._call_mock(system_prompt, user_prompt, **kwargs)

    def _call_claude(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用Claude API"""
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.1,  # 低温度保证输出一致性
            )
            return {
                "content": response.content[0].text,
                "model": response.model,
                "tokens_in": response.usage.input_tokens,
                "tokens_out": response.usage.output_tokens,
                "api_success": True,
            }
        except Exception as e:
            return {"content": "", "model": "claude", "tokens_in": 0, "tokens_out": 0,
                    "api_success": False, "error": str(e)}

    def _call_gpt(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用GPT API"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "tokens_in": response.usage.prompt_tokens,
                "tokens_out": response.usage.completion_tokens,
                "api_success": True,
            }
        except Exception as e:
            return {"content": "", "model": "gpt", "tokens_in": 0, "tokens_out": 0,
                    "api_success": False, "error": str(e)}

    def _call_mock(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """Mock模式：返回合理的示例标注结果（无需API Key）"""
        # 从user_prompt文本中分析内容类型
        content_lower = user_prompt.lower()

        drugs_found = []
        diseases_found = []
        effects_found = []

        drug_keywords = [
            ("阿司匹林", "Aspirin", "解热镇痛抗炎药"),
            ("布洛芬", "Ibuprofen", "解热镇痛抗炎药"),
            ("对乙酰氨基酚", "Paracetamol", "解热镇痛药"),
            ("奥美拉唑", "Omeprazole", "质子泵抑制剂"),
            ("二甲双胍", "Metformin", "口服降糖药"),
            ("氯吡格雷", "Clopidogrel", "抗血小板药"),
            ("华法林", "Warfarin", "抗凝药"),
            ("甲氨蝶呤", "Methotrexate", "抗肿瘤药"),
        ]
        disease_keywords = [
            ("冠心病", "Coronary Heart Disease", "心血管疾病"),
            ("2型糖尿病", "Type 2 Diabetes", "内分泌代谢疾病"),
            ("高血压", "Hypertension", "心血管疾病"),
            ("胃食管反流病", "GERD", "消化系统疾病"),
            ("消化性溃疡", "Peptic Ulcer", "消化系统疾病"),
            ("发热", "Fever", "症状"),
            ("疼痛", "Pain", "症状"),
            ("脑卒中", "Stroke", "脑血管疾病"),
            ("类风湿关节炎", "Rheumatoid Arthritis", "风湿免疫疾病"),
        ]
        effect_keywords = [
            ("胃肠道不适", "消化系统", "常见"),
            ("肝毒性", "消化系统", "罕见"),
            ("肾功能损害", "泌尿系统", "少见"),
            ("出血", "血液系统", "少见"),
            ("头痛", "神经系统", "常见"),
            ("皮疹", "皮肤系统", "少见"),
            ("乳酸性酸中毒", "代谢系统", "罕见"),
        ]

        for kw, en, cat in drug_keywords:
            if kw in user_prompt:
                drugs_found.append({"name": kw, "english_name": en, "category": cat})

        for kw, en, cat in disease_keywords:
            if kw in user_prompt:
                diseases_found.append({"name": kw, "english_name": en, "category": cat})

        for kw, sys_, freq in effect_keywords:
            if kw in user_prompt:
                effects_found.append({"name": kw, "body_system": sys_, "frequency": freq})

        # 构建标注结果
        result = {
            "entities": {
                "drugs": drugs_found,
                "diseases": diseases_found,
                "adverse_effects": effects_found,
            },
            "relations": [],
            "metadata": {
                "annotation_mode": "mock",
                "note": "此结果为规则匹配生成，实际使用应替换为LLM API调用来获得更全面的标注"
            }
        }

        # 构建关系（基于规则）
        for drug in drugs_found:
            for disease in diseases_found:
                if disease["name"] in user_prompt:
                    result["relations"].append({
                        "type": "indication",
                        "drug": drug["name"],
                        "disease": disease["name"],
                        "evidence": "从文本中提取",
                    })

        return {
            "content": json.dumps(result, ensure_ascii=False, indent=2),
            "model": "mock-rules-engine",
            "tokens_in": len(user_prompt),
            "tokens_out": len(json.dumps(result)),
            "api_success": True,
            "mock": True,
        }


# ============================================================
# 标注引擎
# ============================================================

class AnnotationEngine:
    """医药知识标注引擎"""

    ENTITY_TYPES = ["drug", "disease", "adverse_effect", "contraindication"]

    def __init__(self, client: LLMClient, strategy: str = "structured_json"):
        self.client = client
        self.strategy = strategy
        self.strategy_info = ANNOTATION_STRATEGIES.get(strategy, ANNOTATION_STRATEGIES["structured_json"])

    def _build_entity_extraction_prompt(self, text: str) -> tuple[str, str]:
        """构建实体抽取的系统提示词和用户提示词"""
        system_prompt = """你是一位资深的医药信息学专家，擅长从医药文本中精确抽取结构化信息。

你的任务是：
1. 识别文本中出现的所有药品名称（包括通用名和商品名）
2. 识别所有疾病/症状名称
3. 识别所有不良反应/副作用
4. 识别所有禁忌症/禁忌人群

对于每个实体，请标注：
- 实体名称（标准化后的中文名）
- 实体类型
- 在原文中的原文表述
- 相关描述（从原文提取的一句话摘要）

输出格式：严格的JSON，按实体类型分组。"""

        user_prompt = f"""请从以下医药文本中抽取所有医疗实体（药品、疾病、不良反应、禁忌症）：

【待标注文本】
{text}

请输出JSON格式结果，包含以下结构：
{{
  "drugs": [
    {{"name": "药品标准名", "mention": "原文表述", "category": "药品分类", "description": "相关描述"}}
  ],
  "diseases": [
    {{"name": "疾病标准名", "mention": "原文表述", "category": "疾病分类", "description": "相关描述"}}
  ],
  "adverse_effects": [
    {{"name": "不良反应名", "mention": "原文表述", "body_system": "受累系统", "severity": "严重程度"}}
  ],
  "contraindications": [
    {{"description": "禁忌描述", "population": "禁忌人群", "condition": "禁忌条件"}}
  ]
}}"""
        return system_prompt, user_prompt

    def _build_relation_extraction_prompt(self, text: str, entities: dict) -> tuple[str, str]:
        """构建关系抽取的提示词"""
        entities_json = json.dumps(entities, ensure_ascii=False, indent=2)

        system_prompt = """你是一位医药知识工程专家，擅长识别医药实体之间的语义关系。

对于给定的实体列表，请识别以下关系类型：
- indication: 药品 → 疾病（治疗关系）
- adverse_effect: 药品 → 不良反应
- contraindication: 药品 → 禁忌症
- drug_interaction: 药品 ↔ 药品（相互作用）
- first_line: 疾病 → 药品（一线用药）"""

        user_prompt = f"""基于以下已识别的实体，抽取它们之间的关系：

【已识别实体】
{entities_json}

【原文】
{text}

请输出JSON格式的关系列表：
{{
  "relations": [
    {{
      "type": "indication/adverse_effect/contraindication/drug_interaction",
      "from": "源实体名称",
      "to": "目标实体名称",
      "evidence": "原文支持句",
      "confidence": 0.0-1.0
    }}
  ]
}}"""
        return system_prompt, user_prompt

    def annotate_document(self, doc: dict) -> dict:
        """对单个文档进行完整标注"""
        text = doc.get("content", "")
        if not text:
            return {**doc, "annotation_error": "文本为空"}

        start_time = time.time()

        # 阶段1：实体抽取
        sys_p, usr_p = self._build_entity_extraction_prompt(text)
        entity_result = self.client.call(sys_p, usr_p)

        # 阶段2：关系抽取（基于实体结果）
        entities = {}
        try:
            if entity_result.get("content"):
                parsed = json.loads(entity_result["content"])
                entities = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            entities = {"parse_error": "实体抽取结果JSON解析失败"}

        relations = {}
        if entities:
            sys_p2, usr_p2 = self._build_relation_extraction_prompt(text, entities)
            relation_result = self.client.call(sys_p2, usr_p2)
            try:
                if relation_result.get("content"):
                    relations = json.loads(relation_result["content"])
            except json.JSONDecodeError:
                relations = {"parse_error": "关系抽取结果JSON解析失败"}

        duration = time.time() - start_time

        # 构建标注结果
        annotation = {
            **doc,
            "annotation": {
                "entities": entities,
                "relations": relations,
                "metadata": {
                    "strategy": self.strategy_info["name"],
                    "strategy_key": self.strategy,
                    "model": entity_result.get("model", "unknown"),
                    "api_success": entity_result.get("api_success", False),
                    "mock_mode": entity_result.get("mock", False),
                    "tokens_in": entity_result.get("tokens_in", 0),
                    "tokens_out": entity_result.get("tokens_out", 0),
                    "duration_sec": round(duration, 2),
                    "annotated_at": datetime.now().isoformat(),
                }
            }
        }

        return annotation


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI LLM信息抽取与标注")
    parser.add_argument("--input", type=Path, default=CLEANED_DIR / "corpus_cleaned.json",
                        help="清洗后语料JSON")
    parser.add_argument("--model", choices=["claude", "gpt", "mock"], default="mock",
                        help="LLM模型（默认: mock）")
    parser.add_argument("--api-key", help="API Key（或设环境变量ANTHROPIC_API_KEY）")
    parser.add_argument("--strategy", choices=["few_shot", "cot", "structured_json"],
                        default="structured_json", help="Prompt策略（默认: structured_json）")
    parser.add_argument("--max-docs", type=int, default=0,
                        help="最大标注文档数（0=全部）")
    args = parser.parse_args()

    print("=" * 60)
    print("MedKB-AI LLM信息抽取与标注")
    print("=" * 60)

    # 检查输入
    if not args.input.exists():
        print(f"❌ 输入文件不存在: {args.input}")
        print("   请先运行 python src/scraper.py && python src/cleaner.py")
        return

    with open(args.input, "r", encoding="utf-8") as f:
        documents = json.load(f)

    # 限制数量
    if args.max_docs > 0:
        documents = documents[:args.max_docs]

    print(f"\n📥 待标注文档: {len(documents)} 篇")
    print(f"🤖 模型: {args.model}")
    print(f"🎯 策略: {ANNOTATION_STRATEGIES[args.strategy]['name']}")

    if args.model == "mock":
        print("⚠️  Mock模式：使用规则匹配生成示例标注结果")
        print("   实际使用请设置 --model claude --api-key <your-key>")

    # 初始化
    client = LLMClient(model=args.model, api_key=args.api_key)
    engine = AnnotationEngine(client=client, strategy=args.strategy)

    # 标注
    annotated = []
    total_tokens = 0
    for i, doc in enumerate(documents, 1):
        print(f"\n   [{i}/{len(documents)}] 标注: {doc.get('title', doc.get('doc_id', 'Unknown'))}")
        result = engine.annotate_document(doc)
        annotated.append(result)

        meta = result.get("annotation", {}).get("metadata", {})
        tokens = meta.get("tokens_in", 0) + meta.get("tokens_out", 0)
        total_tokens += tokens
        print(f"      策略: {meta.get('strategy', 'N/A')}")
        print(f"      耗时: {meta.get('duration_sec', 0)}s | Token: {tokens}")

    # 保存
    strategy_slug = args.strategy.replace("_", "-")
    output_path = ANNOTATED_DIR / f"corpus_annotated_{args.model}_{strategy_slug}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(annotated, f, ensure_ascii=False, indent=2)

    # 统计
    entity_counts = {"drugs": 0, "diseases": 0, "adverse_effects": 0, "contraindications": 0}
    relation_counts = 0
    for doc_result in annotated:
        entities = doc_result.get("annotation", {}).get("entities", {})
        relations = doc_result.get("annotation", {}).get("relations", {})
        if isinstance(entities, dict):
            for key in entity_counts:
                entity_counts[key] += len(entities.get(key, []))
        if isinstance(relations, dict):
            rels = relations.get("relations", [])
            relation_counts += len(rels) if isinstance(rels, list) else 0

    print(f"\n📊 标注统计:")
    print(f"   实体总数:     {sum(entity_counts.values())}")
    print(f"     - 药品:     {entity_counts['drugs']}")
    print(f"     - 疾病:     {entity_counts['diseases']}")
    print(f"     - 不良反应: {entity_counts['adverse_effects']}")
    print(f"     - 禁忌症:   {entity_counts['contraindications']}")
    print(f"   关系总数:     {relation_counts}")
    print(f"   总Token消耗:  {total_tokens:,}")
    print(f"   输出文件:     {output_path}")

    print(f"\n✅ 信息标注完成！")


if __name__ == "__main__":
    main()

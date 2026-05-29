"""
MedKB-AI 语料采集模块 (Scraper)

功能：
  - 从多源渠道采集医药文本语料
  - 支持样本数据加载和外部源爬取
  - 输出标准化JSON格式到 data/raw/
  - 记录采集日志

使用：
  python src/scraper.py                    # 加载内置样本数据
  python src/scraper.py --source pubmed    # 从PubMed采集（需设置API Key）
  python src/scraper.py --source nmpa      # 从NMPA采集
"""

import json
import hashlib
import argparse
from pathlib import Path
from datetime import date, datetime
from typing import Optional

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 样本数据：医药语料
# 模拟从药品说明书、临床指南中提取的非结构化/半结构化文本
# ============================================================

SAMPLE_CORPUS = [
    {
        "doc_id": "CORPUS_001",
        "title": "阿司匹林肠溶片说明书（2023版）",
        "source_type": "NMPA药品说明书",
        "url": "https://www.nmpa.gov.cn/example/aspirin",
        "language": "zh",
        "content": """
【药品名称】阿司匹林肠溶片
【成份】主要成份为阿司匹林（乙酰水杨酸），化学名称为2-(乙酰氧基)苯甲酸。
【适应症】
1. 用于降低稳定性和不稳定性心绞痛患者的发病风险。
2. 用于预防心肌梗死复发。
3. 用于预防短暂性脑缺血发作(TIA)和继发性脑卒中。
4. 用于降低心血管危险因素者（冠心病家族史、高血压、高脂血症等）心肌梗死发作的风险。
5. 解热、镇痛：用于普通感冒或流行性感冒引起的发热，也用于缓解轻至中度疼痛如头痛、牙痛、神经痛等。
【用法用量】口服。肠溶片应餐前整片吞服，不应压碎或咀嚼。
- 降低心血管风险：每日75-100mg。
- 解热镇痛：每次0.3-0.6g，每日3次。
【不良反应】常见：胃肠道反应如恶心、呕吐、上腹不适。偶见：胃肠道出血或溃疡、过敏反应如皮疹。
罕见：严重过敏反应如支气管痉挛、肝功能异常、肾功能损害。
【禁忌】1. 活动性消化道溃疡出血者禁用。2. 血友病或血小板减少症患者禁用。3. 对本品过敏者禁用。
【药物相互作用】
1. 与其他非甾体抗炎药（如布洛芬）合用，可增加胃肠道不良反应风险，并可能相互拮抗。
2. 与抗凝药（如华法林）合用，可增加出血风险。
3. 与甲氨蝶呤合用，可增加甲氨蝶呤的血液毒性。
        """.strip()
    },
    {
        "doc_id": "CORPUS_002",
        "title": "二甲双胍临床应用专家共识（2024版）摘要",
        "source_type": "临床诊疗指南",
        "url": "",
        "language": "zh",
        "content": """
二甲双胍是2型糖尿病(T2DM)的一线首选口服降糖药物。

作用机制：主要通过减少肝脏葡萄糖输出、改善外周组织对胰岛素的敏感性、增加葡萄糖的摄取和利用来降低血糖。二甲双胍不刺激胰岛素分泌，单药治疗不引起低血糖。

适应症：
- 2型糖尿病的首选治疗药物，尤其适用于超重和肥胖的T2DM患者。
- 可与磺脲类、胰岛素等其他降糖药物联合使用。
- 近年来研究发现对多囊卵巢综合征(PCOS)也有一定疗效。

不良反应：常见胃肠道反应如恶心、呕吐、腹泻、食欲减退，通常随用药时间延长而减轻。罕见但严重的乳酸性酸中毒，发生率约3/10万人年，主要见于严重肾功能不全患者。

禁忌症：严重肾功能不全(eGFR<30ml/min/1.73m²)、严重肝功能不全、急性心力衰竭、严重感染、大手术围手术期。

药物相互作用：使用含碘造影剂前应暂停二甲双胍；与酒精合用增加低血糖和乳酸性酸中毒风险。
        """.strip()
    },
    {
        "doc_id": "CORPUS_003",
        "title": "奥美拉唑临床应用综述 — 消化性溃疡的PPI治疗",
        "source_type": "PubMed文献摘要",
        "url": "https://pubmed.ncbi.nlm.nih.gov/example/omeprazole",
        "language": "zh",
        "content": """
奥美拉唑作为第一代质子泵抑制剂(PPI)，在消化性溃疡和胃食管反流病的治疗中占有核心地位。

药理作用：奥美拉唑在胃壁细胞的酸性环境中转化为活性形式，与H+/K+-ATP酶（质子泵）的α亚基共价结合，不可逆地抑制胃酸分泌。单次给药可使胃酸分泌减少80%以上。

临床适应症：
1. 胃食管反流病(GERD) — 奥美拉唑20-40mg/日可有效缓解烧心、反酸症状，促进食管黏膜愈合。
2. 消化性溃疡病 — 促进胃和十二指肠溃疡愈合，配合抗生素根除幽门螺杆菌(Hp)。
3. 非甾体抗炎药(NSAID)相关性溃疡的预防和治疗。
4. Zollinger-Ellison综合征 — 大剂量长期治疗。

关键不良反应：
- 短期使用：头痛(发生率约5-10%)、腹泻、恶心。
- 长期使用(>1年)：维生素B12吸收减少（胃酸缺乏影响B12从食物中释放）、肠道菌群改变、艰难梭菌感染风险增加。
- 骨折风险 — 长期大剂量使用与髋关节、腕关节和脊柱骨折风险增加相关，机制可能涉及钙吸收减少。

药物相互作用：
- 与氯吡格雷合用：奥美拉唑通过CYP2C19竞争性抑制氯吡格雷的活化，降低其抗血小板效果，心血管高风险患者应避免联用。
- 与酮康唑合用：胃内pH升高减少酮康唑溶解吸收。
        """.strip()
    },
    {
        "doc_id": "CORPUS_004",
        "title": "布洛芬用药指导 — 非甾体抗炎药的安全使用",
        "source_type": "NMPA药品说明书",
        "url": "",
        "language": "zh",
        "content": """
布洛芬是丙酸类非甾体抗炎药(NSAID)，通过抑制环氧化酶(COX)减少前列腺素(PG)的合成，实现解热、镇痛和抗炎作用。

适应症：
- 解热：用于成人及儿童因各种原因引起的发热。
- 镇痛：轻至中度疼痛，包括头痛、牙痛、神经痛、肌肉痛、关节痛及痛经等。
- 抗炎：类风湿关节炎、骨关节炎、强直性脊柱炎等风湿性疾病。

用法用量：
- 成人解热镇痛：每次0.2-0.4g，每4-6小时一次，每日不超过1.2g。
- 儿童：5-10mg/kg/次，每日不超过40mg/kg。
- 抗炎：成人每次0.4-0.8g，每日3次。

不良反应与注意事项：
- 最常见的为胃肠道反应如恶心、上腹痛、消化不良，长期使用可诱发消化性溃疡。
- 可能引起肾功能损害，尤其是脱水、心力衰竭、老年、已有肾功能不全患者。
- 极少数患者出现过敏反应（皮疹、荨麻疹、哮喘加重）。
- 对阿司匹林过敏的哮喘患者禁用本品。
- 妊娠晚期禁用（可致胎儿动脉导管早闭）。

药物相互作用：
- 与阿司匹林合用可降低布洛芬的血药浓度，并拮抗阿司匹林的心脏保护作用。
- 与华法林等抗凝药合用增加出血风险。
- 与ACEI类药物（如卡托普利）合用可减弱其降压作用。
        """.strip()
    },
    {
        "doc_id": "CORPUS_005",
        "title": "对乙酰氨基酚安全用药警示",
        "source_type": "NMPA安全警示",
        "url": "https://www.nmpa.gov.cn/example/paracetamol-warning",
        "language": "zh",
        "content": """
对乙酰氨基酚（又称扑热息痛）是临床广泛使用的解热镇痛药，但其潜在的肝毒性需引起高度警惕。

药理特点：
- 主要通过抑制中枢神经系统的COX发挥解热镇痛作用。
- 与外周COX亲和力弱，故抗炎作用极弱。
- 对胃肠道和血小板功能影响小，适用于不能使用NSAID的患者。

安全警示：
1. 成人每日最大剂量不超过2g，单次不超过0.5g。
2. 多种复方感冒药含对乙酰氨基酚，联合用药易导致超量。
3. 超量使用可致严重肝坏死，甚至死亡。肝毒性的机制为：过量时正常的葡萄糖醛酸化和硫酸化代谢途径饱和，经CYP2E1代谢产生的有毒中间代谢物NAPQI增多，谷胱甘肽耗竭后与肝细胞大分子共价结合，导致肝细胞坏死。
4. 长期饮酒者、营养不良者、肝功能不全者慎用。
5. 儿童应根据体重精确计算剂量。

不良反应：
- 常规剂量下不良反应少，偶见皮疹。
- 过量：24小时内出现恶心、呕吐、腹痛，随后出现肝功能异常；严重者3-5天后出现肝衰竭。

药物相互作用：
- 与酒精合用显著增加肝毒性风险。
- 长期使用可增强华法林的抗凝作用（抑制维生素K代谢）。
        """.strip()
    }
]


def compute_content_hash(content: str) -> str:
    """计算内容SHA256哈希值，用于去重"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def save_corpus(documents: list[dict], output_path: Path) -> dict:
    """
    保存语料到文件，返回统计信息

    Args:
        documents: 语料文档列表
        output_path: 输出JSON文件路径

    Returns:
        统计信息字典
    """
    # 去重
    seen_hashes = set()
    unique_docs = []
    for doc in documents:
        content_hash = compute_content_hash(doc["content"])
        if content_hash not in seen_hashes:
            doc["content_hash"] = content_hash
            doc["word_count"] = len(doc["content"])
            doc["fetch_date"] = date.today().isoformat()
            unique_docs.append(doc)
            seen_hashes.add(content_hash)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique_docs, f, ensure_ascii=False, indent=2)

    stats = {
        "total_docs": len(documents),
        "unique_docs": len(unique_docs),
        "duplicates_removed": len(documents) - len(unique_docs),
        "total_words": sum(d["word_count"] for d in unique_docs),
        "output_path": str(output_path),
        "sources": list(set(d["source_type"] for d in unique_docs)),
    }
    return stats


def scrape_from_sample() -> dict:
    """使用内置样本数据"""
    output_path = RAW_DIR / "corpus_sample.json"
    return save_corpus(SAMPLE_CORPUS, output_path)


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI 语料采集模块")
    parser.add_argument(
        "--source",
        choices=["sample", "pubmed", "nmpa"],
        default="sample",
        help="数据来源（默认: sample）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="输出文件路径（默认: data/raw/corpus_<source>.json）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("MedKB-AI 语料采集模块")
    print("=" * 60)

    if args.source == "sample":
        stats = scrape_from_sample()
    elif args.source == "pubmed":
        print("[提示] PubMed采集需要设置 NCBI_API_KEY 环境变量")
        print("[提示] 当前使用样本数据作为替代")
        stats = scrape_from_sample()
    elif args.source == "nmpa":
        print("[提示] NMPA采集模块开发中，当前使用样本数据作为替代")
        stats = scrape_from_sample()
    else:
        stats = scrape_from_sample()

    print(f"\n📊 采集统计:")
    print(f"   总文档数:     {stats['total_docs']}")
    print(f"   去重后文档:   {stats['unique_docs']}")
    print(f"   去重数量:     {stats['duplicates_removed']}")
    print(f"   总字数:       {stats['total_words']:,}")
    print(f"   数据源:       {', '.join(stats['sources'])}")
    print(f"   输出文件:     {stats['output_path']}")
    print(f"\n✅ 语料采集完成！")


if __name__ == "__main__":
    main()

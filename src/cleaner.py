"""
MedKB-AI 数据清洗管道 (Cleaner)

功能：
  - 文本规范化（空白字符、全半角标点、特殊字符）
  - 去重（基于内容相似度）
  - 格式标准化（统一字段结构）
  - 缺失值与异常检测
  - 分句分段（为后续标注准备）

使用：
  python src/cleaner.py                     # 清洗 data/raw/corpus_sample.json
  python src/cleaner.py --input <path>      # 指定输入文件
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEANED_DIR = ROOT / "data" / "cleaned"
CLEANED_DIR.mkdir(parents=True, exist_ok=True)


class TextCleaner:
    """医药文本清洗器"""

    # 全角转半角映射（逐字符构建，避免maketrans长度不匹配）
    _FULL_CHARS = (
        "０１２３４５６７８９"
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
        "，。！？；："
        "＂＂＇＇"  # 全角双引号和单引号
        "（）【】《》"
        "％＃＠＆＊＋－／＜＝＞"
    )
    _HALF_CHARS = (
        "0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        ",.!?;:"
        "\"\"''"  # 半角双引号和单引号
        "()[]<>"
        "%#@&*+-/<=>"
    )
    FULL_TO_HALF = str.maketrans(_FULL_CHARS, _HALF_CHARS)

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """规范化空白字符：合并多空白行，去除首尾空白"""
        text = re.sub(r'[ \t]+', ' ', text)          # 合并空格/Tab
        text = re.sub(r'\n{3,}', '\n\n', text)        # 合并多余空行
        text = re.sub(r' +$', '', text, flags=re.MULTILINE)  # 去除行尾空格
        return text.strip()

    @staticmethod
    def normalize_punctuation(text: str) -> str:
        """规范化标点符号：全角→半角，统一中文标点"""
        text = text.translate(TextCleaner.FULL_TO_HALF)
        # 统一省略号
        text = re.sub(r'\.{3,}|…{1,}', '……', text)
        # 统一破折号
        text = re.sub(r'--+|——+', '——', text)
        return text

    @staticmethod
    def remove_artifacts(text: str) -> str:
        """去除常见噪声：HTML标签、特殊控制字符、页码标记等"""
        # HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 控制字符（保留换行和Tab）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        # Markdown图片语法
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        # 文献引用标记 [1], [2,3], [4-6]
        text = re.sub(r'\[\d+(?:[,，\-–—]\d+)*\]', '', text)
        return text

    @staticmethod
    def normalize_medical_terms(text: str) -> str:
        """规范化医药术语：统一常见同义词表达"""
        term_map = {
            r'副作用': '不良反应',
            r'副反应': '不良反应',
            r'毒副反应': '不良反应',
            r'胃食道反流': '胃食管反流',
            r'幽门螺旋杆菌': '幽门螺杆菌',
            r'幽门螺旋菌': '幽门螺杆菌',
            r'HP\b': '幽门螺杆菌',
            r'NSAIDs?': '非甾体抗炎药',
            r'NSAID': '非甾体抗炎药',
            r'T2DM': '2型糖尿病',
        }
        for pattern, replacement in term_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """中文分句：按句号、分号、换行等边界切分"""
        # 保留分隔符的分句
        sentences = re.split(r'(?<=[。！？；\n])(?![。！？；\n])', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    @staticmethod
    def detect_quality_issues(text: str) -> list[str]:
        """检测数据质量问题"""
        issues = []
        # 过短
        if len(text) < 100:
            issues.append("文本过短(<100字符)")
        # 过多数字
        digit_ratio = sum(c.isdigit() for c in text) / max(len(text), 1)
        if digit_ratio > 0.3:
            issues.append(f"数字比例过高({digit_ratio:.1%})")
        # 过多英文
        ascii_ratio = sum(c.isascii() and c.isalpha() for c in text) / max(len(text), 1)
        if ascii_ratio > 0.5:
            issues.append(f"英文字母比例过高({ascii_ratio:.1%})")
        # 缺失关键信息
        if not re.search(r'适应|治疗|作用|用于', text):
            issues.append("可能缺少适应症/功能描述")
        return issues


def clean_document(doc: dict) -> dict:
    """清洗单个文档"""
    cleaner = TextCleaner()
    original = doc.get("content", "")

    # 清洗流水线
    cleaned = original
    cleaned = cleaner.remove_artifacts(cleaned)
    cleaned = cleaner.normalize_punctuation(cleaned)
    cleaned = cleaner.normalize_whitespace(cleaned)
    cleaned = cleaner.normalize_medical_terms(cleaned)

    # 分句
    sentences = cleaner.split_sentences(cleaned)

    # 质量检测
    quality_issues = cleaner.detect_quality_issues(cleaned)

    # 统计
    original_words = len(original)
    cleaned_words = len(cleaned)
    words_removed = original_words - cleaned_words

    return {
        **doc,  # 保留原始字段
        "original_content": original,
        "content": cleaned,
        "sentence_count": len(sentences),
        "sentences": sentences,
        "original_words": original_words,
        "cleaned_words": cleaned_words,
        "words_removed": words_removed,
        "cleaning_ratio": f"{(1 - cleaned_words/max(original_words,1)) * 100:.1f}%",
        "quality_issues": quality_issues,
        "quality_score": "A" if len(quality_issues) == 0 else "B" if len(quality_issues) <= 2 else "C",
        "cleaned_at": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="MedKB-AI 数据清洗管道")
    parser.add_argument("--input", type=Path, default=RAW_DIR / "corpus_sample.json",
                        help="输入JSON文件路径")
    parser.add_argument("--output", type=Path, help="输出JSON文件路径")
    args = parser.parse_args()

    print("=" * 60)
    print("MedKB-AI 数据清洗管道")
    print("=" * 60)

    # 加载
    if not args.input.exists():
        print(f"❌ 输入文件不存在: {args.input}")
        print("   请先运行 python src/scraper.py")
        return

    with open(args.input, "r", encoding="utf-8") as f:
        documents = json.load(f)

    print(f"\n📥 加载文档: {len(documents)} 篇")

    # 清洗
    cleaned_docs = [clean_document(doc) for doc in documents]

    # 统计
    total_original = sum(d["original_words"] for d in cleaned_docs)
    total_cleaned = sum(d["cleaned_words"] for d in cleaned_docs)
    total_sentences = sum(d["sentence_count"] for d in cleaned_docs)
    quality_dist = {"A": 0, "B": 0, "C": 0}
    for d in cleaned_docs:
        quality_dist[d["quality_score"]] += 1

    # 保存
    output_path = args.output or CLEANED_DIR / "corpus_cleaned.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_docs, f, ensure_ascii=False, indent=2)

    print(f"\n📊 清洗统计:")
    print(f"   原始总字数:   {total_original:,}")
    print(f"   清洗后字数:   {total_cleaned:,}")
    print(f"   去除字数:     {total_original - total_cleaned:,}")
    print(f"   总句子数:     {total_sentences:,}")
    print(f"   质量分布:     A级:{quality_dist['A']} B级:{quality_dist['B']} C级:{quality_dist['C']}")

    for i, doc in enumerate(cleaned_docs, 1):
        issues = doc["quality_issues"]
        if issues:
            print(f"\n   ⚠️  [{doc['doc_id']}] {doc['title']}")
            for issue in issues:
                print(f"       - {issue}")

    print(f"\n   输出文件:     {output_path}")
    print(f"\n✅ 数据清洗完成！")


if __name__ == "__main__":
    main()

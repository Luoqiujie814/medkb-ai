"""
MedKB-AI Web API 服务

FastAPI 后端，提供 RESTful API + 静态页面服务

使用：
  python src/web_server.py
  python src/web_server.py --port 8080
  python src/web_server.py --reload   (开发模式热重载)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ---------- FastAPI App ----------
from fastapi import FastAPI, Query as FastQuery
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from query_engine import QueryEngine
from validator import QualityValidator

DB_PATH = ROOT / "db" / "medkb.db"
STATIC_DIR = ROOT / "src" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="MedKB-AI API",
    description="医药知识治理与智能问答系统 - Web API",
    version="1.0.0",
)


def get_engine():
    engine = QueryEngine(DB_PATH)
    engine.connect()
    return engine


# ============================================================
# API 路由
# ============================================================

@app.get("/api/stats")
def api_stats():
    """知识库统计"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建，请先运行 kb_builder.py"}
    engine = get_engine()
    try:
        stats = engine.get_statistics()
        # 额外：质检统计
        validator = QualityValidator(DB_PATH)
        validator.connect()
        issues = validator.run_all_checks()
        validator.close()
        stats["quality_issues"] = len(issues)
        stats["quality_score"] = "A" if len([i for i in issues if i["severity"] == "fail"]) == 0 else "B"
        return stats
    finally:
        engine.close()


@app.get("/api/drugs")
def api_drugs_list():
    """药品列表"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        drugs = engine.conn.execute(
            "SELECT drug_id, name, generic_name, category FROM drugs ORDER BY name"
        ).fetchall()
        return {"drugs": [dict(row) for row in drugs]}
    finally:
        engine.close()


@app.get("/api/drugs/{name}")
def api_drug_detail(name: str):
    """药品详情"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        result = engine.search_drug(name)
        # 处理 Row 对象 → dict
        if result.get("found"):
            result["indications"] = _rows_to_dicts(result.get("indications", []))
            result["adverse_effects"] = _rows_to_dicts(result.get("adverse_effects", []))
            result["drug_interactions"] = _rows_to_dicts(result.get("drug_interactions", []))
        return result
    finally:
        engine.close()


@app.get("/api/diseases")
def api_diseases_list():
    """疾病列表"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        diseases = engine.conn.execute(
            "SELECT disease_id, name, category FROM diseases ORDER BY name"
        ).fetchall()
        return {"diseases": [dict(row) for row in diseases]}
    finally:
        engine.close()


@app.get("/api/diseases/{name}")
def api_disease_detail(name: str):
    """疾病详情"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        result = engine.search_disease(name)
        if result.get("found"):
            result["drugs"] = _rows_to_dicts(result.get("drugs", []))
        return result
    finally:
        engine.close()


@app.get("/api/interactions")
def api_check_interaction(
    drug_a: str = FastQuery(..., description="药品A名称"),
    drug_b: str = FastQuery(..., description="药品B名称"),
):
    """药物相互作用查询"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        return engine.check_interaction(drug_a, drug_b)
    finally:
        engine.close()


@app.get("/api/search")
def api_fulltext_search(q: str = FastQuery(..., description="搜索关键词")):
    """全文搜索"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        result = engine.full_text_search(q)
        return result
    finally:
        engine.close()


@app.get("/api/drugs/{name}/graph")
def api_drug_graph(name: str):
    """药品知识图谱数据（前端可视化用）"""
    if not DB_PATH.exists():
        return {"error": "数据库未构建"}
    engine = get_engine()
    try:
        drug = engine.search_drug(name)
        if not drug.get("found"):
            return {"error": f"未找到药品: {name}"}

        nodes = []
        links = []

        # 中心药品节点
        drug_id = f"drug_{drug['name']}"
        nodes.append({
            "id": drug_id,
            "name": drug["name"],
            "type": "drug",
            "category": drug.get("category", ""),
        })

        # 适应症 → 疾病节点
        for ind in _rows_to_dicts(drug.get("indications", [])):
            disease_name = ind.get("disease_name", "")
            if disease_name:
                did = f"disease_{disease_name}"
                if did not in [n["id"] for n in nodes]:
                    nodes.append({"id": did, "name": disease_name, "type": "disease",
                                  "category": ind.get("disease_category", "")})
                links.append({
                    "source": drug_id, "target": did,
                    "type": "indication",
                    "label": "一线" if ind.get("is_first_line") else "治疗",
                    "evidence": ind.get("evidence_level", ""),
                })

        # 不良反应节点
        for ae in _rows_to_dicts(drug.get("adverse_effects", [])):
            effect_name = ae.get("effect_name", "")
            if effect_name:
                eid = f"effect_{effect_name}"
                nodes.append({"id": eid, "name": effect_name, "type": "adverse_effect",
                              "severity": ae.get("severity", ""),
                              "body_system": ae.get("body_system", "")})
                links.append({
                    "source": drug_id, "target": eid,
                    "type": "adverse_effect",
                    "label": ae.get("frequency", ""),
                    "severity": ae.get("severity", ""),
                })

        # 相互作用 → 药品节点
        for inter in _rows_to_dicts(drug.get("drug_interactions", [])):
            target_name = inter.get("drug_b_name", "")
            if target_name:
                tid = f"drug_{target_name}"
                if tid not in [n["id"] for n in nodes]:
                    nodes.append({"id": tid, "name": target_name, "type": "drug",
                                  "category": "相互作用药品"})
                links.append({
                    "source": drug_id, "target": tid,
                    "type": "drug_interaction",
                    "label": inter.get("interaction_type", ""),
                    "severity": inter.get("severity_level", ""),
                })

        return {"nodes": nodes, "links": links}
    finally:
        engine.close()


# ---------- 静态文件 ----------

@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------- 工具函数 ----------

def _rows_to_dicts(rows):
    """将 sqlite3.Row 列表转为普通 dict 列表"""
    if not rows:
        return []
    result = []
    for row in rows:
        try:
            result.append(dict(row))
        except Exception:
            result.append(row)
    return result


# ---------- 启动入口 ----------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MedKB-AI Web 服务")
    parser.add_argument("--port", type=int, default=8000, help="端口号 (默认: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认: 127.0.0.1)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    print("=" * 60)
    print("  MedKB-AI Web 服务")
    print("=" * 60)
    print(f"\n  🌐 地址: http://{args.host}:{args.port}")
    print(f"  📖 API文档: http://{args.host}:{args.port}/docs")
    print(f"  📊 前端页面: http://{args.host}:{args.port}/")
    print(f"\n  按 Ctrl+C 停止服务\n")

    uvicorn.run(
        "web_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

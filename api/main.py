"""
宝可梦助手 API 服务
提供查询、伤害计算和聊天功能

路由已拆分到 routers/ 目录：
- routers/auth.py: 认证（注册/登录/同步）
- routers/chat.py: 聊天（普通/流式/标题）
- routers/search.py: 搜索（宝可梦/招式/道具）
- routers/home.py: HOME 使用率排名

数据模型在 schemas.py
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import date
from dotenv import load_dotenv
import asyncio
import concurrent.futures
import json
import os
import sqlite3
import sys

# 加载环境变量（兼容从项目根目录启动）
_API_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_API_DIR, ".env"))

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 添加 damage_calculator 目录到路径
DAMAGE_CALC_DIR = os.path.join(PROJECT_ROOT, "damage_calculator")
sys.path.insert(0, DAMAGE_CALC_DIR)

from cale_chinese_calculator import CaleChineseDamageCalculator as ChineseDamageCalculator
from api.query_service import PokemonQueryService
from api.chat_service import ChatService
from api.llm_service import LLMService
from api.auth_service import AuthService
from api.alias_service import AliasService
from api.rag_service import RAGService
from api.user_pokemon_service import UserPokemonService
from pokemon_data.rag_graph.graph_db import GraphDB

# 路由
from api.routers import auth as auth_router
from api.routers import chat as chat_router
from api.routers import search as search_router
from api.routers import home as home_router
from api.schemas import FeedbackRequest, QueryRequest, DamageCalcRequest

app = FastAPI(
    title="宝可梦助手 API",
    description="提供宝可梦数据查询、伤害计算和智能对话功能",
    version="1.0.0"
)

# CORS 配置 - 允许安卓客户端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 静态文件挂载 ====================
POKEMON_DATA_DIR = os.path.join(PROJECT_ROOT, "pokemon_data")
APP_ICON_PATH = os.path.join(_API_DIR, "appicon.png")

@app.get("/appicon.png")
async def app_icon():
    """返回 App 图标"""
    if not os.path.exists(APP_ICON_PATH):
        raise HTTPException(status_code=404, detail="图标未找到")
    return FileResponse(APP_ICON_PATH, media_type="image/png")

app.mount("/static", StaticFiles(directory=POKEMON_DATA_DIR), name="static")

CALC_DIR = os.path.join(PROJECT_ROOT, "web", "calc")
app.mount("/calc", StaticFiles(directory=CALC_DIR, html=True), name="calc")

CALE_DIR = os.path.join(PROJECT_ROOT, "web", "cale")
app.mount("/cale", StaticFiles(directory=CALE_DIR, html=True), name="cale")

WEB_DIR = os.path.join(PROJECT_ROOT, "web")
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# ==================== 服务初始化 ====================
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")

alias_service = AliasService(db_path=DB_PATH)
damage_calc = ChineseDamageCalculator(db_path=DB_PATH, alias_resolver=alias_service.resolve)
query_service = PokemonQueryService(db_path=DB_PATH)

try:
    llm_service = LLMService()
except ValueError as e:
    print(f"警告: LLM 服务初始化失败 - {e}")
    print("将使用降级模式（规则匹配）")
    llm_service = None

auth_service = AuthService(db_path=DB_PATH)
user_pokemon_service = UserPokemonService(db_path=DB_PATH)
graph_db = GraphDB()

# 访问量统计
USERS_DB_PATH = auth_service.db_path

def _init_visit_stats_table():
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visit_stats (
            date TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

_init_visit_stats_table()


@app.middleware("http")
async def visit_counter_middleware(request: Request, call_next):
    """统计页面 + API 访问量"""
    response = await call_next(request)
    path = request.url.path
    should_count = (
        (path.startswith("/api/") and path != "/api/visit-stats")
        or path == "/"
        or path.endswith(".html")
        or path in ("/web", "/web/", "/calc", "/calc/", "/cale", "/cale/")
    )
    if should_count:
        try:
            today = date.today().isoformat()
            conn = sqlite3.connect(USERS_DB_PATH)
            conn.execute(
                "INSERT INTO visit_stats (date, count) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET count = count + 1",
                (today,),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    return response

# RAG 服务
try:
    rag_service = RAGService(
        db_path=DB_PATH,
        alias_service=alias_service,
        query_service=query_service,
        llm_service=llm_service,
    )
except Exception as e:
    print(f"警告: RAG 服务初始化失败 - {e}")
    print("查询功能将不可用")
    rag_service = None

# 聊天服务
chat_service = ChatService(
    query_service=query_service,
    damage_calc=damage_calc,
    llm_service=llm_service,
    rag_service=rag_service,
    user_pokemon_service=user_pokemon_service,
)

# ==================== 注册路由 ====================
auth_router.init_services(auth_service, user_pokemon_service)
chat_router.init_services(chat_service, llm_service, auth_router)
search_router.init_services(DB_PATH)
home_router.init_services(DB_PATH, PROJECT_ROOT)

app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(search_router.router)
app.include_router(home_router.router)


@app.on_event("shutdown")
async def shutdown_event():
    """关闭常驻 Node.js 计算器进程"""
    try:
        damage_calc.calc.shutdown()
    except Exception:
        pass


# ==================== 零散端点 ====================

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "message": "宝可梦助手 API",
        "version": "1.0.0",
        "endpoints": {
            "register": "/api/auth/register",
            "login": "/api/auth/login",
            "query": "/api/query",
            "damage_calc": "/api/damage-calc",
            "chat": "/api/chat"
        }
    }


@app.get("/download/app")
async def download_app():
    """下载安卓 APK（自动选取 app/ 目录下最新的 apk 文件）"""
    import glob
    apk_dir = os.path.join(PROJECT_ROOT, "mobile", "PokemonApp", "app")
    apk_files = glob.glob(os.path.join(apk_dir, "*.apk"))
    if not apk_files:
        raise HTTPException(status_code=404, detail="APK 文件未找到")
    latest_apk = max(apk_files, key=os.path.getmtime)
    filename = os.path.basename(latest_apk)
    return FileResponse(
        latest_apk,
        media_type="application/vnd.android.package-archive",
        filename=filename
    )


@app.post("/api/query")
async def query_pokemon_data(request: QueryRequest):
    """查询宝可梦数据（RAG 混合检索）"""
    try:
        if rag_service:
            result = rag_service.answer(request.query)
        else:
            result = query_service.intelligent_query(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/damage-calc")
async def calculate_damage(request: DamageCalcRequest):
    """计算宝可梦对战伤害"""
    try:
        calc_params = {
            "attacker_name": request.attacker_name,
            "defender_name": request.defender_name,
            "move_name": request.move_name,
        }
        if request.attacker_evs: calc_params["attacker_evs"] = request.attacker_evs
        if request.defender_evs: calc_params["defender_evs"] = request.defender_evs
        if request.attacker_nature: calc_params["attacker_nature"] = request.attacker_nature
        if request.defender_nature: calc_params["defender_nature"] = request.defender_nature
        if request.attacker_ability: calc_params["attacker_ability"] = request.attacker_ability
        if request.defender_ability: calc_params["defender_ability"] = request.defender_ability
        if request.attacker_item: calc_params["attacker_item"] = request.attacker_item
        if request.defender_item: calc_params["defender_item"] = request.defender_item
        if request.attacker_boosts: calc_params["attacker_boosts"] = request.attacker_boosts
        if request.defender_boosts: calc_params["defender_boosts"] = request.defender_boosts
        if request.attacker_status: calc_params["attacker_status"] = request.attacker_status
        if request.defender_status: calc_params["defender_status"] = request.defender_status
        if request.attacker_cur_hp is not None: calc_params["attacker_cur_hp"] = request.attacker_cur_hp
        if request.defender_cur_hp is not None: calc_params["defender_cur_hp"] = request.defender_cur_hp
        if request.attacker_tera_type: calc_params["attacker_tera_type"] = request.attacker_tera_type
        if request.defender_tera_type: calc_params["defender_tera_type"] = request.defender_tera_type
        if request.weather: calc_params["weather"] = request.weather
        if request.terrain: calc_params["terrain"] = request.terrain
        if request.is_critical_hit: calc_params["is_critical_hit"] = request.is_critical_hit
        if request.is_reflect: calc_params["is_reflect"] = request.is_reflect
        if request.is_light_screen: calc_params["is_light_screen"] = request.is_light_screen
        if request.generation: calc_params["generation"] = request.generation

        result = damage_calc.calculate_chinese(**calc_params)

        if result.get("success"):
            return {
                "success": True,
                "damage_range": result.get("damageRange"),
                "description": result.get("description"),
                "ko_chance": result.get("kochance", {}).get("text"),
                "attacker": result.get("attacker"),
                "defender": result.get("defender"),
                "raw_damage": result.get("damage")
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "计算失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/rebuild-index")
async def rebuild_index():
    """重建 RAG 向量索引"""
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG 服务未初始化")
    try:
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        await loop.run_in_executor(executor, rag_service.rebuild_index)
        return {"success": True, "message": f"索引重建完成，共 {rag_service.index.ntotal} 个向量"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visit-stats")
async def get_visit_stats():
    """返回今日访问量和累计访问量"""
    try:
        today = date.today().isoformat()
        conn = sqlite3.connect(USERS_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT count FROM visit_stats WHERE date = ?", (today,))
        row = cur.fetchone()
        today_count = row[0] if row else 0
        cur.execute("SELECT SUM(count) FROM visit_stats")
        row = cur.fetchone()
        total_count = row[0] if row else 0
        conn.close()
        return {"today": today_count, "total": total_count}
    except Exception as e:
        return {"today": 0, "total": 0}


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """接收用户反馈，将对话记录写入本地 feedback 日志文件"""
    from datetime import datetime

    feedback_dir = os.path.join(_API_DIR, "feedback")
    os.makedirs(feedback_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(feedback_dir, f"feedback_{timestamp}.json")

    record = {
        "timestamp": datetime.now().isoformat(),
        "lang": request.lang,
        "context": [{"role": m.role, "content": m.content} for m in request.context],
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

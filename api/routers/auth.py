"""
认证路由：注册、登录、用户数据同步
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from ..schemas import AuthRequest, PokemonSyncRequest, TeamSyncRequest

router = APIRouter(prefix="/api", tags=["认证"])

# 服务引用（由 init_services 设置）
_auth_service = None
_user_pokemon_service = None


def init_services(auth_service, user_pokemon_service):
    """注入服务实例"""
    global _auth_service, _user_pokemon_service
    _auth_service = auth_service
    _user_pokemon_service = user_pokemon_service


def _get_user_id_optional(request: Request) -> Optional[int]:
    """从 Authorization header 提取 user_id，无 token 或无效时返回 None"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        info = _auth_service.verify_token(auth[7:])
        return info["user_id"]
    except Exception:
        return None


def _require_user_id(request: Request) -> int:
    """从 Authorization header 提取 user_id，无效时抛 401"""
    uid = _get_user_id_optional(request)
    if uid is None:
        raise HTTPException(status_code=401, detail="未登录或 Token 无效")
    return uid


@router.post("/auth/register")
async def register(request: AuthRequest):
    """用户注册"""
    try:
        _auth_service.register(request.username, request.password)
        return {"success": True, "message": "注册成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/login")
async def login(request: AuthRequest):
    """用户登录，返回 JWT Token"""
    try:
        result = _auth_service.login(request.username, request.password)
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/user/pokemon/sync")
async def sync_user_pokemon(body: PokemonSyncRequest, request: Request):
    """同步用户宝可梦配置（全量替换）"""
    uid = _require_user_id(request)
    _user_pokemon_service.sync_pokemon(uid, body.pokemon)
    return {"success": True, "count": len(body.pokemon)}


@router.post("/user/teams/sync")
async def sync_user_teams(body: TeamSyncRequest, request: Request):
    """同步用户队伍（全量替换）"""
    uid = _require_user_id(request)
    _user_pokemon_service.sync_teams(uid, body.teams)
    return {"success": True, "count": len(body.teams)}

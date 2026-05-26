"""
Pydantic 数据模型 - 请求/响应结构定义
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any


class QueryRequest(BaseModel):
    """查询请求"""
    query: str = Field(
        ...,
        description="用户的查询问题",
        example="查询喷火龙的种族值"
    )


class DamageCalcRequest(BaseModel):
    """伤害计算请求"""
    attacker_name: str = Field(..., description="攻击方宝可梦名称", example="盖欧卡")
    defender_name: str = Field(..., description="防御方宝可梦名称", example="固拉多")
    move_name: str = Field(..., description="招式名称", example="冲浪")

    # 努力值
    attacker_evs: Optional[Dict[str, int]] = Field(
        None,
        description="攻击方努力值",
        example={"hp": 4, "atk": 0, "def": 0, "spa": 252, "spd": 0, "spe": 252}
    )
    defender_evs: Optional[Dict[str, int]] = Field(
        None,
        description="防御方努力值",
        example={"hp": 252, "atk": 0, "def": 0, "spa": 0, "spd": 4, "spe": 252}
    )

    # 性格
    attacker_nature: Optional[str] = Field(None, description="攻击方性格", example="胆小")
    defender_nature: Optional[str] = Field(None, description="防御方性格", example="固执")

    # 特性
    attacker_ability: Optional[str] = Field(None, description="攻击方特性", example="始源之海")
    defender_ability: Optional[str] = Field(None, description="防御方特性", example="日照")

    # 道具
    attacker_item: Optional[str] = Field(None, description="攻击方道具", example="讲究眼镜")
    defender_item: Optional[str] = Field(None, description="防御方道具", example="突击背心")

    # 能力变化
    attacker_boosts: Optional[Dict[str, int]] = Field(
        None,
        description="攻击方能力变化（-6 到 +6）",
        example={"atk": 0, "def": 0, "spa": 1, "spd": 0, "spe": 0}
    )
    defender_boosts: Optional[Dict[str, int]] = Field(
        None,
        description="防御方能力变化（-6 到 +6）",
        example={"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    )

    # 状态
    attacker_status: Optional[str] = Field(None, description="攻击方状态（烧伤/麻痹/中毒/剧毒/睡眠/冰冻）", example="")
    defender_status: Optional[str] = Field(None, description="防御方状态", example="")

    # 当前HP
    attacker_cur_hp: Optional[int] = Field(100, description="攻击方当前HP百分比（0-100）", example=100)
    defender_cur_hp: Optional[int] = Field(100, description="防御方当前HP百分比（0-100）", example=100)

    # 太晶
    attacker_tera_type: Optional[str] = Field(None, description="攻击方太晶属性", example="水")
    defender_tera_type: Optional[str] = Field(None, description="防御方太晶属性", example="")

    # 场地效果
    weather: Optional[str] = Field(None, description="天气（大晴天/大雨/沙暴/雪/终极强光/始源大海）", example="大雨")
    terrain: Optional[str] = Field(None, description="场地（电气场地/青草场地/精神场地/薄雾场地）", example="")

    # 其他
    is_critical_hit: Optional[bool] = Field(False, description="是否急所", example=False)
    is_reflect: Optional[bool] = Field(False, description="是否有反射壁", example=False)
    is_light_screen: Optional[bool] = Field(False, description="是否有光墙", example=False)
    generation: Optional[int] = Field(10, description="世代（10=Champions）", example=10)


class AuthRequest(BaseModel):
    """注册/登录请求"""
    username: str = Field(..., description="用户名", example="trainer01")
    password: str = Field(..., description="密码", example="pikachu123")


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色：user 或 assistant", example="user")
    content: str = Field(..., description="消息内容", example="盖欧卡对固拉多使用冲浪")


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息", example="盖欧卡对固拉多使用冲浪")
    context: Optional[List[ChatMessage]] = Field(None, description="对话历史上下文（可选）")
    model: Optional[str] = Field(None, description="对话模型（可选，覆盖服务器默认值）")
    tool_model: Optional[str] = Field(None, description="Tool Use 模型（可选，覆盖服务器默认值）")
    debug: Optional[bool] = Field(False, description="调试模式：返回每次 LLM 调用的 messages（测试用）")
    platform: Optional[str] = Field(None, description="客户端平台：mobile / web（影响伤害计算器链接）")


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    context: List[ChatMessage] = Field(..., description="本次对话记录")
    lang: Optional[str] = Field("zh", description="用户语言")


class TitleRequest(BaseModel):
    """标题生成请求"""
    messages: List[Dict[str, str]] = Field(..., description="对话消息列表，每条含 role 和 content")


class PokemonSyncRequest(BaseModel):
    pokemon: List[Dict[str, Any]]


class TeamSyncRequest(BaseModel):
    teams: List[Dict[str, Any]]

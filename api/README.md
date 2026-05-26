# 宝可梦助手 API

基于 FastAPI 的宝可梦数据查询和伤害计算 API 服务，为安卓客户端提供后端支持。

## 功能特性

- **智能聊天接口**: 自动识别用户意图，路由到查询或计算功能
- **数据查询**: 查询宝可梦种族值、招式、特性、道具、属性克制等信息
- **伤害计算**: 精确计算宝可梦对战伤害，支持完整的对战参数配置
- **中文支持**: 全面支持中文名称、拼音输入和自然语言交互（谐音/拼音自动匹配）

## 快速开始

### 验证环境

在启动服务前，先运行验证脚本检查环境：

```bash
cd api
python verify.py
```

如果所有检查通过，继续下一步。

### 安装依赖

```bash
# 从项目根目录安装
pip install -r requirements.txt
```

### 启动服务

**方式 1: 使用启动脚本（推荐，从项目根目录）**

```bash
bash start.sh
```

**方式 2: 直接运行（从项目根目录）**

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

服务将在 `http://localhost:8000` 启动

> **注意**：服务启动后，首次伤害计算请求会自动启动一个常驻 Node.js 进程（`PersistentNodeProcess`），后续计算复用该进程（单次 ~1ms）。服务关闭时自动清理该进程。

### 测试服务

**方式 1: 使用测试脚本**

打开新终端运行：
```bash
python test_api.py
```

**方式 2: 使用浏览器（推荐）**

访问交互式 API 文档，可以直接在浏览器中测试所有接口：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

详细测试方法见 [TEST.md](TEST.md)

### 查看 API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 接口

### 1. 用户注册 `/api/auth/register`

**POST** 请求，注册新用户

```json
{
  "username": "trainer01",
  "password": "pikachu123"
}
```

**成功响应** (200):
```json
{
  "success": true,
  "message": "注册成功"
}
```

**失败响应** (400): 用户名已存在、密码过短等

### 2. 用户登录 `/api/auth/login`

**POST** 请求，登录并获取 JWT Token

```json
{
  "username": "trainer01",
  "password": "pikachu123"
}
```

**成功响应** (200):
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "trainer01"
}
```

**失败响应** (401): 用户名或密码错误

### 2.5 用户宝可梦同步 `/api/user/pokemon/sync`

**POST** 请求，全量替换用户已保存的宝可梦配置。需要 Authorization header。

```
Authorization: Bearer <token>
```

```json
{
  "pokemon": [
    {
      "name": "妙蛙花", "name_en": "Venusaur",
      "base_hp": 80, "base_attack": 82, "base_defense": 83,
      "base_sp_attack": 100, "base_sp_defense": 100, "base_speed": 80,
      "ev_hp": 0, "ev_attack": 0, "ev_defense": 0,
      "ev_sp_attack": 32, "ev_sp_defense": 2, "ev_speed": 32,
      "nature": "内敛", "ability": "茂盛", "item": "生命宝珠",
      "move1": "飞叶风暴", "move2": "污泥炸弹", "move3": "催眠粉", "move4": "大地之力"
    }
  ]
}
```

### 2.6 用户队伍同步 `/api/user/teams/sync`

**POST** 请求，全量替换用户队伍。需要 Authorization header。

```json
{
  "teams": [
    { "name": "晴天队", "members": ["妙蛙花", "喷火龙", "固拉多"] }
  ]
}
```

### 3. 智能聊天 `/api/chat`

**POST** 请求，自动识别意图并返回结果

```json
{
  "message": "盖欧卡对固拉多使用根源波动",
  "context": [],       // 可选，对话历史
  "model": "",         // 可选，对话模型（意图识别/结果总结），覆盖服务器默认值
  "tool_model": "",    // 可选，计算模型（伤害参数提取 Tool Use），覆盖服务器默认值
  "debug": false,      // 可选，调试模式：响应中附带每次 LLM 调用的完整 messages（仅测试用，生产不传）
  "platform": "mobile" // 可选，客户端平台：mobile / web（影响伤害计算器链接：mobile→mobile.html，其他→index_zh.html）
}
```

**响应示例**:
```json
{
  "success": true,
  "type": "damage_calc",
  "response": "252特攻盖欧卡的根源波动对252HP固拉多造成 85-100% 伤害\n有 6.3% 概率一击击倒",
  "data": {
    "damage_range": [340, 402],
    "ko_chance": {...}
  }
}
```

### 4. 流式聊天 `/api/chat/stream`

**POST** 请求，SSE 流式推送回复（供安卓客户端使用）

请求格式与 `/api/chat` 相同，同样支持 `model`、`tool_model`、`platform` 字段：
```json
{
  "message": "查询喷火龙的种族值",
  "context": [],
  "model": "claude-sonnet-4-6",
  "tool_model": "claude-sonnet-4-6",
  "platform": "mobile"
}
```

**响应格式**: `text/event-stream`，逐字推送：
```
data: 【
data: 喷
data: 火
data: 龙
data: 】
...
data: [DONE]
```

客户端通过 SSE 协议接收，实现打字机效果。

### 5. 对话标题生成 `/api/chat/title`

**POST** 请求，根据对话内容用 LLM 生成简短标题（供客户端自动命名对话）

```json
{
  "messages": [
    {"role": "user", "content": "盖欧卡对固拉多使用根源波动能秒吗"},
    {"role": "assistant", "content": "..."}
  ]
}
```

**响应示例**:
```json
{
  "success": true,
  "title": "盖欧卡根源波动伤害计算"
}
```

取前 3 条消息概括主题，标题不超过 15 字。LLM 服务未初始化时返回 `{"success": false, "title": ""}`。

### 6. 宝可梦搜索 `/api/pokemon/search`

**GET** 请求，按名称模糊搜索宝可梦（中英日名称、拼音、首字母缩写、别名均可）

```
GET /api/pokemon/search?keyword=妙蛙&limit=20
GET /api/pokemon/search?keyword=mwzz       # 拼音首字母：妙蛙种子
GET /api/pokemon/search?keyword=老喷        # 别名：老喷
```

**响应示例**:
```json
{
  "results": [
    {
      "pokedex_id": 1,
      "name_zh": "妙蛙种子",
      "name_en": "Bulbasaur",
      "name_ja": "フシギダネ",
      "type1": "grass", "type2": "poison",
      "ability1_name": "茂盛", "ability2_name": null, "hidden_ability_name": "叶绿素",
      "hp": 45, "attack": 49, "defense": 49, "sp_attack": 65, "sp_defense": 65, "speed": 45,
      "image_official_artwork": "pokemonImage/001-bulbasaur-officialArtwork.png"
    }
  ]
}
```

### 7. 宝可梦详情 `/api/pokemon/{pokedex_id}`

**GET** 请求，按图鉴编号获取宝可梦完整数据

```
GET /api/pokemon/6
```

响应格式与搜索结果单条相同。

### 8. 招式搜索 `/api/moves/search`

**GET** 请求，按名称模糊搜索招式（中英日名称、拼音、首字母缩写均可，可选按宝可梦过滤可学招式）

```
GET /api/moves/search?keyword=地震&pokedex_id=6&limit=20
GET /api/moves/search?keyword=dz          # 拼音首字母：地震
```

- `keyword`：搜索关键词（中英日名称 / 拼音全拼 / 首字母缩写）
- `pokedex_id`（可选）：传入时只返回该宝可梦在朱紫可学的招式

**响应示例**:
```json
{
  "results": [
    {
      "id": 89,
      "name_zh": "地震",
      "name_en": "Earthquake",
      "name_ja": "じしん",
      "type": "ground",
      "damage_class": "physical",
      "power": 100,
      "accuracy": 100
    }
  ]
}
```

### 9. 道具搜索 `/api/items/search`

**GET** 请求，按名称模糊搜索道具（中英日名称、拼音、首字母缩写、别名均可，只返回有中文名的道具）

```
GET /api/items/search?keyword=围巾&limit=20
GET /api/items/search?keyword=wj           # 拼音首字母（别名"围巾"）→ 讲究围巾
```

**响应示例**:
```json
{
  "results": [
    {
      "id": 287,
      "name_zh": "精选围巾",
      "name_en": "choice-scarf",
      "name_ja": "こだわりスカーフ",
      "category": "held-items",
      "image_path": "heldItemImage/choice-scarf.png"
    }
  ]
}
```

### 10. 数据查询 `/api/query`

**POST** 请求，查询宝可梦相关数据

```json
{
  "query": "查询喷火龙的种族值"
}
```

**响应示例**:
```json
{
  "success": true,
  "query_type": "pokemon",
  "data": [
    {
      "name_zh": "喷火龙",
      "hp": 78,
      "attack": 84,
      "defense": 78,
      "sp_attack": 109,
      "sp_defense": 85,
      "speed": 100
    }
  ],
  "message": "查询成功"
}
```

### 11. 访问量统计 `/api/visit-stats`

**GET** 请求，返回今日访问量和累计访问量

```
GET /api/visit-stats
```

**响应示例**:
```json
{
  "today": 42,
  "total": 1234
}
```

统计范围：所有 API 接口调用（`/api/*`）和页面访问（`.html`、根路径 `/`、网页目录 `/web`、`/calc`、`/cale`），不含静态资源。数据存储在 `users.db` 的 `visit_stats` 表中，避免 `pokemonData.db` 同步时被覆盖。

### 12. 用户反馈 `/api/feedback`

**POST** 请求，提交本次对话记录作为问题反馈

```json
{
  "context": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "lang": "zh"
}
```

**响应示例**:
```json
{ "success": true }
```

反馈记录以 JSON 文件保存到 `api/feedback/` 目录，文件名格式为 `feedback_YYYYMMDD_HHMMSS_ffffff.json`，包含时间戳、语言和完整对话内容。

### 13. 使用率排名 `/api/home/usage`

**GET** 请求，获取宝可梦使用率排名数据

```
GET /api/home/usage?source=champions&season=0&rule=0
GET /api/home/usage?source=sv&season=39&rule=1
```

- `source`：数据源，`champions`（默认）或 `sv`
- `season`：赛季号，`0` 表示最新赛季（默认）
- `rule`：`0`=单打（默认），`1`=双打

**响应示例**:
```json
{
  "seasons": [1, 2],
  "current_season": 2,
  "rankings": [
    {
      "rank": 1,
      "pokemon_id": "0445-00",
      "pokemon_name": "ガブリアス",
      "image_url": "https://s3-ap-northeast-1.amazonaws.com/pokedb.tokyo/champs/assets/pokemon/icons_128/pokemon-0445-00.webp"
    }
  ],
  "source": "champions",
  "rule": 0
}
```

### 14. 宝可梦详情 `/api/home/pokemon-detail`

**GET** 请求，获取单个宝可梦的详细使用率数据（种族值、特性、道具、招式、性格、太晶属性、可学招式表）

```
GET /api/home/pokemon-detail?pokemon_id=0006-00&source=champions&season=0&rule=0
```

- `pokemon_id`：宝可梦 ID（格式 `NNNN-FF`，来自排名接口）
- `source`：数据源，`champions`（默认）或 `sv`
- `season`：赛季号，`0` 表示最新赛季（默认）
- `rule`：`0`=单打（默认），`1`=双打

**响应示例**:
```json
{
  "pokemon_id": "0006-00",
  "rank": 5,
  "current_form": { "name_zh": "喷火龙", "name_en": "charizard" },
  "forms": [
    {
      "home_id": "0006-00",
      "name_zh": "喷火龙", "name_en": "charizard",
      "image_url": "/static/pokemonImage/006-charizard-officialArtwork.png",
      "hp": 78, "attack": 84, "defense": 78,
      "sp_attack": 109, "sp_defense": 85, "speed": 100, "total_stats": 534,
      "type1": "fire", "type2": "flying",
      "ability1": "猛火", "ability2": null, "hidden_ability": "太阳之力",
      "is_default": true,
      "has_moves": true
    }
  ],
  "usage": {
    "abilities": [{ "name": "猛火", "rate": 86.7, "name_zh": "猛火" }],
    "items": [{ "name": "喷火龙进化石Y", "rate": 62.3, "name_zh": "喷火龙进化石Y" }],
    "moves": [{ "name": "热风", "rate": 59.6, "name_zh": "热风", "name_en": "heat-wave" }],
    "personalities": [{ "name": "内敛", "rate": 31.9, "name_zh": "内敛" }],
    "tera_types": [{ "name": "火", "rate": 59.6, "name_zh": "火属性" }]
  },
  "moves": [{ "name_zh": "热风", "name_en": "heat-wave", "learn_method": "Champions" }],
  "seasons": [2, 1],
  "current_season": 2,
  "source": "champions",
  "rule": 0
}
```

**forms 字段说明**:
- `home_id`：形态 ID（格式 `NNNN-FF`，如 `0006-00`）
- `has_moves`：该形态是否有独立技能池（查询 `pokemon_moves_champions` 或 `pokemon_moves_sv` 表）。`true` 表示有独立技能池（如洛托姆各形态），不能从其他形态切换到该形态；`false` 表示没有独立技能池（如 Mega 进化），可以从其他形态切换到该形态

### 15. 伤害计算 `/api/damage-calc`

**POST** 请求，精确计算对战伤害

```json
{
  "attacker_name": "盖欧卡",
  "defender_name": "固拉多",
  "move_name": "根源波动",
  "attacker_evs": {"spa": 252, "spe": 252, "hp": 4},
  "attacker_nature": "胆小",
  "weather": "大雨"
}
```

**完整参数列表**:
- `attacker_name`, `defender_name`, `move_name`: 必需
- `attacker_evs`, `defender_evs`: 努力值分配
- `attacker_nature`, `defender_nature`: 性格
- `attacker_ability`, `defender_ability`: 特性
- `attacker_item`, `defender_item`: 道具
- `attacker_boosts`, `defender_boosts`: 能力变化 (-6 到 +6)
- `attacker_status`, `defender_status`: 状态异常
- `attacker_cur_hp`, `defender_cur_hp`: 当前HP百分比
- `attacker_tera_type`, `defender_tera_type`: 太晶属性
- `attacker_is_terastallized`, `defender_is_terastallized`: 是否开启太晶化
- `weather`: 天气（大晴天/大雨/沙暴/雪等）
- `terrain`: 场地（电气场地/青草场地等）
- `is_critical_hit`: 是否急所
- `is_reflect`, `is_light_screen`: 是否有反射壁/光墙
- `is_aurora_veil`: 是否有极光幕
- `generation`: 世代（默认10，宝可梦冠军）
- `mode`: 对战模式（`Singles` 单打 / `Doubles` 双打，默认双打）

**响应示例**:
```json
{
  "success": true,
  "damage_range": [340, 402],
  "description": "252特攻盖欧卡的根源波动对252HP固拉多造成 85-100% 伤害",
  "ko_chance": "有 6.3% 概率一击击倒",
  "attacker": {...},
  "defender": {...}
}
```

## 项目结构

```
api/
├── main.py              # FastAPI 主入口（服务初始化 + 中间件 + 零散端点 + Router 注册）
├── schemas.py           # Pydantic 数据模型（请求/响应结构定义）
├── routers/             # API 路由（按功能拆分）
│   ├── __init__.py
│   ├── auth.py              # 认证路由（注册/登录/同步）
│   ├── chat.py              # 聊天路由（普通/流式/标题生成）
│   ├── search.py            # 搜索路由（宝可梦/招式/道具/Mega石）
│   └── home.py              # HOME 路由（使用率排名/宝可梦详情）
├── auth_service.py      # 用户认证服务（注册/登录/JWT）
├── user_pokemon_service.py # 用户宝可梦/队伍同步服务（存 users.db，按 user_id 隔离）
├── alias_service.py     # 别名解析服务（基于 battle_terms 精确索引 + rapidfuzz 模糊匹配 + 拼音匹配）
├── rag_index.py         # RAG 索引构建器（从数据库构建 FAISS 向量索引，含 wiki_sections 百科知识）
├── rag_service.py       # RAG 混合检索服务（语义检索 + 精确匹配 + LLM 答案生成）
├── query_service.py     # 数据查询服务（SQL 查询方法）
├── chat_service.py      # 智能聊天服务主入口（Agent Loop 路由，使用 Mixin 模式组合子模块）
├── chat/                # ChatService 拆分模块
│   ├── __init__.py
│   ├── text_processor.py    # 文本处理 Mixin（jieba 切词、拼音匹配、形态名 normalize、中英互译）
│   ├── damage_pipeline.py   # 伤害计算管线 Mixin（参数提取 → 计算执行 → 结果格式化）
│   ├── threshold_pipeline.py # 阈值计算管线 Mixin（攻击阈值 + 防御阈值搜索）
│   ├── calc_formatter.py    # 计算器格式化 Mixin（URL 构建 + 伤害结果格式化 + 润色文本）
│   ├── query_pipeline.py    # 查询管线 Mixin（查询处理 + 工具结果格式化）
│   ├── tool_executor.py     # 工具执行 Mixin（工具分发 + 能力值计算）
│   ├── wiki_tools.py        # Wiki 工具 Mixin（页面查找/读取/搜索）
│   └── home_queries.py      # HOME 查询 Mixin（使用率排名/详情/队伍）
├── llm_service.py       # LLM 服务封装（Agent Loop 核心 + 工具标签/展示）
├── task_planner.py      # 任务规划器（复杂问题拆分执行，create_plan 工具）
├── llm/                 # LLM 模块（独立函数）
│   ├── __init__.py
│   ├── helpers.py           # 共享工具函数（load_prompt/load_tools/extra_params）
│   ├── rejection.py         # 内容安全拒绝检测
│   ├── param_extractors.py  # 参数提取（伤害计算/阈值搜索）
│   └── summarizers.py       # 结果总结（查询/伤害/阈值）
├── vocabulary_loader.py # 名词库加载器（从数据库加载）
├── prompt/              # LLM 提示词与 Tool Schema（可直接编辑，无需改代码）
│   ├── llm1_unified.txt                 # Agent Loop 统一提示词（含工具选择指引 + 禁止凭记忆答数值/关系）
│   ├── llm2_damage_params.txt           # LLM#2 伤害参数提取提示词
│   ├── llm2_damage_calculator_tool.json # LLM#2 damage_calculator tool schema
│   ├── llm2b_query_tools.txt            # 查询工具路由提示词（含 wiki 工具规则）
│   ├── llm2b_query_tools.json           # 23个查询+百科 tools schema（含 search_stat/status/type/nature、fetch_wiki_page、search_wiki、stat_calculator、get_home_rankings、get_pokemon_home_usage、get_home_teams）
│   ├── llm3_damage_summary.txt          # LLM#3 伤害结果总结提示词
│   ├── llm_query_summary.txt            # 查询结果总结提示词（统一总结）
│   ├── llm2_threshold_tool.json         # 阈值参数提取 tool schema
│   ├── llm2_threshold_params.txt        # 阈值参数提取提示词
│   ├── llm3_threshold_summary.txt       # 阈值结果总结提示词
│   ├── create_plan_tool.json            # 任务规划器 tool schema（create_plan，最多8个子任务）
│   └── graph_extract_prompt.txt         # GraphRAG Step 5：通用语义关系抽取模板（已终止，代码保留）
├── data/                # RAG 索引数据（自动生成）
│   ├── rag.faiss        # FAISS 向量索引（~10MB）
│   └── rag_docs.pkl     # 文档元数据
├── feedback/            # 用户反馈记录（自动生成，每条反馈一个 JSON 文件）
├── .env.example         # 环境变量模板
├── README.md            # 本文档
├── README_LLM.md        # LLM 智能解析详细说明
└── test/                # 测试目录
    ├── test_questions.md        # 对话测试问题清单（100题）
    ├── test_questions_sv.md     # 朱紫版本测试问题清单
    ├── test_chat_questions.py   # 对话自动化测试脚本
    ├── profile_two_questions.py # 单题性能分析脚本
    └── responses/               # 测试回复存档（按时间戳分目录）
```

## 技术栈

- **FastAPI**: 现代高性能 Web 框架
- **Pydantic**: 数据验证和序列化
- **SQLite**: 宝可梦数据库
- **Uvicorn**: ASGI 服务器
- **LLM（OpenAI 兼容接口）**: 智能意图识别和参数提取（支持 DeepSeek / 智谱 GLM / Anthropic Claude；GLM 系列自动禁用深度思考避免 content 为空；默认 GLM-5，可通过 `.env` 切换）
- **sentence-transformers + FAISS**: RAG 混合检索（语义向量检索 + 精确匹配）
- **rapidfuzz**: 中文别名模糊匹配（top-5 候选，≥75分优先补位）
- **pypinyin**: 中文拼音转换（支持谐音/拼音输入自动匹配实体名称，三层匹配：battle_terms 精确 → name_zh 模糊 → 拼音精确+模糊）
- **bcrypt**: 密码安全哈希
- **python-jose**: JWT Token 生成与验证

## 开发说明

### 添加新接口

1. 在 `schemas.py` 中定义请求/响应模型
2. 在对应 `routers/` 文件中添加路由端点（或新建 router 文件并在 `main.py` 中注册）
3. 如需新服务，在 `main.py` 中初始化并注入到 router

### 聊天管线架构（Agent Loop）

```
用户输入
  │
  → RAG 检索（整句 + jieba 逐词，含 wiki_sections 百科知识）
  │
  → Agent Loop（最多 5 轮，首轮 tool_choice="required" 强制调工具）
  │   每轮 LLM 决策：
  │   ├─ 调普通查询工具（search_pokemon / search_moves / search_abilities / search_items / search_stat / search_status / search_type / search_nature / execute_sql / fetch_wiki_page / search_wiki / stat_calculator / get_home_rankings / get_pokemon_home_usage / get_home_teams 等）→ 执行 → 回填 → 下一轮
  │   ├─ 调 create_plan（任务规划器）→ 拆分多步任务 → 逐个执行 → 结果回填 → LLM 生成 final_answer
  │   ├─ 调终结性工具（damage_calculator / ev_threshold_calculator）→ 退出 loop → 独立管线
  │   └─ 输出 final_answer → 退出 loop
  │
  收尾：
  ├─ final_answer + 有工具历史 → LLM#3 总结（带 tool_history 上下文）
  ├─ final_answer + 无工具历史 → 直接返回（纯闲聊/常识）
  ├─ terminal_tool → 独立预处理管线（预处理 → 计算器 → 专用总结）
  └─ max_rounds → LLM#3 兜底总结

伤害计算管线（terminal_tool=damage_calculator）：
  共享检索 + loop 已查数据 → LLM#2(Tool Use) 伤害参数提取 → 计算器 → LLM#3 结果总结
  世代推断：LLM 显式指定 > 限定图鉴匹配（Champions→ZA→SV，从新到旧）> 全国图鉴 fallback > 报错
  生成多情况 scenarios（满攻 vs 无耐久 / 极攻 vs 极限耐久；天气/场地冲突时各情况展开）
  → 计算器执行 → LLM#3 总结（按天气/场地分组，每条情况输出格式化行；空内容自动 fallback 模板）
  → 附加在线计算器 markdown 链接（指向 NCP 计算器中文翻译版，支持宝可梦冠军）

阈值搜索管线（terminal_tool=ev_threshold_calculator）：
  共享检索 + loop 已查数据 → LLM#2t(Tool Use) 阈值参数提取 → 阈值扫描计算 → LLM#3t 结果总结
  世代推断同伤害管线；Gen 10 自动将 evs(0-252) 转换为 sps(0-32)
  攻击阈值：扫描能力点 0-32 找最低击杀投入；防御阈值：33×33 扫描 HP+防御找最低存活投入
  默认参数：LLM 未提取攻击/防御投入时，防御阈值默认攻击方极攻（满 sps + 加攻性格），攻击阈值默认防守方极限耐久（满 HP + 满防/spd + 加防性格）
```

**伤害计算输出格式**（LLM #3，含单打/双打模式说明）：
```
双打模式下，满攻配置下能一击秒杀，极限耐久配置下不能。

晴天：
满攻 vs 无耐久: 252 攻 绯红脉动 故勒顿 闪焰冲锋 vs. 0 HP / 0 防 盖欧卡[晴天] : 64-75 (36.6 - 42.9%) -- 确定 3次攻击击杀
极攻 vs 极限耐久: 252 攻 固执 绯红脉动 故勒顿 闪焰冲锋 vs. 252 HP / 252 防 慎重 盖欧卡[晴天] : 48-57 (27.4 - 32.5%) -- 确定 4次攻击击杀

雨天：
满攻 vs 无耐久: ...
极攻 vs 极限耐久: ...

🔗 [在线计算器](https://pokemonPokemon.github.io/VGC-Damage-Calculator-Chinese/?gen=9&p1=...&p2=...&move1=...&mode=Singles)
```

**阈值计算输出格式**（LLM #3t）：
```
防御阈值（攻击方默认极攻）：
  攻击方: 32能力点 Modest 雪妖女（超级进化） 暗影球 [Snow]
  推荐方案: HP+24(24能力点) / 特防+28(28能力点)，总投入=52能力点
  伤害: 134-158 (84.3%-99.4%)，确定两发击杀
  🔗 [在线计算器](...)

防御阈值（掉血百分比限制）：
  目标: 不被1确击杀，掉血不超过60%
  推荐方案: HP+25(196努力值) / 特防+15(116努力值)，总投入=40能力值
  伤害: 138-164 (55.2%-65.6%)，掉血不超过60%
  🔗 [在线计算器](...)

攻击阈值（防守方默认极限耐久）：
  防守方: 32 HP / 32 特防 Calm 耿鬼（超级进化） [Snow]
  最少投入: 特攻+14(14能力点) → 138-164 (102.2%-121.5%)，确定一发击杀
  满投入: 特攻+32(32能力点) → 152-180 (112.6%-133.3%)，确定一发击杀

攻击阈值（防守方无耐久）：
  防守方: 无耐久 耿鬼（超级进化）
  最少投入: 特攻+14(14能力点) → 138-164 (102.2%-121.5%)，确定一发击杀
  满投入: 特攻+32(32能力点) → 152-180 (112.6%-133.3%)，确定一发击杀
  🔗 [在线计算器](...)
```

**在线计算器 URL 参数**（由 `url_loader.js` 解析）：

| 参数 | 示例 | 说明 |
|---|---|---|
| `gen` | `10` | 世代 (1-10，默认 10 即宝可梦冠军) |
| `p1` / `p2` | `Koraidon` | 攻守方宝可梦英文名 |
| `move1`-`move4` | `Flare Blitz` | 攻击方招式 |
| `move2_1`-`move2_4` | `Water Spout` | 防守方招式 |
| `evs1` / `evs2` | `0,252,0,0,4,252` | 努力值 (hp,atk,def,spa,spd,spe) |
| `sps1` / `sps2` | `0,0,0,32,0,32` | 能力点 Gen 10 (hp,atk,def,spa,spd,spe, 0-32) |
| `nature1` / `nature2` | `Adamant` | 性格 |
| `ability1` / `ability2` | `Orichalcum Pulse` | 特性 |
| `item1` / `item2` | `Choice Band` | 道具 |
| `tera1` / `tera2` | `Fire` | 太晶属性 |
| `weather` | `Sun` | 天气 |
| `terrain` | `Electric` | 场地 |
| `status1` / `status2` | `Burned` | 状态 |
| `mode` | `Singles` / `Doubles` | 单打/双打（默认双打） |
```

**多情况 scenario 规则**：
- 满攻：攻击方满投资（Gen 10 为 32 点，Gen 1-9 为 252 EV），性格不加攻（认真）；防守方 0 投资
- 极攻：攻击方满投资 + 加攻性格（物理固执/特殊内敛）；防守方满 HP + 满防（Gen 10 为 32 点，Gen 1-9 为 252 EV）+ 加防性格
- 天气/场地冲突（如故勒顿 vs 盖欧卡）：每种天气下各展开满攻/极攻两种情况

**模型配置**：

开发者可通过 `.env` 修改默认模型：
```
LLM_MODEL=GLM-5                  # 控制 LLM #1 和 #3（支持 deepseek-chat / GLM-5 等；默认 GLM-5）
LLM_MODEL_TOOL_USE=GLM-5         # 控制 LLM #2（参数提取；默认 GLM-5）
DEEPSEEK_API_KEY=xxx             # API Key（变量名沿用，实际可对接任何 OpenAI 兼容服务）
DEEPSEEK_BASE_URL=https://open.bigmodel.cn/api/paas/v4/  # API Base URL
```

GLM 系列模型默认强制开启深度思考（thinking），会消耗全部 max_tokens 导致 content 为空。`llm_service.py` 会自动检测模型名以 `glm` 开头时传入 `thinking: {type: "disabled"}` 禁用深度思考。

切回 Anthropic 时，将 `llm_service.py` 中注释的 Anthropic 代码取消注释，并改用 `ANTHROPIC_API_KEY`。

**Fallback 链**：
| LLM 调用 | 失败时 fallback |
|----------|-----------------|
| LLM #1 失败 | 关键词匹配旧流程 |
| LLM #2 失败 | 返回友好错误提示 |
| LLM #3 失败或返回空 | 模板格式化（`_format_damage_response`）|
| RAG 不可用 | 空上下文，LLM 仍可工作 |
| 无 LLM 服务 | 完全降级到关键词匹配 |

重建 RAG 索引：`python -m api.rag_index` 或调用 `POST /api/admin/rebuild-index`

需要配置 `ANTHROPIC_API_KEY` 环境变量，参考 `.env.example`。未配置时自动降级到规则匹配。

## 部署

### 生产环境部署

```bash
# 使用 gunicorn + uvicorn workers
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker 部署

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 注意事项

1. **CORS 配置**: 生产环境需要限制 `allow_origins` 为具体的客户端域名
2. **数据库路径**: 确保 `pokemonData.db` 路径正确
3. **性能优化**: 考虑添加缓存机制（Redis）提升查询性能
4. **错误处理**: 生产环境应添加更完善的日志和错误追踪

## 后续计划

- [x] 集成 LLM 提升自然语言理解能力
- [x] 添加用户认证和会话管理（注册/登录/JWT）
- [x] SSE 流式聊天接口（`/api/chat/stream`）
- [x] 对话标题自动生成（`/api/chat/title`，Haiku 模型）
- [x] 移动端数据接口（宝可梦/招式/道具搜索，供客户端配队使用）
- [x] 用户反馈接口（`/api/feedback`，对话记录保存到本地 JSON）
- [x] `execute_sql` 通用 SQL 查询工具（LLM 直接生成 SELECT，覆盖任意条件筛选）
- [x] 访问量统计（`/api/visit-stats`，中间件自动计数，数据存 `users.db`）
- [ ] 实现 WebSocket 支持实时对话
- [ ] 添加查询结果缓存
- [ ] 支持更多查询类型（队伍分析、配招推荐等）

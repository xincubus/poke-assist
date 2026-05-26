# API 测试指南

## 方法 1: 使用测试脚本（推荐）

### 步骤 1: 启动服务

打开第一个终端：
```bash
cd c:/Users/xincu/Desktop/pokemon/api
python main.py
```

### 步骤 2: 运行测试

打开第二个终端：
```bash
cd c:/Users/xincu/Desktop/pokemon/api
pip install requests  # 如果还没安装
python test_api.py
```

## 方法 2: 使用浏览器（最简单）

1. 启动服务：
```bash
cd c:/Users/xincu/Desktop/pokemon/api
python main.py
```

2. 打开浏览器访问：
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

3. 在 Swagger UI 中可以直接测试所有接口

## 方法 3: 使用 curl

### 测试根路径
```bash
curl http://localhost:8000/
```

### 测试聊天接口
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"你好\"}"
```

### 测试伤害计算（通过聊天）
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"盖欧卡对固拉多使用冲浪\"}"
```

### 测试查询接口
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"查询喷火龙的种族值\"}"
```

### 测试伤害计算接口（直接调用）
```bash
curl -X POST http://localhost:8000/api/damage-calc \
  -H "Content-Type: application/json" \
  -d "{\"attacker_name\": \"盖欧卡\", \"defender_name\": \"固拉多\", \"move_name\": \"冲浪\"}"
```

## 方法 4: 使用 Postman 或 Insomnia

1. 导入 OpenAPI 规范：http://localhost:8000/openapi.json
2. 直接在图形界面中测试

## 测试用例示例

### 聊天接口测试用例

```json
// 问候
{"message": "你好"}

// 伤害计算
{"message": "盖欧卡对固拉多使用根源波动"}
{"message": "252特攻胆小盖欧卡的冲浪打固拉多"}

// 查询
{"message": "查询喷火龙的种族值"}
{"message": "火属性克制什么"}
```

### 伤害计算接口测试用例

```json
// 简单计算
{
  "attacker_name": "盖欧卡",
  "defender_name": "固拉多",
  "move_name": "冲浪"
}

// 完整参数
{
  "attacker_name": "盖欧卡",
  "defender_name": "固拉多",
  "move_name": "根源波动",
  "attacker_evs": {"spa": 252, "spe": 252, "hp": 4},
  "defender_evs": {"hp": 252, "def": 0, "spd": 4, "spe": 252},
  "attacker_nature": "胆小",
  "defender_nature": "固执",
  "weather": "大雨",
  "attacker_ability": "始源之海",
  "attacker_item": "讲究眼镜"
}
```

## 常见问题

### 1. 端口被占用
如果 8000 端口被占用，修改 `main.py` 最后一行：
```python
uvicorn.run(app, host="0.0.0.0", port=8001)  # 改成其他端口
```

### 2. 模块导入错误
确保在项目根目录运行，或设置 PYTHONPATH：
```bash
export PYTHONPATH="c:/Users/xincu/Desktop/pokemon:$PYTHONPATH"
```

### 3. 数据库路径错误
检查 `main.py` 中的 `DB_PATH` 是否正确指向 `pokemonData.db`

## 查看日志

服务启动后会显示详细日志，包括：
- 请求路径
- 响应状态码
- 错误信息

如需更详细的日志，在 `main.py` 中添加：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

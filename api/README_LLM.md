# LLM 智能解析功能

## 概述

聊天服务现已升级为基于 Claude API 的智能解析，替代了原有的规则匹配方式。

### 改进点

**之前（规则匹配）**：
- 写死的正则表达式和关键词匹配
- 只能识别固定的几种句式
- 用户稍微换个说法就可能失败
- 难以维护和扩展

**现在（LLM 解析）**：
- 使用 Claude API 理解自然语言
- 支持各种灵活的表达方式
- 自动提取结构化参数
- 降级机制保证可用性

## 工作流程

### 1. 意图识别
使用 **Claude Haiku**（快速、低成本）快速判断用户意图：
- `query`: 查询宝可梦数据
- `damage_calc`: 计算对战伤害
- `chat`: 普通聊天

### 2. 参数提取（仅伤害计算）
使用 **Claude Sonnet** + Tool Use 提取结构化参数：

**必填参数**：
- `attacker_name`: 攻击方宝可梦
- `move_name`: 使用的招式
- `defender_name`: 防守方宝可梦

**可选参数**：
- 道具：`attacker_item`, `defender_item`
- 性格：`attacker_nature`, `defender_nature`
- 努力值/能力点数：`attacker_evs`, `defender_evs`（Gen10 填 0-32 能力点数，Gen1-9 填 0-252 努力值）
- 世代：`generation`（默认 10，宝可梦冠军；1-9 为对应世代）
- 场地：`field_weather`, `field_terrain`
- 对战模式：`mode`（`Singles` 单打 / `Doubles` 双打，默认双打）
- 其他：`is_critical` 等

## 配置

### 1. 安装依赖

```bash
# 从项目根目录安装
pip install -r requirements.txt
```

新增依赖：
- `anthropic>=0.40.0`: Claude API SDK
- `python-dotenv>=1.0.0`: 环境变量管理

### 2. 配置 API Key

创建 `.env` 文件（参考 `.env.example`）：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

获取 API Key：https://console.anthropic.com/

### 3. 启动服务

```bash
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 使用示例

### 聊天接口

```bash
POST http://localhost:8000/api/chat
Content-Type: application/json

{
  "message": "围巾太火古雷顿闪焰冲锋能秒满HP密勒顿吗"
}
```

**LLM 会自动提取**：
- 攻击方：古雷顿
- 道具：讲究围巾
- 太晶：太晶火
- 招式：闪焰冲锋
- 防守方：密勒顿
- 防守方配置：满HP（hp: 252）

### 支持的表达方式

以下表达都能正确识别：

```
✅ "盖欧卡对固拉多使用根源波动"
✅ "252特攻胆小盖欧卡的根源波动打252HP固拉多"
✅ "头戴太火故勒顿使用闪焰冲锋能秒密勒顿吗"
✅ "故勒顿闪焰冲锋打密勒顿"
✅ "围巾盖欧卡根源波动能秒固拉多吗"
✅ "满攻固执故勒顿的闪焰冲锋对满HP密勒顿"
```

## 降级机制

如果没有配置 `ANTHROPIC_API_KEY` 或 API 调用失败：

1. **意图识别**：降级到简单的关键词匹配
2. **参数提取**：返回错误提示，要求用户配置 API Key
3. **查询功能**：不受影响，继续正常工作

这保证了服务的基本可用性。

## 成本估算

基于 Claude API 定价（2026年3月）：

- **Haiku**（意图识别）：~$0.25 / 1M input tokens
- **Sonnet**（参数提取）：~$3 / 1M input tokens

**单次对话成本**：
- 意图识别：~10 tokens → $0.0000025
- 参数提取：~200 tokens → $0.0006
- **总计**：约 $0.0006 / 次

1000 次对话约 $0.60，成本很低。

## 架构

```
用户消息
    ↓
ChatService.parse_intent()
    ↓
LLMService.recognize_intent()  ← Haiku（快速）
    ↓
判断意图类型
    ↓
[damage_calc] → LLMService.extract_damage_calc_params()  ← Sonnet + Tool Use
    ↓
返回结构化参数
    ↓
调用 ChineseDamageCalculator
    ↓
返回结果
```

## 文件说明

- [llm_service.py](llm_service.py): LLM 服务封装
- [chat_service.py](chat_service.py): 聊天服务（已重构）
- [main.py](main.py): FastAPI 主程序（已更新）
- [.env.example](.env.example): 环境变量模板
- [requirements.txt](../requirements.txt): 依赖列表（API 服务 + 爬虫共用，位于项目根目录）

## 故障排查

### 1. API Key 错误

```
ValueError: 需要提供 ANTHROPIC_API_KEY 环境变量或在初始化时传入 api_key
```

**解决**：检查 `.env` 文件是否存在且包含正确的 API Key。

### 2. 网络问题

```
anthropic.APIConnectionError: Connection error
```

**解决**：检查网络连接，确保能访问 `api.anthropic.com`。

### 3. 参数提取失败

如果 LLM 没有返回 tool_use，会返回空字典 `{}`，此时会提示缺少必填参数。

**解决**：检查用户输入是否包含足够信息，或查看日志了解 LLM 响应。

## 未来优化

1. **缓存机制**：相同问题缓存结果，减少 API 调用
2. **批量处理**：多轮对话合并请求
3. **本地模型**：支持 Ollama 等本地部署方案
4. **多语言**：支持英文、日文输入
5. **上下文记忆**：利用对话历史优化参数提取

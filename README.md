# Pokemon 宝可梦对战助手

基于 LLM 的宝可梦对战助手，支持中文/日文/英文三语。包含智能问答、伤害计算、使用率查询等功能。

[English](README_EN.md)

## 功能

- **智能问答**：通过自然语言查询宝可梦数据（种族值、招式、特性、道具等）
- **伤害计算**：支持全世代伤害计算，包括太晶化、天气、场地等复杂机制
- **使用率查询**：查询宝可梦 HOME Champions 对战使用率排名和配招
- **阈值搜索**：搜索能确一/耐住特定攻击的努力值分配方案
- **网页端**：支持深色/浅色主题、中日英三语切换
- **安卓客户端**：.NET MAUI 开发，支持 SSE 流式响应

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp api/.env.example api/.env
```

编辑 `api/.env`，填入 LLM API Key：

```env
LLM_TOOL_USE_API_KEY=your_api_key_here
LLM_SUMMARY_API_KEY=your_api_key_here
API_BASE_URL=http://localhost:8000
```

### 3. 启动服务

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

首次启动会自动构建 RAG 索引（约 1 分钟），后续启动直接加载缓存。

访问 `http://localhost:8000` 使用网页端，或 `http://localhost:8000/docs` 查看 API 文档。

## 项目结构

```
├── api/                     # FastAPI 后端服务
│   ├── main.py              # 主入口
│   ├── llm_service.py       # LLM Agent Loop 核心
│   ├── chat_service.py      # 聊天服务主入口
│   ├── prompt/              # LLM 提示词与 Tool Schema
│   └── .env.example         # 环境变量模板
├── damage_calculator/       # 伤害计算器（Python + Node.js）
│   ├── cale/                # NCP 计算引擎（fork 自 nerd-of-now）
│   └── cale_chinese_calculator.py  # 中文翻译层
├── web/                     # 网页端
│   ├── calc/                # 旧版中文计算器
│   └── cale/                # 当前使用的计算器（英文 NCP + 中文覆盖层）
├── mobile/                  # .NET MAUI 安卓客户端
├── pokemon_data/            # 数据目录
│   ├── pokemonData.db       # 主数据库（~119MB）
│   ├── createTable/         # 建表脚本
│   └── wiki/                # 52poke Wiki 数据
│       ├── wiki_meta.db     # Wiki 元数据
│       └── wikitext_cache/  # Wiki 原始文本缓存
├── models/                  # Embedding 模型
│   └── bge-small-zh-v1.5/  # 中文语义向量模型
└── requirements.txt
```

## 技术栈

- **Python 3.9+**：后端服务、数据处理
- **FastAPI**：API 框架
- **SQLite**：数据存储
- **Node.js**：伤害计算引擎
- **BGE Small ZH**：中文语义向量检索
- **jieba + pypinyin**：中文分词与拼音匹配
- **.NET MAUI**：安卓客户端

## 数据来源

本项目使用了以下数据来源：

| 来源 | 用途 | 协议 |
|------|------|------|
| [PokeAPI](https://pokeapi.co/) | 宝可梦基础数据（英文） | MIT |
| [神奇宝贝百科（52Poke Wiki）](https://wiki.52poke.com/) | 中文百科数据 | CC BY-NC-SA 3.0 |
| [NCP VGC Damage Calculator](https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/) | 伤害计算引擎 | MIT |
| [pokedb.tokyo](https://champs.pokedb.tokyo/) | HOME Champions 使用率数据 | - |

详细说明见下方 [致谢与许可](#致谢与许可) 章节。

## 致谢与许可

### 本项目许可

本项目采用 [GNU General Public License v3.0](LICENSE) 开源。

### 第三方致谢

#### 伤害计算器

本项目的伤害计算功能 fork 自 [NCP VGC Damage Calculator](https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/)，由 nerd-of-now 维护。

> Originally the official Nuggetbridge damage calculator 2015-2016, later adapted for Trainer Tower 2017-2020, now adapted for Nimbasa City Post from 2021-present. Maintained and developed by nerd-of-now.
>
> Credits and license: MIT License.
>
> Written by Honko. VGC 2015 Update by Tapin and Firestorm. VGC 2016, 2017, 2018, 2019, and 2020 done by squirrelboyVGC. VGC 2021 onwards done by nerd-of-now.

#### 神奇宝贝百科（52Poke Wiki）

本项目通过 [神奇宝贝百科](https://wiki.52poke.com/) 的 MediaWiki API 下载了百科内容（术语知识库、招式效果、场地/天气说明等），存入数据库用于 RAG 检索。

依据其许可协议：
- **署名（BY）**：数据来源于[神奇宝贝百科](https://wiki.52poke.com/)，由神奇宝贝百科的编辑者们贡献
- **非商业性使用（NC）**：本项目仅供个人学习与非商业用途
- **相同方式共享（SA）**：本项目中基于 52Poke 内容的衍生部分同样适用 [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/deed.zh-hans) 协议

#### HOME Champions 使用率数据

本项目的使用率查询功能使用了 [champs.pokedb.tokyo](https://champs.pokedb.tokyo/) 提供的宝可梦 HOME Champions 对战使用率数据。该数据由 pokedb.tokyo 团队整理和维护。

#### PokeAPI

基础宝可梦数据来自 [PokeAPI](https://pokeapi.co/)，一个开放的宝可梦 RESTful API。

#### jQuery

网页端使用了 [jQuery](https://jquery.com/)（MIT License）：
- jQuery 3.1.1（`web/calc/jquery-3.1.1.min.js`）
- jQuery 2.1.0（`web/calc/script_res/jquery-2.1.0.min.js`）

#### select2

网页端使用了 [select2](https://select2.org/)（Apache License 2.0 或 GNU GPL v2.0 双许可）：
- `web/calc/script_res/select2.min.js`

#### Embedding 模型

语义向量检索使用 [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5) 模型（MIT License）。

#### 宝可梦版权

Pokémon 及其相关名称、图像、数据等知识产权归 Nintendo / Creatures Inc. / GAME FREAK inc. 所有。本项目为非官方粉丝项目，与上述公司无任何关联、授权或背书关系，仅供学习与交流使用。

本项目中使用的宝可梦图片来源于 [PokeAPI](https://pokeapi.co/)，仅以合理使用（Fair Use）原则用于非商业用途的说明与展示。

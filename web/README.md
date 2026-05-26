# Web 前端

网页端聊天 Demo 和工具页面。

## 文件说明

| 文件 | 说明 |
|------|------|
| `index.html` | 主聊天界面（支持深色/浅色主题、中日英三语切换、访问量统计） |
| `home/home.html` | 宝可梦使用率排名页面（支持 Champions/SV 数据源、单打/双打切换、赛季选择、中文名、卡片网格布局） |
| `home/pokemon.html` | 单个宝可梦详细使用率页面（种族值、特性/道具/招式/性格/太晶使用率、形态切换、可学招式表） |
| `calc/` | 旧版中文伤害计算器（VGC2024版，已弃用） |
| `cale/` | 当前使用的伤害计算器（英文版 NCP + 中文翻译覆盖层）。`mobile.html` 包含 `getPokemonConfig(pnum)` JS 函数，供 MAUI WebView 调用提取宝可梦配置（JSON） |

## 使用方式

启动 API 服务后访问：
- 聊天页面：`http://localhost:8000/web/` 或 `http://localhost:8000/web/index.html`
- 使用率页面：`http://localhost:8000/web/home/home.html`
- 宝可梦详情页面：`http://localhost:8000/web/home/pokemon.html?id=0006-00&source=champions&season=0&rule=0`
- 伤害计算器：`http://localhost:8000/cale/index_zh.html`

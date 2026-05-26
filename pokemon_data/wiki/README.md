# wiki - 52poke Wiki 全量数据

通过 MediaWiki API 从 [52poke Wiki](https://wiki.52poke.com) 下载全量 wikitext 源码，用于知识图谱构建。

## 目录结构

```
wiki/
├── download_wiki.py             # 下载脚本（枚举+下载+增量更新，支持 ns=0/10）
├── sync_detector.py             # Wiki ↔ 数据库同步检测（新条目 + 过期检测 + LLM 分析 + 执行更新）
├── run_sync_moves.py            # 批量运行 moves 同步检测
├── run_sync_pokemons.py         # 批量运行 pokemons 同步检测（多形态支持）
├── run_sync_abilities.py        # 批量运行 abilities 同步检测
├── run_sync_status.py           # 批量运行 status 同步检测
├── run_sync_items.py            # 批量运行 items 同步检测
├── apply_sync_moves.py          # 将 moves 同步报告写入 pokemonData.db
├── apply_sync_abilities.py      # 将 abilities 同步报告写入 pokemonData.db
├── apply_sync_status.py         # 将 status 同步报告写入 pokemonData.db
├── apply_sync_items.py          # 将 items 同步报告写入 pokemonData.db
├── backfill_wiki_summary.py     # 提取 wiki 页面首段摘要 + 建 FTS5 索引
├── template_expander.py         # 模板递归展开引擎（分类表驱动）
├── seed_wiki_templates.py       # 把 Template 页灌进 wiki_templates 表
├── classify_templates.py        # 批量给 wiki_templates 打分类标签
├── test_template_expander.py    # template_expander 单元测试（32 条）
├── wiki_meta.db                 # SQLite 元数据库（wiki_pages + wiki_redirects + wiki_templates）
├── all_pages.json               # 内容页标题列表（namespace=0）
├── all_pages_ns10.json          # Template 页标题列表（namespace=10）
├── wikitext_cache/              # wikitext 文件缓存（内容页 + Template 同目录）
│   ├── 931_变小（招式）.wiki
│   ├── 273915_Template_招式效果_不能连续使用.wiki
│   └── ...
├── sync_reports/                # 同步检测报告目录
│   └── sync_report_YYYYMMDD_HHMMSS.json
├── UPDATE_LOG.md                # Wiki 数据更新记录 + 脚本用法速查
└── README.md
```

## 用法

### 内容页下载（默认 namespace=0）

```bash
# 枚举全量内容页列表（~30秒，73K+页）
python pokemon_data/wiki/download_wiki.py --refresh-list

# 下载/更新所有内容页（~10-20小时，支持断点续传）
python pokemon_data/wiki/download_wiki.py

# 只处理前N页（测试用）
python pokemon_data/wiki/download_wiki.py --limit 100

# 强制重新下载（忽略时间戳）
python pokemon_data/wiki/download_wiki.py --force

# 查看下载统计（按 namespace 拆分）
python pokemon_data/wiki/download_wiki.py --stats
```

### Template 命名空间下载（namespace=10）

Phase 0 的关键前置步骤：wiki 页面里的 `{{招式效果/...}}`、`{{招式说明|一般|SV}}` 等模板调用要靠 Template 正文才能展开成完整文本。

```bash
# 枚举全量 Template（几千级别）
python pokemon_data/wiki/download_wiki.py --namespace 10 --refresh-list

# 下载所有 Template
python pokemon_data/wiki/download_wiki.py --namespace 10 --auto-restart --batch-size 500

# 只抓对战相关的高频前缀（推荐先跑一轮）
python pokemon_data/wiki/download_wiki.py --namespace 10 --prefix "招式效果/"
python pokemon_data/wiki/download_wiki.py --namespace 10 --prefix "特性效果/"
python pokemon_data/wiki/download_wiki.py --namespace 10 --prefix "状态效果/"
python pokemon_data/wiki/download_wiki.py --namespace 10 --prefix "招式说明/"
```

### 模板展开（分类表驱动）

Phase 0 的核心：52poke 页面里的模板按作用分三类，分类信息存在 `wiki_templates` 表里，`template_expander.py` 查表决定怎么处理每个模板。

| category  | 行为                                       | 典型模板 |
|-----------|--------------------------------------------|----------|
| semantic  | 展开 body，递归替换参数                     | `招式效果/不能连续使用`、`招式说明/一般` |
| infobox   | 不展开 body，只把调用参数压成 `key: value` | `招式信息框`、`Movelist/*`、`名字/entry` |
| inline    | 按 `param_fmt` 输出单个参数                 | `m`/`s`/`i`/`a`/`p`/`lang`/`tt` |
| drop      | 整个删掉                                   | `模板文档`、`神奇宝贝百科招式工程` |
| unknown   | 新模板默认值，行为等同 drop                 | —— |

`param_fmt` 约定：
- inline: `$1`/`$2`/`$last`/`$name`，或字符串模板如 `"$1($2)"`
- infobox: `key_value` (默认) / `title_only` / `drop_body`

#### 一次性初始化流程

```bash
# 1) 下载 Template（如果没下过）
python pokemon_data/wiki/download_wiki.py --namespace 10 --auto-restart

# 2) 把下载好的 Template 灌进 wiki_templates 表（初始 category='unknown'）
python pokemon_data/wiki/seed_wiki_templates.py

# 3) 应用内置默认规则（批量标记常见的 semantic / infobox / inline / drop）
python pokemon_data/wiki/classify_templates.py --apply-defaults

# 4) 查看未分类清单，人工过高频项
python pokemon_data/wiki/classify_templates.py --list unknown --limit 50
python pokemon_data/wiki/classify_templates.py --stats
```

#### 手动打标

```bash
# 按前缀
python pokemon_data/wiki/classify_templates.py --prefix "招式效果/" --category semantic

# 按精确名
python pokemon_data/wiki/classify_templates.py --names "m,s,i,a,p" --category inline --param-fmt "\$last"
python pokemon_data/wiki/classify_templates.py --names "招式信息框" --category infobox --param-fmt key_value

# 查看某类
python pokemon_data/wiki/classify_templates.py --list semantic --limit 100
```

或直接写 SQL：

```sql
UPDATE wiki_templates SET category='semantic' WHERE name LIKE '招式效果/%';
UPDATE wiki_templates SET category='drop'     WHERE name LIKE '神奇宝贝百科%';
```

#### 使用展开器

```bash
# 命令行展开单页（验证用）
python pokemon_data/wiki/template_expander.py wikitext_cache/253994_血月（招式）.wiki

# 代码引用
from pokemon_data.wiki.template_expander import expand

with open('.../血月（招式）.wiki', encoding='utf-8') as f:
    text = expand(f.read())
# text 是 300 字级别的干净文本：规则原文 + 压平的信息框 + 替换成单词的内联引用
```

#### 单元测试

```bash
python pokemon_data/wiki/test_template_expander.py
```

32 条测试：normalize_template_body / substitute_params / render_inline / render_infobox / 四种 category 的行为 / 循环守卫 / 血月页集成测试。

### 同步检测（Wiki ↔ 数据库）

检测 wiki 有但数据库没有的新条目，以及 wiki 页面内容与数据库值不一致的条目。用 LLM 对比数据库值与 wiki 全文（包括变更记录章节），判断是否需要更新。支持 moves/abilities/items/status/pokemons 五种实体类型。

#### 快捷脚本（推荐）

```bash
# moves 同步（批量/单文件）
python pokemon_data/wiki/run_sync_moves.py --since 2026-04-01
python pokemon_data/wiki/run_sync_moves.py --file "pokemon_data/wiki/wikitext_cache/1009_守住（招式）.wiki"

# pokemons 同步（批量/单文件，支持多形态）
python pokemon_data/wiki/run_sync_pokemons.py --since 2026-04-01
python pokemon_data/wiki/run_sync_pokemons.py --file "pokemon_data/wiki/wikitext_cache/159_喷火龙.wiki"

# abilities 同步（批量/单文件）
python pokemon_data/wiki/run_sync_abilities.py --since 2026-04-01

# status 同步（批量/单文件）
python pokemon_data/wiki/run_sync_status.py --since 2026-04-01

# items 同步（批量/单文件）
python pokemon_data/wiki/run_sync_items.py --since 2026-04-01
python pokemon_data/wiki/run_sync_items.py --file "pokemon_data/wiki/wikitext_cache/302775_炎武王进化石（道具）.wiki"

# 只检测新增条目（跳过过期分析，适用于找 wiki 新增但数据库没有的条目）
python pokemon_data/wiki/run_sync_items.py --since 2025-10-01 --new-only
python pokemon_data/wiki/run_sync_moves.py --since 2025-10-01 --new-only
# ... 其他类型同理
```

**通用参数**：
- `--since YYYY-MM-DD`：只检查此日期后更新的页面（默认 2026-05-01）
- `--until YYYY-MM-DD`：只检查此日期前更新的页面（默认不限）
- `--new-only`：只检测新增条目，跳过过期条目分析
- `--file <path>`：单文件模式，只分析指定的 wikitext 文件

#### 完整流程（sync_detector.py）

```bash
# 检测 + LLM 分析（默认检查 2026-04-01 后更新的页面）
python pokemon_data/wiki/sync_detector.py

# 只检测不调用 LLM（快速扫描）
python pokemon_data/wiki/sync_detector.py --quick

# 指定实体类型
python pokemon_data/wiki/sync_detector.py --entity moves
python pokemon_data/wiki/sync_detector.py --entity pokemons

# 指定起始日期
python pokemon_data/wiki/sync_detector.py --since 2025-06-01

# 跳过 API 刷新（用本地缓存的时间戳）
python pokemon_data/wiki/sync_detector.py --skip-api

# 执行更新建议（会先确认 yes/no）
python pokemon_data/wiki/sync_detector.py --apply sync_reports/sync_report_YYYYMMDD_HHMMSS.json
```

**检测逻辑**：
- **Phase 1 - 新条目检测**：对比 wiki 页面标题与数据库 `name_zh`，找出 wiki 有但数据库没有的条目（含重命名检测）
- **Phase 2 - 过期条目检测**：筛出 `wiki_updated >= since_date` 的实体页面，用 `template_expander` 展开 wikitext 模板后，LLM 对比数据库值与 wiki 全文（包括 info 框 + 变更记录章节），提取具体变化
- LLM 使用 `LLM_SYNC` 配置（mimo-v2.5，thinking enabled），单轮分析，不需要预筛选

**输出**：
- `sync_reports/sync_report_moves_mimo.json`：包含过期条目、LLM 更新建议（含字段、旧值、新值、变更原因）
- 控制台摘要：显示检测结果统计

**审核流程**：
1. 运行 `sync_detector.py` 或 `run_sync_moves.py` 生成报告
2. 查看 JSON 报告中的更新建议
3. 确认后运行 `apply_sync_moves.py` 执行更新

#### 应用同步报告

将同步报告中的变更写入 `pokemonData.db`：

```bash
# moves（默认自动查找最新报告，也可指定报告路径）
python pokemon_data/wiki/apply_sync_moves.py --dry-run
python pokemon_data/wiki/apply_sync_moves.py
python pokemon_data/wiki/apply_sync_moves.py sync_reports/sync_report_moves_xxx.json

# abilities
python pokemon_data/wiki/apply_sync_abilities.py --dry-run
python pokemon_data/wiki/apply_sync_abilities.py

# status
python pokemon_data/wiki/apply_sync_status.py --dry-run
python pokemon_data/wiki/apply_sync_status.py

# items
python pokemon_data/wiki/apply_sync_items.py --dry-run
python pokemon_data/wiki/apply_sync_items.py
```

**环境变量**（`api/.env`）：
```
LLM_SYNC_API_KEY=...
LLM_SYNC_BASE_URL=...
LLM_MODEL_SYNC=mimo-v2.5
```

### 摘要回填 + FTS5 索引

Phase 1 前置：为 `wiki_pages` 表补充 `summary` 列（首段纯文本摘要），并建立 FTS5 全文索引 `wiki_pages_fts`，支撑 `search_wiki` 工具。

```bash
# 首次运行（+ 建 FTS5）
python pokemon_data/wiki/backfill_wiki_summary.py --rebuild

# 仅补充新增页面摘要（FTS5 已存在则跳过）
python pokemon_data/wiki/backfill_wiki_summary.py

# 重建 FTS5（删除旧索引重新建）
python pokemon_data/wiki/backfill_wiki_summary.py --rebuild
```

产出：
- `wiki_pages.summary` 列：~40K 条有摘要（namespace=0, status='done'）
- `wiki_pages_fts` FTS5 虚拟表：索引 `title` + `summary`，支持中文关键词搜索

## 增量更新机制

- `wiki_meta.db` 记录每个页面的 `wiki_updated`（wiki 最后修改时间）和 `local_downloaded`（本地下载时间）
- 运行时比较两个时间戳，只下载 wiki 上有更新的页面
- 中断后重新运行自动跳过已下载且未更新的页面

## 文件命名

`{page_id}_{页面标题}.wiki`，如 `931_变小（招式）.wiki`

用 page_id 前缀避免特殊字符导致文件名冲突。Template 页名中的 `/` 会替换为 `_`（如 `招式效果/不能连续使用` → `273915_Template_招式效果_不能连续使用.wiki`）。

## 数据规模

- 内容页（namespace=0）: ~73,000 页 — 包含宝可梦图鉴、招式、特性、道具、NPC、地点、剧情、TCG、动画、漫画、对战术语等
- Template（namespace=10）: ~几千页 — 招式效果模板、特性效果模板、状态效果模板、信息框模板等
- `wiki_templates` 表：每个 Template 一行，记录分类 + param_fmt + 备注，是 `template_expander.py` 的唯一决策源
- `wiki_pages_fts` FTS5 索引：对 title + summary 建全文搜索，~78K 条记录
- 重定向页面自动跟随（如 `变小` → `变小（招式）`），存入 `wiki_redirects` 表

## 注意事项

- 同一实体可能有多个页面（如 大晴天（招式）、大晴天（状态）、大晴天（天气）是三个不同页面，不要合并）
- 52poke 是 MediaWiki 站点，wikitext 中的 `[[内部链接]]` 和 `{{模板}}` 天然编码了实体关系
- 下载速度约 0.5 请求/秒，避免对 wiki 服务器造成压力
- Template 和内容页用同一张 `wiki_pages` 表、同一个 `wikitext_cache/` 目录，通过 `namespace` 字段区分

# 宝可梦数据库生成指南

本目录包含用于生成宝可梦数据库的所有脚本。

## 目录结构

```
createTable/
├── create_all_tables.py          # 主脚本：一键生成所有数据表
├── create_battle_terms_table.py  # 创建对战术语表并插入数据
├── add_pinyin.py                 # 为所有表的中文名称添加拼音列（全拼+首字母缩写）
├── readme.md                     # 本文件
├── form_translations.json        # 形态翻译数据（由 form_translations_data.py 生成）
└── csv/
    ├── pokemons/                  # 宝可梦（新流程）
    │   ├── extract_pokemons_to_csv.py   # pokemon JSON → pokemons.csv
    │   ├── supplement_gen9_pipeline.py  # 补全第九世代缺失图鉴说明（52poke + 日文Wiki）
    │   ├── import_pokemons_csv.py       # pokemons_updated.csv → pokemonData.db
    │   ├── populate_name_ncp.py         # 填充 pokemons.name_ncp 列（NCP 计算器 pokedex key 映射）
    │   ├── populate_gen_availability.py # 填充世代可用性字段（first_gen/in_sv/in_champions）
    │   ├── pokemons.csv                 # 原始数据（运行 extract 后生成）
    │   ├── pokemons_updated.csv         # 补全后数据（运行 supplement 后生成）
    │   ├── pokemon_data.csv             # 旧版原始数据（legacy 流程遗留）
    │   ├── pokemon_data_gen9_updated.csv # 旧版补充Gen9后数据（legacy 流程遗留）
    │   ├── gen9_progress.txt            # 旧版Gen9补充进度记录（legacy 流程遗留）
    │   ├── pokemon_ja_urls.json         # 日文wiki链接缓存
    │   └── pokemon_ja_cache/            # 日文wiki HTML缓存
    ├── abilities/
    │   ├── extract_abilities_to_csv.py  # 特性 JSON → abilities.csv
    │   ├── supplement_abilities_csv.py  # 补全缺失字段 → abilities_updated.csv
    │   ├── import_abilities_csv.py      # abilities_updated.csv → pokemonData.db
    │   ├── abilities.csv
    │   ├── abilities_updated.csv
    │   ├── ability_ja_urls.json
    │   └── ability_ja_cache/
    ├── moves/
    │   ├── extract_moves_to_csv.py      # 招式 JSON → moves.csv
    │   ├── supplement_moves_csv.py      # 补全缺失字段 → moves_updated.csv
    │   ├── import_moves_csv.py          # moves_updated.csv → pokemonData.db（重建 moves 表）
    │   ├── moves.csv
    │   ├── moves_updated.csv
    │   ├── move_ja_urls.json
    │   └── move_ja_cache/
    ├── items/
    │   ├── download_items_csv.py        # 直接下载道具数据 → items.csv
    │   ├── supplement_items_csv.py      # 补全缺失字段 → items_updated.csv
    │   ├── import_items_csv.py          # items_updated.csv → pokemonData.db
    │   ├── populate_item_gen_availability.py # 填充道具世代可用性字段（name_ncp/first_gen/in_sv/in_champions）
    │   ├── items.csv
    │   ├── item_ja_urls.json
    │   └── item_ja_cache/
    ├── natures/
    │   ├── extract_natures_to_csv.py    # 从 nature JSON 提取性格数据 → natures.csv
    │   ├── import_natures_csv.py        # 从 natures.csv 导入 natures 表
    │   └── natures.csv
    ├── pokemon_moves/
    │   ├── extract_pokemon_moves_csv.py # pokemon JSON → pokemon_moves.csv
    │   ├── import_pokemon_moves_csv.py  # pokemon_moves.csv → pokemonData.db
    │   └── pokemon_moves.csv
    ├── status/
    │   ├── extract_status_to_csv.py     # 从 status/ HTML 提取异常状态 → status.csv
    │   ├── import_status_csv.py         # status.csv → pokemonData.db
    │   └── status.csv
    ├── terrains/
    │   ├── extract_terrains_to_csv.py   # 从 terrain/ HTML 提取场地数据 → terrains.csv
    │   ├── import_terrains_csv.py       # terrains.csv → pokemonData.db（重建 terrains 表）
    │   └── terrains.csv                 # 提取后的场地数据（运行 extract 后生成）
    ├── types/
    │   ├── extract_types_to_csv.py      # 从 type_html/ HTML 提取属性数据 → types.csv
    │   ├── import_types_csv.py          # types.csv → pokemonData.db（重建 types 表）
    │   ├── create_type_effectiveness_table.py  # 从 type/ JSON 重建 type_effectiveness 表
    │   └── types.csv                    # 提取后的属性数据（运行 extract 后生成）
    └── weather/
        ├── extract_weather_to_csv.py    # 从 weather_html/ HTML 提取天气数据 → weather.csv
        ├── supplement_weather_csv.py    # 检查缺失字段，生成 weather_updated.csv
        ├── import_weather_csv.py        # weather_updated.csv → pokemonData.db（重建 weather 表）
        ├── weather.csv                  # 提取后的天气数据（运行 extract 后生成）
        └── weather_updated.csv          # 补全后的天气数据（运行 supplement 后生成）
    └── wiki_terms/
        ├── scrape_wiki_terms.py         # 从 52poke wiki 多分类爬取术语页面 HTML
        ├── extract_wiki_terms.py        # 从缓存 HTML 提取结构化数据 → wiki_terms.json
        ├── clean_wiki_terms.py          # 清洗数据 → wiki_terms_clean.json
        ├── import_wiki_terms.py         # wiki_terms_clean.json → pokemonData.db（wiki_pages + wiki_sections）
        ├── page_index.json              # 页面索引（838 条）
        ├── wiki_terms.json              # 原始提取数据
        ├── wiki_terms_clean.json        # 清洗后数据
        └── html_cache/                  # 52poke HTML 缓存
└── legacy/                       # 分项脚本归档
    ├── form_translations_data.py  # 生成 form_translations.json（形态翻译表）
    ├── export_battle_terms.py
    ├── import_battle_terms.py
    └── update_pokemons_image_path.py
```

## 快速开始

### 方式一：使用主脚本（推荐）

运行主脚本可以一次性创建所有基础表：

```bash
cd C:\Users\xincu\Desktop\pokemon\pokemon_data\createTable
python create_all_tables.py
```

这将自动创建以下表：
1. `types` - 属性表
2. `type_effectiveness` - 属性克制表
3. `abilities` - 特性表
4. `moves` - 招式表
5. `items` - 道具表
6. `pokemons` - 宝可梦表（仅结构，需手动导入数据）
7. `pokemon_moves` - 宝可梦招式学习表（依赖 pokemons 表）

### 方式二：分步执行（新流程）

各主要表均有统一的三步流程：**提取 → 补全 → 导入**

#### pokemons 表（新流程）

```bash
# 步骤1：从 JSON 提取
python csv/pokemons/extract_pokemons_to_csv.py
# 步骤2：补全第九世代缺失的图鉴说明
python csv/pokemons/supplement_gen9_pipeline.py --step1-only  # 只补52poke中日文
python csv/pokemons/supplement_gen9_pipeline.py --step2-only  # 只补日文Wiki
python csv/pokemons/supplement_gen9_pipeline.py               # 完整流程
# 步骤3：导入数据库
python csv/pokemons/import_pokemons_csv.py                 # 只更新文本字段
python csv/pokemons/import_pokemons_csv.py --full-rebuild  # 删表重建（全量导入）
```

#### abilities 表

```bash
python csv/abilities/extract_abilities_to_csv.py
python csv/abilities/supplement_abilities_csv.py
python csv/abilities/import_abilities_csv.py
```

#### moves 表

```bash
python csv/moves/extract_moves_to_csv.py
python csv/moves/supplement_moves_csv.py
python csv/moves/import_moves_csv.py
```

#### items 表

```bash
python csv/items/download_items_csv.py
python csv/items/supplement_items_csv.py
python csv/items/import_items_csv.py
```

#### pokemon_moves 表

```bash
python csv/pokemon_moves/extract_pokemon_moves_csv.py
python csv/pokemon_moves/import_pokemon_moves_csv.py
```

注意：move_name_zh 为空的条目是因为 moves 表中对应招式缺少中文名，先补全 moves 表再重新提取即可。

#### weather 表

```bash
# 步骤0：下载 HTML（需要 cloudscraper + undetected-chromedriver）
python download/download_weather_html.py
# 步骤1：从 HTML 提取所有字段
python csv/weather/extract_weather_to_csv.py
# 步骤2：检查缺失字段
python csv/weather/supplement_weather_csv.py --check
# 步骤3：导入数据库
python csv/weather/import_weather_csv.py
```

#### status 表

```bash
# 步骤1：从 HTML 提取（需要 pokemon_data/status/ 目录下的 HTML 文件）
python csv/status/extract_status_to_csv.py
# 步骤2：手动检查 status.csv，确认数据无误
# 步骤3：导入数据库
python csv/status/import_status_csv.py
```

#### weather 表（新版，含属性/招式/特性效果字段）

```bash
# 步骤0：下载 HTML（需要 cloudscraper + undetected-chromedriver）
python download/download_weather_html.py
# 步骤1：从 HTML 提取所有字段
python csv/weather/extract_weather_to_csv.py
# 步骤2：检查缺失字段，生成 weather_updated.csv
python csv/weather/supplement_weather_csv.py
# 步骤3：导入数据库
python csv/weather/import_weather_csv.py
```

#### terrains 表（含效果字段）

```bash
# 步骤0：下载 HTML（需要 cloudscraper + undetected-chromedriver）
python download/download_terrains_html.py
# 步骤1：从 HTML 提取所有字段
python csv/terrains/extract_terrains_to_csv.py
# 步骤2：导入数据库
python csv/terrains/import_terrains_csv.py
```

#### types 表（含描述/效果字段）

```bash
# 步骤0：下载 HTML（需要 cloudscraper + undetected-chromedriver）
python download/download_types_html.py
# 步骤1：从 HTML 提取所有字段
python csv/types/extract_types_to_csv.py
# 步骤2：手动检查 types.csv，修正描述/效果文本
# 步骤3：导入数据库
python csv/types/import_types_csv.py
```

#### 拼音列（搜索匹配用）

数据导入完成后，运行以下脚本为所有表的 name_zh 添加拼音列（`name_pinyin` 全拼 + `name_pinyin_abbr` 首字母缩写），battle_terms 表则为 aliases 添加 `aliases_pinyin` + `aliases_pinyin_abbr`：

```bash
pip install pypinyin
python add_pinyin.py          # 正式写入
python add_pinyin.py --dry-run  # 只统计不写入
```

### 步骤 5：验证数据

检查数据库中的数据是否正确：

使用 SQLite 客户端查询：

```sql
-- 查看宝可梦总数
SELECT COUNT(*) FROM pokemons;

-- 查看招式总数
SELECT COUNT(*) FROM moves;

-- 查看特性总数
SELECT COUNT(*) FROM abilities;

-- 查看属性克制关系总数
SELECT COUNT(*) FROM type_effectiveness;

-- 查看招式学习记录总数
SELECT COUNT(*) FROM pokemon_moves;

-- 查看各世代招式学习记录数
SELECT generation, COUNT(*)
FROM pokemon_moves
GROUP BY generation
ORDER BY generation;

-- 查询火属性对其他属性的克制关系
SELECT t1.name_zh as attacker, t2.name_zh as defender, te.effectiveness
FROM type_effectiveness te
JOIN types t1 ON te.attacker_type_id = t1.id
JOIN types t2 ON te.defender_type_id = t2.id
WHERE t1.name_en = 'fire'
ORDER BY te.effectiveness DESC;

-- 查询被水属性克制的属性（效果拔群）
SELECT t2.name_zh as defender, te.effectiveness
FROM type_effectiveness te
JOIN types t1 ON te.attacker_type_id = t1.id
JOIN types t2 ON te.defender_type_id = t2.id
WHERE t1.name_en = 'water' AND te.effectiveness = 2.0;
```

## 数据库表结构

### 1. types（属性表）
- `id` - 属性 ID
- `name_en` - 英文名
- `name_ja` - 日文名
- `name_zh` - 中文名
- `description_zh / _en / _ja` - 三语描述（属性简介）
- `effect_zh / _en / _ja` - 三语效果（属性特性，如免疫/附加效果等）

### 2. type_effectiveness（属性克制表）
- `attacker_type_id` - 攻击方属性 ID（关联 types 表）
- `defender_type_id` - 防御方属性 ID（关联 types 表）
- `effectiveness` - 克制效果倍率
  - `0` - 无效
  - `0.5` - 效果不好
  - `1.0` - 正常
  - `2.0` - 效果拔群

### 3. abilities（特性表）
- `id` - 特性 ID
- `name_ja` - 日文名
- `name_zh` - 中文名
- `name_en` - 英文名
- `description_ja/zh/en` - 各语言描述
- `pokemon_list` - 拥有该特性的宝可梦列表

### 4. moves（招式表）
- `id` - 招式 ID
- `name_ja/zh/en` - 各语言名称
- `type` - 属性（英文名，保留用于导出）
- `type_id` - 属性 ID（关联 types 表）
- `damage_class` - 伤害类别（物理/特殊/变化）
- `power` - 威力
- `accuracy` - 命中率
- `priority` - 优先度
- `pp` - PP 值
- `description_ja/zh/en` - 各语言游戏内描述
- `effect_ja/zh/en` - 各语言机制效果（详细对战效果，区别于游戏内描述）
- `learned_by_pokemon` - 可学习该招式的宝可梦列表

### 5. items（道具表）
- `id` - 道具 ID
- `name_ja/zh/en` - 各语言名称
- `category` - 类别
- `fling_power` - 投掷威力
- `fling_effect` - 投掷效果
- `description_ja/zh/en` - 各语言描述
- `image_path` - 图片相对路径（如 `heldItemImage/master-ball.png`）
- `name_ncp` - NCP 伤害计算器中的道具名（Title Case，如 `Choice Specs`），用于伤害计算时名称映射
- `first_gen` - 道具首次出现世代（2-9），用于全国图鉴世代推断
- `in_sv` - 是否在 ITEMS_SV 列表中（0/1）
- `in_champions` - 是否在 ITEMS_CHAMPIONS 列表中（0/1）

### 6. pokemons（宝可梦表）
- `id` - 自增主键
- `pokedex_id` - 图鉴编号
- `pokeapi_id` - PokeAPI 编号
- `name_ja/zh/en` - 各语言名称
- `is_default_form` - 是否默认形态
- `type1/type2` - 属性（英文名，保留用于导出）
- `type1_id/type2_id` - 属性 ID（关联 types 表）
- `image_official_artwork` - 官方插图相对路径（如 `pokemonImage/001-bulbasaur-officialArtwork.png`）
- `ability1/2/hidden` - 特性（ID 和名称）
- `weight_kg` - 体重
- `hp/attack/defense/sp_attack/sp_defense/speed` - 种族值
- `total_stats` - 种族值总和
- `name_ncp` - NCP 伤害计算器的 pokedex key（如 `Basculegion`、`Mega Charizard X`），用于伤害计算时名称映射
- `first_gen` - 首次出现世代（1-9），用于全国图鉴世代推断
- `in_sv` - 是否在朱紫限定图鉴中（0/1）
- `in_champions` - 是否在冠军限定图鉴中（0/1）
- `description_ja/en/zh` - 各语言图鉴说明

### 7. pokemon_moves（宝可梦招式学习表）
- `id` - 自增主键
- `pokedex_id` - 图鉴编号
- `pokeapi_id` - PokeAPI 编号
- `pokemon_name_ja/zh/en` - 宝可梦名称
- `move_id` - 招式 ID
- `move_name_ja/zh/en` - 招式名称
- `learn_method` - 学习方式（等级提升/蛋招式/教学招式/招式机）
- `level` - 学习等级（仅等级提升）
- `version_group` - 版本组
- `generation` - 世代

### 8. pokemon_moves_sv（朱紫世代招式表）
与 `pokemon_moves` 结构相同，但仅包含朱紫世代（第九世代）的数据。

### 9. wiki_pages（术语知识库 - 页面表）
- `id` - 自增主键
- `title` - 页面标题（如"击中要害"、"威吓（特性）"）
- `url` - 52poke wiki 链接
- `summary` - 一句话摘要
- `category` - 分类（术语/特性/招式/状态变化/游戏系统/属性/地形/宝可梦特殊能力）

### 10. wiki_sections（术语知识库 - 段落表）
- `id` - 自增主键
- `page_id` - 关联 wiki_pages.id
- `heading` - 段落标题（如"概述"、"效果"、"第九世代"）
- `level` - 标题层级（2 或 3）
- `text` - 正文内容
- `section_order` - 段落在页面中的顺序

## 常见问题

### Q1: 为什么八九世代的图鉴说明为空？

PokeAPI 的数据可能不完整，特别是较新世代的中日文翻译。需要使用 `supplement_all.py` 从 52poke 维基补充。

### Q2: 如果 supplement_all.py 中断了怎么办？

脚本会每 10 条记录保存一次进度到 `progress.txt`。重新运行脚本会跳过已处理的记录。

### Q3: 为什么需要先创建 pokemons 表才能创建 pokemon_moves 表？

`pokemon_moves` 表依赖 `pokemons` 表的数据来获取正确的图鉴编号和中日文名称。

### Q4: 如何更新数据？

1. 重新下载 JSON 数据（使用 `download` 文件夹中的脚本）
2. 重新运行 `extract_pokemon_data.py`
3. 重新运行 `create_all_tables.py`

### Q5: legacy 文件夹是什么？

包含已被整合到 `create_all_tables.py` 的旧版脚本，保留用于参考。

### Q6: 为什么 pokemons 和 moves 表中保留了原有的 type 字段？

原有的 type1、type2（pokemons）和 type（moves）字段保留英文名称，用于数据导出和向后兼容。新增的 type1_id、type2_id（pokemons）和 type_id（moves）字段用于关联查询 types 表，获取多语言名称。

### Q7: 如何更新现有数据库的 items 表以添加图片路径？

如果你的数据库是在添加 image_path 功能之前创建的，重新运行 items 流程即可：

```bash
python csv/items/extract_items_to_csv.py
python csv/items/supplement_items_csv.py
python csv/items/import_items_csv.py
```

### Q8: 如何更新现有数据库的 pokemons 表以添加图片路径？

如果你的数据库是在添加 image_official_artwork 功能之前创建的，可以运行以下脚本更新：

```bash
python pokemon_data/createTable/legacy/update_pokemons_image_path.py
```

该脚本会自动添加 image_official_artwork 列并填充所有宝可梦的官方插图路径。图片文件名格式为 `{pokeapi_id:03d}-{name_en}-officialArtwork.png`（ID < 1000 时用 3 位数字格式化）。

### Q9: 如何导出和导入 battle_terms 表数据？

**导出到 Excel：**
```bash
python pokemon_data/createTable/legacy/export_battle_terms.py
```

导出文件会保存到 `pokemon_data/exports/battle_terms_YYYYMMDD_HHMMSS.xlsx`，包含所有术语数据。

**从 Excel 导入：**
```bash
# 完全替换模式（清空表后导入）
python pokemon_data/createTable/legacy/import_battle_terms.py path/to/battle_terms.xlsx

# 追加模式（只插入新记录，跳过已存在的）
python pokemon_data/createTable/legacy/import_battle_terms.py path/to/battle_terms.xlsx --mode append

# 更新模式（根据 id 更新，无 id 则插入）
python pokemon_data/createTable/legacy/import_battle_terms.py path/to/battle_terms.xlsx --mode update
```

**编辑说明：**
- 在 Excel 中可以新增、修改、删除术语
- 新增行时 id 列留空（导入时自动生成）
- category 必须是以下之一：stat_spread, item_alias, role, mechanic, calc_concept, ev_nature, pokemon_alias
- term, category, definition 为必填字段

### Q10: 如何更新 wiki_terms 术语知识库？

wiki_terms 数据来自 52poke wiki，覆盖 9 个分类（术语、游戏系统、状态变化、特性、属性、对战、特殊能力、地形、招式），共 833 页。

```bash
# 步骤1：爬取 HTML（跳过已缓存，约 15-20 分钟）
python csv/wiki_terms/scrape_wiki_terms.py
# 步骤2：从 HTML 提取结构化数据
python csv/wiki_terms/extract_wiki_terms.py
# 步骤3：清洗数据
python csv/wiki_terms/clean_wiki_terms.py
# 步骤4：导入数据库（删旧表重建）
python csv/wiki_terms/import_wiki_terms.py
```

### Q11: 为什么宝可梦形态的中日文名称显示为英文后缀？

某些带形态的宝可梦（如龙卷云、雷电云）的中文名和日文名可能直接使用了英文形态后缀（如 "龙卷云-therian"），而不是官方翻译（应该是"龙卷云（灵兽形态）"）。

**原因：** PokeAPI 的 pokemon-form 端点不提供中文翻译，只有日文、英文、法文等。

**解决方案：**

1. 生成本地翻译表（已包含 150 个形态）：
   ```bash
   python pokemon_data/createTable/legacy/form_translations_data.py
   ```

2. 重新导出 CSV 文件（脚本已更新，会自动使用翻译表）：
   ```bash
   python csv/pokemons/extract_pokemons_to_csv.py
   ```

3. 如果发现新的形态缺失翻译，编辑 `form_translations_data.py` 添加后重新运行步骤 1

**复合后缀支持：** 脚本支持自动拆分复合形态后缀（如 `-single-strike-gmax` → 「一击流 超极巨化」），会从后缀末尾逐段匹配已知翻译并合并。

### Q12: 如何更新 pokemons 表的 name_ncp 列？

`name_ncp` 列存储 NCP 伤害计算器的 pokedex key（如 `Basculegion`、`Mega Charizard X`），用于伤害计算时将数据库宝可梦名映射为计算器引擎名称。

```bash
# 填充 name_ncp 列
python csv/pokemons/populate_name_ncp.py

# 仅预览，不写入
python csv/pokemons/populate_name_ncp.py --dry-run
```

脚本会从 `damage_calculator/cale/pokedex.js` 提取所有世代的 pokedex key，按优先级匹配：手动覆盖 → normalize 直接匹配 → mega/primal 翻转 → 去后缀。

### Q13: 如何更新 pokemons 表的世代可用性字段？

`first_gen`、`in_sv`、`in_champions` 字段用于伤害计算时自动推断世代（限定图鉴优先，全国图鉴 fallback）。

```bash
# 填充世代可用性字段
python csv/pokemons/populate_gen_availability.py

# 仅预览，不写入
python csv/pokemons/populate_gen_availability.py --dry-run
```

脚本从 `damage_calculator/cale/pokedex.js` 提取各世代 pokedex key 列表，确定每个宝可梦的首次出现世代和限定图鉴可用性。

### Q14: 如何更新 items 表的世代可用性字段？

`name_ncp`、`first_gen`、`in_sv`、`in_champions` 字段用于伤害计算时道具参与世代推断（如讲究眼镜不在冠军道具列表中，会将世代从 Gen 10 降到 Gen 9）。

```bash
# 填充道具世代可用性字段
python csv/items/populate_item_gen_availability.py

# 仅预览，不写入
python csv/items/populate_item_gen_availability.py --dry-run
```

脚本从 `damage_calculator/cale/item_data.js` 提取各世代道具列表，匹配 DB 中的 name_en（kebab-case → Title Case），确定每个道具的首次出现世代和限定图鉴可用性。DB 共 2175 道具，NCP 计算器约 300 个，大部分游戏内部道具无匹配（预期）。

## 数据流程图

```
JSON 文件 (pokemon_data/pokemon/*.json)
    ↓
csv/pokemons/extract_pokemons_to_csv.py
    ↓
csv/pokemons/pokemon_data_gen9_updated.csv（旧流程遗留）或 pokemons.csv（新流程）
    ↓
csv/pokemons/supplement_gen9_pipeline.py（补全第九世代缺失图鉴说明）
    ↓
csv/pokemons/import_pokemons_csv.py
    ↓
pokemonData.db（pokemons 表）
```

> 旧流程（legacy/）：JSON → pokemon_data.csv（中文列名）→ pokemon.xlsx → create_pokemons_table.py → DB
> 已归档，新项目请使用 csv/pokemons/ 下的新流程。

## 技术细节

### 版本组到世代的映射

脚本使用以下映射关系将版本组转换为世代编号：

- 第 1 世代：red-blue, yellow, red-green-japan, blue-japan
- 第 2 世代：gold-silver, crystal
- 第 3 世代：ruby-sapphire, emerald, firered-leafgreen, colosseum, xd
- 第 4 世代：diamond-pearl, platinum, heartgold-soulsilver
- 第 5 世代：black-white, black-2-white-2
- 第 6 世代：x-y, omega-ruby-alpha-sapphire
- 第 7 世代：sun-moon, ultra-sun-ultra-moon, lets-go-pikachu-lets-go-eevee
- 第 8 世代：sword-shield, brilliant-diamond-shining-pearl, legends-arceus
- 第 9 世代：scarlet-violet

### 学习方式映射

- `level-up` → 等级提升
- `egg` → 蛋招式
- `tutor` → 教学招式
- `machine` → 招式机
- 其他特殊方式 → 特殊

## 维护者

如有问题或建议，请联系项目维护者。

## 更新日志

- 2024-XX-XX: 创建整合脚本和文档
- 2024-XX-XX: 添加 CSV 排序功能
- 2024-XX-XX: 修改数据库路径为 pokemonData.db

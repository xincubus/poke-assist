# evolutions 表数据脚本

## 概述

从 52poke Wiki 提取宝可梦进化关系，导入到 `pokemonData.db` 的 `evolutions` 表。

## 文件说明

- `extract_evolutions.py` - 从 wiki wikitext 提取进化关系，生成 CSV
- `import_evolutions.py` - 将 CSV 导入数据库
- `evolutions.csv` - 提取的进化关系数据（525条）

## 数据结构

evolutions 表结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 主键 |
| from_pokemon_id | INTEGER | 进化前宝可梦 ID |
| to_pokemon_id | INTEGER | 进化后宝可梦 ID |
| method | TEXT | 进化方式 |
| level | INTEGER | 等级（level-up 时） |
| item_id | INTEGER | 道具 ID（use-item 时） |
| condition | TEXT | 其他条件（JSON） |
| is_mega | BOOLEAN | 是否 Mega 进化 |
| is_gmax | BOOLEAN | 是否超极巨化 |

## method 枚举值

- `level-up` - 升级进化（305条）
- `mega` - Mega 进化（83条）
- `use-item` - 使用道具进化（48条）
- `gmax` - 超极巨化（30条）
- `level-up-friendship` - 亲密度进化（16条）
- `trade` - 交换进化（16条）
- `level-up-move` - 学会招式进化（11条）
- `level-up-location` - 地点进化（6条）
- `level-up-affection` - 好感度进化（2条）
- `level-up-beautiful` - 美丽度进化（1条）
- `other` - 其他特殊进化（7条）

## 使用方法

### 1. 提取进化关系

```bash
python extract_evolutions.py
```

从 `pokemon_data/wiki/wiki_meta.db` 读取 wikitext，解析 `{{进化框}}` 模板，生成 `evolutions.csv`。

### 2. 导入数据库

```bash
python import_evolutions.py
```

将 CSV 导入 `pokemonData.db`，自动创建表和索引。

## 数据源

- 52poke Wiki wikitext（`pokemon_data/wiki/wikitext_cache/`）
- 解析 `{{进化框}}` 模板中的 name、evotype、level、item 等字段
- 中文名映射到 `pokemons.id`，道具名映射到 `items.id`

## 进化方式映射

| Wiki evotype | method | 说明 |
|---|---|---|
| Level | level-up | 升级进化 |
| Stone / Item | use-item | 使用进化石/道具 |
| Happiness | level-up-friendship | 亲密度进化 |
| Trade | trade | 交换进化 |
| Move | level-up-move | 学会招式进化 |
| Location | level-up-location | 地点进化 |
| Held | level-up-hold-item | 携带道具进化 |
| Affection | level-up-affection | 好感度进化 |
| Beautiful | level-up-beautiful | 美丽度进化 |

## 查询示例

```sql
-- 查看皮卡丘的进化链
SELECT
    p1.name_zh AS from_name,
    p2.name_zh AS to_name,
    e.method,
    e.level,
    i.name_zh AS item_name
FROM evolutions e
JOIN pokemons p1 ON e.from_pokemon_id = p1.id
JOIN pokemons p2 ON e.to_pokemon_id = p2.id
LEFT JOIN items i ON e.item_id = i.id
WHERE p1.name_zh = '皮卡丘' OR p2.name_zh = '皮卡丘';

-- 查看所有需要道具进化的宝可梦
SELECT
    p1.name_zh AS from_name,
    p2.name_zh AS to_name,
    i.name_zh AS item_name
FROM evolutions e
JOIN pokemons p1 ON e.from_pokemon_id = p1.id
JOIN pokemons p2 ON e.to_pokemon_id = p2.id
LEFT JOIN items i ON e.item_id = i.id
WHERE e.method = 'use-item';
```

## 注意事项

- 525 条进化关系覆盖了大部分有进化的宝可梦
- 包含 83 条 Mega 进化和 30 条超极巨化
- 铝钢龙→铝钢桥龙的道具"复合金属"在数据库中不存在
- 伊布的多分支进化已正确提取（8条记录）

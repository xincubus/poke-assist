# db_supplement — 数据库补全脚本

从 52poke Wiki 的 wikitext 模板中提取结构化数据，补全 `pokemonData.db` 中缺失的字段和表。

## 前置条件

- Wiki 下载完成（`pokemon_data/wiki/wikitext_cache/` 有 ~73K 文件）
- `pokemon_data/wiki/wiki_meta.db` 存在（含 wiki_pages + wiki_redirects 表）

## 脚本列表

| 脚本 | 目标 | 状态 |
|------|------|------|
| `01_supplement_pokemons.py` | pokemons 补 10 列 | 已完成 |
| `02_supplement_moves.py` | moves 补 6 列 | 已完成 |
| `03_supplement_abilities.py` | abilities 补 7 列机制属性 | 已完成 |
| `04_supplement_ability_effects.py` | abilities 补对战中/对战外效果 | 已完成 |
| `04_supplement_move_effects.py` | moves 补 effect_zh | 已完成 |
| `05_supplement_items.py` | items 补 name_zh | 已完成 |
| `06_create_evolutions.py` | 新建 evolutions 表 | 已完成 |
| `07_expand_status.py` | 扩展 status 表 | 已完成 |
| `08_create_type_matchups.py` | 新建 type_matchups_by_gen 表 | 已完成 |

## 01_supplement_pokemons.py

补全 pokemons 表的 10 列：

| 字段 | 类型 | 说明 | 形态相关 |
|------|------|------|----------|
| species | TEXT | 种类名（鼠、种子） | 否 |
| egg_group1 | TEXT | 蛋群1（陆上、妖精） | 否 |
| egg_group2 | TEXT | 蛋群2（可为空） | 否 |
| gender_ratio | INTEGER | 性别比例代码（127=1♂:1♀） | 否 |
| catch_rate | INTEGER | 捕获率 | 否 |
| color | TEXT | 图鉴颜色（黄、绿） | 否 |
| ev_yield | TEXT | 击败获得努力值（sa+2） | 否 |
| base_exp | INTEGER | 基础经验值 | 是 |
| height_m | REAL | 身高(米) | 是 |
| weight_kg | REAL | 体重(公斤) | 是 |

### 执行流程

1. **Phase 1**：ALTER TABLE 新增列 + 提取形态无关字段（species 等 7 列），同一 pokedex_id 下所有形态共享
2. **Phase 2**：形态相关字段（height/weight/base_exp），default form 取无后缀值，非 default form 通过 `wiki_redirects` 形态别名或后缀规则匹配 formN
3. **Phase 3**：未匹配的形态调用 LLM（mimo-v2.5）解析，结果写回 `wiki_meta.db` 的 `wiki_redirects` 表（`target_page_id=0` 标记为形态别名）

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/01_supplement_pokemons.py
```

脚本幂等，可重复运行。LLM 解析结果会缓存到 `wiki_redirects`，下次运行直接命中。

### 验证

```sql
SELECT count(*) FROM pokemons WHERE species IS NOT NULL;       -- 应 ~1350
SELECT count(*) FROM pokemons WHERE height_m IS NOT NULL;      -- 应 ~1350
SELECT count(*) FROM pokemons WHERE weight_kg IS NOT NULL;     -- 应 ~1350
```

## 02_supplement_moves.py

补全 moves 表的 6 列对战机制属性：

| 字段 | 类型 | 说明 |
|------|------|------|
| makes_contact | INTEGER | 是否接触招式 (0/1) |
| can_protect | INTEGER | 能否被守住 (0/1) |
| can_magic_coat | INTEGER | 能否被魔法反射 (0/1) |
| can_snatch | INTEGER | 能否被化为己用 (0/1) |
| can_mirror_move | INTEGER | 能否被鹦鹉学舌 (0/1) |
| target | INTEGER | 目标范围代码 (1-16) |

### 匹配策略

6 轮匹配 + 3 条特例，基于 `wiki_pages` 和 `wiki_redirects` 索引：

1. `name_zh（招式）` → pages_map（815）
2. `name_zh` → pages_map（2，日文文件名页面）
3. redirect → pages_map（26）
4. redirect → pages_map 带后缀（0）
5. 繁体`（招式）` → pages_map（5）
6. 繁体 → pages_map（66）
7. 特例硬编码（Z招式同义词 + opencc 精度修正）

匹配率：919/937（98.1%），未匹配 18 个为暗影招式（无中文名无 wiki 页面）。

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/02_supplement_moves.py
```

脚本幂等，可重复运行。

### 验证

```sql
SELECT count(*) FROM moves WHERE makes_contact IS NOT NULL;    -- 应 ~919
SELECT makes_contact, count(*) FROM moves GROUP BY makes_contact;
SELECT target, count(*) FROM moves WHERE target IS NOT NULL GROUP BY target ORDER BY count(*) DESC;
```

## 03_supplement_abilities.py

补全 abilities 表的 7 个对战机制属性列：

| 字段 | 类型 | 说明 | Wiki 参数 |
|------|------|------|----------|
| affected_by_mold_breaker | INTEGER | 受不受破格等无视特性效果影响 (0/1) | Moldbreaker |
| affected_by_no_ability | INTEGER | 受不受无特性状态影响 (0/1) | Noability |
| triggers_on_entry | INTEGER | 入场时发动 (0/1) | Entry |
| can_be_traced | INTEGER | 能不能被追踪复制 (0/1) | Trace |
| works_when_transformed | INTEGER | 变身时有没有效果 (0/1) | Transform |
| can_be_swapped | INTEGER | 能不能被特性交换 (0/1) | Skillswap |
| can_be_overridden | INTEGER | 能不能被其他特性覆盖 (0/1) | Change |

### 匹配策略

中文名两轮匹配（直接扫描 wikitext_cache 文件名）：

1. `{name_zh}（特性）` → 312/314
2. `{name_zh}` → 剩余 2 条（水泡、心眼）

匹配率：314/314（100%），60 条 GO 特性（id ≥ 10001）跳过。

### 参数值规则

- Wiki 参数为 `no` → 0
- Wiki 参数为 `y`/`yes` 或缺失 → 1（默认值）

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/03_supplement_abilities.py
```

脚本幂等，可重复运行。

### 验证

```sql
-- 全部非 GO 特性应有值
SELECT count(*) FROM abilities WHERE id < 10000 AND affected_by_mold_breaker IS NOT NULL;  -- 应 314

-- 各列分布
SELECT affected_by_mold_breaker, count(*) FROM abilities WHERE id < 10000 GROUP BY affected_by_mold_breaker;
SELECT affected_by_no_ability, count(*) FROM abilities WHERE id < 10000 GROUP BY affected_by_no_ability;

-- GO 特性应为 NULL
SELECT count(*) FROM abilities WHERE id >= 10000 AND affected_by_mold_breaker IS NULL;  -- 应 60
```

## 04_supplement_ability_effects.py

补全 abilities 表的对战中/对战外效果：

| 字段 | 类型 | 说明 |
|------|------|------|
| effect_battle | TEXT | 对战中效果 |
| effect_overworld | TEXT | 对战外效果（仅 9 条有） |

### 数据源

52poke Wiki 特性页面的 `==特性效果==` section，按 `===对战中===` / `===对战外===` 子标题分段。

### 匹配策略

中文名两轮匹配（同 03）：314/314（100%）

### Wikitext 清理

- `[[link|text]]` → text
- `{{s|状态}}` / `{{a|特性}}` / `{{i|道具}}` → 文本
- `{{特性效果/属性无效|水|回复}}` → 属性无效（水、回复）
- `{{MSP|...}}` → 移除（精灵图装饰）
- 表格、HTML 注释 → 移除

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/04_supplement_ability_effects.py
```

脚本幂等，可重复运行。

### 验证

```sql
SELECT count(*) FROM abilities WHERE effect_battle IS NOT NULL AND id < 10000;  -- 应 ~312
SELECT count(*) FROM abilities WHERE effect_overworld IS NOT NULL AND id < 10000;  -- 应 ~9
SELECT id, name_zh, effect_overworld FROM abilities WHERE effect_overworld IS NOT NULL AND id < 10000;
```

## 04_supplement_move_effects.py

补全 moves 表的 `effect_zh`（101 条，排除暗影招式 18 条）。

数据源：wikitext 文件的 `==招式附加效果==` section，展开 25 种 `招式效果/` 模板为纯中文文本。

### 匹配策略

复用 Step 2 的 6 轮匹配 + 3 条特例：919/937（98.1%）

### 模板展开

25 种招式效果模板（中毒/灼伤/能力提升/保护/天气影响等）+ 通用模板清理（{{m|}}、{{s|}}、{{type|}}、{{frac|}} 等）。

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/04_supplement_move_effects.py
```

脚本幂等，可重复运行。

### 验证

```sql
SELECT count(*) FROM moves WHERE effect_zh IS NULL OR effect_zh = '';  -- 应 18（暗影招式）
SELECT count(*) FROM moves WHERE effect_zh IS NOT NULL AND effect_zh != '';  -- 应 919
```

## 05_supplement_items.py

补全 items 表 449 条缺失的 `name_zh`。

### 数据源

`wiki_meta.db` 中 2619 个道具页面的标题（如"讲究头带（道具）"），通过 `name_en` 模糊匹配。

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/05_supplement_items.py
```

### 验证

```sql
SELECT count(*) FROM items WHERE name_zh IS NULL OR name_zh = '';  -- 应减少（部分游戏内部道具无 Wiki 页面）
```

## 06_create_evolutions.py

新建 evolutions 表，存储宝可梦进化关系。

### 建表

```sql
CREATE TABLE IF NOT EXISTS evolutions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pokemon_id      INTEGER NOT NULL,
    evolves_to_id   INTEGER NOT NULL,
    method          TEXT NOT NULL,
    level           INTEGER,
    item_name       TEXT,
    condition       TEXT,
    FOREIGN KEY (pokemon_id) REFERENCES pokemons(id),
    FOREIGN KEY (evolves_to_id) REFERENCES pokemons(id)
);
```

### 数据源

- 等级进化：`宝可梦进化等级列表` 页面的 `pokelist/catch` 模板
- 非等级进化：`宝可梦进化家族列表` 子页面

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/06_create_evolutions.py
```

### 验证

```sql
SELECT count(*) FROM evolutions;  -- 预期 ~525
SELECT method, count(*) FROM evolutions GROUP BY method;
```

## 07_expand_status.py

扩展 status 表，新增 12 列分类/机制属性，从 124 个状态变化 wiki 页面提取结构化数据。

### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| category | TEXT | abnormal / weather / terrain / field / stat_change / special |
| type_zh | TEXT | 属性（草/超能力/恶等） |
| duration | TEXT | 回合数（'5' / '3或4' / ''） |
| is_field | INTEGER | 是否场地效果 0/1 |
| affects_pokemon | INTEGER | 是否作用于宝可梦本体 0/1 |
| batonpass | INTEGER | 能否被接棒传递 0/1 |
| removable_by_defog | INTEGER | 能否被吹飞解除 0/1 |
| removable_by_spin | INTEGER | 能否被高速旋转解除 0/1 |
| blocked_by_safeguard | INTEGER | 能否被神秘守护阻止 0/1 |
| blocked_by_magicguard | INTEGER | 能否被魔法防守阻止 0/1 |
| blocked_by_substitute | INTEGER | 能否被替身阻止 0/1 |
| note | TEXT | 备注 |

### 数据源

- `wiki_meta.db` → `wiki_pages`（`title LIKE '%（状态）' AND status='done'`），124 条
- 通过 wikitext_cache 中的 `{{状态信息框}}` 模板提取全部字段
- 文件匹配：按标题匹配缓存文件名（含无 `（状态）` 后缀的 fallback）

### 分类规则（优先级从高到低）

1. name_zh 去后缀在 weather 表命中 → `weather`（8 条，乱流用（天气）后缀）
2. name_zh 去后缀在 terrains 表命中 → `terrain`（4 条）
3. 信息框 `category=异常` → `abnormal`（5 条）
4. `defog=yes` → `field`（11 条）
5. 名字含能力变化关键字 → `stat_change`（10 条）
6. 其余 → `special`（85 条）

### 结果

- 总行数：124（原有 7 条 + 新增 117 条）
- 跳过 2 条（昏厥无信息框、吃饱无英文名）
- category 分布：special 85 / field 11 / stat_change 10 / weather 7 / terrain 4 / abnormal 5

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/07_expand_status.py
```

脚本幂等，可重复运行。

### 验证

```sql
SELECT category, count(*) FROM status GROUP BY category;
SELECT count(*) FROM status WHERE effect_zh IS NOT NULL;
```

## 08_create_type_matchups.py

新建 type_matchups_by_gen 表，存储 Gen 1-10 每一代的 18×18 属性克制矩阵。

### 建表

```sql
CREATE TABLE IF NOT EXISTS type_matchups_by_gen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    generation      INTEGER NOT NULL,
    attacker_type   TEXT NOT NULL,
    defender_type   TEXT NOT NULL,
    effectiveness   REAL NOT NULL,
    UNIQUE(generation, attacker_type, defender_type)
);
```

### 数据源

18 个属性页面（如 `火（属性）.wiki`）的 `==属性相克==` section，含按世代分组的 `{{属性相克}}` 模板。

### 解析策略

只解析防御方字段，攻击方倍率通过反向推导：

| 模板字段 | 含义 | 倍率 | 能否反向推导攻击方 |
|---------|------|------|------------------|
| `weakto` | 被该属性打 2x | 2.0 | 能（对称） |
| `resist` | 被该属性打 0.5x | 0.5 | 能（对称） |
| `unaffected` | 被该属性打 0x（防御方免疫） | 0.0 | 不能（单向） |
| `noeffect` | 攻击该属性 0x（攻击方无效） | 0.0 | 不能（单向） |

关键：`unaffected` 和 `noeffect` 是单向关系，不能反向推导。例如钢页面 `unaffected1=毒` 表示钢免疫毒的攻击（毒→钢=0x），但钢攻击毒仍为 1x。

### 结果

- Gen 1: 225 条（15 属性，无钢/恶/妖精）
- Gen 2-5: 289 条/代（17 属性，无妖精）
- Gen 6-10: 324 条/代（18 属性）
- 总计: 3001 条
- 和现有 type_effectiveness 表（Gen 9）100% 一致

### 运行

```bash
python pokemon_data/createTable/csv/db_supplement/08_create_type_matchups.py
```

脚本幂等，可重复运行。

### 验证

```sql
SELECT generation, count(*) FROM type_matchups_by_gen GROUP BY generation;
-- Gen1: 225, Gen2-5: 289, Gen6+: 324

-- Gen1 无钢/妖精
SELECT * FROM type_matchups_by_gen WHERE generation = 1 AND (attacker_type = '钢' OR defender_type = '钢');
-- 应返回 0 行

-- Gen1 超能力/幽灵交互（wiki 记录了 Gen1 的 bug：幽灵打超能力=0x）
SELECT * FROM type_matchups_by_gen WHERE generation = 1 AND attacker_type = '超能力' AND defender_type = '幽灵';
-- effectiveness = 1.0（超能力打幽灵 = 1x）
SELECT * FROM type_matchups_by_gen WHERE generation = 1 AND attacker_type = '幽灵' AND defender_type = '超能力';
-- effectiveness = 0.0（幽灵打超能力 = 0x，Gen1 bug）

-- 和 type_effectiveness 表（当前世代）对比，应无差异
SELECT t1.attacker_type, t1.defender_type, t1.effectiveness, t2.effectiveness
FROM type_matchups_by_gen t1
JOIN (
    SELECT t_a.name_zh as attacker_type, t_d.name_zh as defender_type, e.effectiveness
    FROM type_effectiveness e
    JOIN types t_a ON e.attacker_type_id = t_a.id
    JOIN types t_d ON e.defender_type_id = t_d.id
) t2 ON t1.attacker_type = t2.attacker_type AND t1.defender_type = t2.defender_type
WHERE t1.generation = 9 AND ABS(t1.effectiveness - t2.effectiveness) > 0.01;
-- 应返回 0 行
```

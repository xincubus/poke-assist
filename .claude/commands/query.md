根据用户的查询请求，在 SQLite 数据库中搜索宝可梦相关数据并返回结果。

## 数据库信息

数据库路径：c:/Users/xincu/Desktop/pokemon/pokemon_data/pokemonData.db

## 可用的表及字段

### pokemons - 宝可梦基础信息
- id, pokedex_id, pokeapi_id
- name_zh（中文名）, name_ja（日文名）, name_en（英文名）
- is_default_form（是否默认形态）
- type1, type2, type1_id, type2_id（属性）
- ability1_name, ability2_name, hidden_ability_name（特性）
- hp, attack, defense, sp_attack, sp_defense, speed, total_stats（种族值）
- weight_kg, image_official_artwork
- description_zh, description_ja, description_en

### moves - 招式信息
- id, name_zh, name_ja, name_en
- type（属性英文）, type_id, damage_class（physical/special/status）
- power（威力）, accuracy（命中）, priority（优先度）, pp
- description_zh, description_ja, description_en
- learned_by_pokemon

### abilities - 特性信息
- id, name_zh, name_ja, name_en
- description_zh, description_ja, description_en
- pokemon_list（拥有该特性的宝可梦列表）

### items - 道具信息
- id, name_zh, name_ja, name_en
- category, fling_power, fling_effect
- description_zh, description_ja, description_en
- image_path

### types - 属性信息
- id, name_en, name_ja, name_zh

### type_effectiveness - 属性克制表
- attacker_type_id, defender_type_id
- effectiveness（0=无效, 0.5=效果不好, 1=普通, 2=效果拔群）

### pokemon_moves_sv - 第九世代（朱紫）宝可梦可学招式
- pokedex_id, pokeapi_id
- pokemon_name_zh, pokemon_name_ja, pokemon_name_en
- move_id, move_name_zh, move_name_en, move_name_ja
- learn_method（学习方式）, level（等级）
- version_group, generation

### pokemon_moves - 全世代宝可梦可学招式（同上结构）

### battle_terms - 对战术语映射表
- term（术语，如"极速"、"围巾"、"破受"）
- aliases（别名，逗号分隔，如"满速,最速"）
- category（分类：stat_spread/item_alias/role/mechanic/calc_concept/ev_nature）
- definition（含义解释）
- formula（计算公式，如有）
- related_field（关联的 pokemons 表字段，如 speed、attack）
- related_value（关联值，如道具英文名 Choice Scarf，可 JOIN items 表）
- language（术语语言，默认 zh）

## 查询规则

1. 使用 sqlite3 CLI 执行 SQL 查询：`sqlite3 c:/Users/xincu/Desktop/pokemon/pokemon_data/pokemonData.db "SQL语句"`
2. 支持中文、日文、英文模糊匹配，优先使用 LIKE '%关键词%' 进行模糊搜索
3. 涉及属性克制时，JOIN types 表获取属性名称
4. 查询结果以易读的表格或列表格式返回
5. 如果用户查询模糊，先搜索匹配的记录，再根据结果进一步查询
6. **术语识别与自学习**：当用户查询中包含可能的对战术语时，按以下流程处理：
   - **第一步：查表**。用 `SELECT * FROM battle_terms WHERE term = '术语' OR aliases LIKE '%术语%'` 查询
   - **第二步：命中则使用**。如果查到了，用 definition/formula/related_field/related_value 辅助构造后续查询
   - **第三步：未命中则自学习**。如果 battle_terms 中没有该术语，则：
     1. 根据 LLM 自身对宝可梦对战的知识，判断该词是否属于对战术语（而非宝可梦名/招式名等普通词汇）
     2. 如果确认是对战术语，构造一条 INSERT 语句写入 battle_terms 表，字段要求：
        - `term`：术语原文
        - `aliases`：常见别名，逗号分隔（没有则留空）
        - `category`：从 stat_spread / item_alias / role / mechanic / calc_concept / ev_nature / ability_alias / move_category / strategy 中选择最合适的
        - `definition`：简明的中文解释
        - `formula`：如涉及数值计算则填写公式，否则留空
        - `related_field`：如关联 pokemons 表字段则填写（如 speed, attack），否则留空
        - `related_value`：如关联道具/特性/招式英文名则填写（方便 JOIN），否则留空
     3. 执行 INSERT 后，告知用户"已学习新术语：XXX"
     4. 继续用该术语的含义完成用户的原始查询
   - **注意**：只对真正的对战术语/黑话触发自学习，普通词汇（宝可梦名、招式名、道具全称等已存在于其他表的数据）不要写入 battle_terms

## 示例查询场景
- 查询宝可梦种族值：SELECT name_zh, hp, attack, defense, sp_attack, sp_defense, speed, total_stats FROM pokemons WHERE name_zh LIKE '%喷火龙%'
- 查询属性克制：SELECT t1.name_zh as 攻击属性, t2.name_zh as 防御属性, te.effectiveness FROM type_effectiveness te JOIN types t1 ON te.attacker_type_id=t1.id JOIN types t2 ON te.defender_type_id=t2.id WHERE t1.name_zh='火'
- 查询招式信息：SELECT name_zh, type, damage_class, power, accuracy, description_zh FROM moves WHERE name_zh LIKE '%地震%'
- 查询宝可梦可学招式：SELECT move_name_zh, learn_method, level FROM pokemon_moves_sv WHERE pokemon_name_zh LIKE '%皮卡丘%'

## 用户查询

$ARGUMENTS

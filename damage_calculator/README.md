# damage_calculator - 宝可梦伤害计算器

基于 [NCP VGC Damage Calculator](https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator) 的宝可梦对战伤害计算工具，支持中文输入，支持 Gen 1-9 及 Champions。

## 架构

```
用户（中文输入）
    │
    ▼
calc_cli.py ──解析"A对B使用C"──▶ cale_chinese_calculator.py
                                      │
                                      │ 从 pokemonData.db 加载
                                      │ 中文名 → normalize(英文名)
                                      │ （只保留字母，小写）
                                      ▼
                              cale_pokemon_damage_calculator.py
                                      │
                                      │ stdin/stdout JSON 行协议（常驻进程）
                                      ▼
                                cale/calculator.js (--persistent)
                                      │
                                      │ normalize → NCP 真实 key
                                      │ NCP 计算引擎（纯 JS，无 DOM）
                                      ▼
                               cale/damage_SV.js + damage_MASTER.js
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `cale/calculator.js` | Node.js 入口，加载 NCP 数据/引擎，含 normalize 映射表（Python 发送的 normalized key → NCP 真实 key），自动检测 Aura/Ruin 特性并设置 `_calcConfig`，2-5 连续攻击默认 3 次（Skill Link→5、Loaded Dice→4，与网页版一致），支持 `--persistent` 模式（stdin 行读取循环，常驻进程）和 CLI 模式（单次 `process.argv[2]`） |
| `cale/damage_SV.js` | NCP 核心计算（Gen 7-10），已去除 2 行 DOM 调用 |
| `cale/damage_MASTER.js` | NCP 公共函数库，16 处 jQuery DOM 读取已替换为 `_calcConfig` 参数 |
| `cale/stat_data.js` | 能力值计算纯函数版（Gen 1-9 + Champions），已去除所有 DOM 依赖 |
| `cale/ko_chance.js` | KO 概率计算（原版未修改） |
| `cale/pokedex.js` | 宝可梦数据（Gen 1-9 + Champions），已加 null guard |
| `cale/move_data.js` | 招式数据（原版未修改） |
| `cale/item_data.js` | 道具数据（原版未修改） |
| `cale/ability_data.js` | 特性数据（原版未修改） |
| `cale/nature_data.js` | 性格数据（原版未修改） |
| `cale/type_data.js` | 属性克制表（原版未修改） |
| `cale/cooldown_za.js` | Legends Z-A 冷却数据（原版未修改） |
| `cale_pokemon_damage_calculator.py` | Python 桥接层，继承 PokemonDamageCalculator，指向 cale/calculator.js |
| `cale_chinese_calculator.py` | 中文翻译层，继承 ChineseDamageCalculator，覆盖天气/状态映射为 NCP 格式，mega/primal 后缀转前缀 normalize，多形态宝可梦 name+form 拆分 |
| `calculator.js` | 旧版引擎（@smogon/calc v0.9.0，仅 Gen 9，已弃用） |
| `pokemon_damage_calculator.py` | Python 桥接基类，支持两种模式：常驻 Node.js 进程（`persistent=True`，通过 `PersistentNodeProcess` 管理 stdin/stdout 通信，单次调用 ~1ms）或传统 subprocess（每次启动新进程，~100ms） |
| `chinese_calculator.py` | 中文翻译基类，从数据库加载中→英映射，名称统一 normalize（只保留字母小写） |
| `calc_cli.py` | CLI 入口，解析 "攻击方对防御方使用招式" 格式的自然语言输入 |
| `test_normalize.py` | 测试脚本，验证 Python normalize + form 拆分后能否匹配 JS 端 NCP key |
| `cale/dump_ncp_keys.js` | 导出 NCP 所有 key 供 test_normalize.py 验证 |

## 使用方式

### CLI 快速计算

```bash
python calc_cli.py "原始盖欧卡对故勒顿使用喷水"
```

默认使用：攻击方 252特攻/252速度/4HP 胆小，防御方 252HP/4特防/252速度。

### Python 中文接口

```python
from cale_chinese_calculator import CaleChineseDamageCalculator

calc = CaleChineseDamageCalculator()  # 自动从 pokemonData.db 加载映射
result = calc.calculate_chinese(
    attacker_name='盖欧卡',
    defender_name='固拉多',
    move_name='喷水',
    attacker_evs={'spa': 252},
    attacker_nature='内敛',
    attacker_ability='降雨',
    attacker_item='讲究眼镜',
    weather='下雨',
)
```

### Python 英文接口

```python
from cale_pokemon_damage_calculator import CalePokemonDamageCalculator

calc = CalePokemonDamageCalculator()
result = calc.calculate(
    attacker_name='Kyogre',
    defender_name='Groudon',
    move_name='Water Spout',
    attacker_evs={'spa': 252},
    attacker_nature='Modest',
    attacker_ability='Drizzle',
    attacker_item='Choice Specs',
    weather='Rain',
)
```

### 支持的参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `attacker/defender_evs` | 努力值（Gen 1-9） | `{'hp': 252, 'atk': 252, 'spe': 4}` |
| `attacker/defender_sps` | 点数（Gen 10 Champions，每项0-32） | `{'spa': 32, 'spe': 32}` |
| `attacker/defender_nature` | 性格 | `'胆小'` / `'Timid'` |
| `attacker/defender_ability` | 特性 | `'始源之海'` / `'Primordial Sea'` |
| `attacker/defender_item` | 道具 | `'讲究眼镜'` / `'Choice Specs'` |
| `attacker/defender_boosts` | 能力变化 | `{'spa': 2}` (特攻+2) |
| `attacker/defender_status` | 异常状态 | `'烧伤'` / `'Burned'` |
| `attacker/defender_cur_hp` | 当前HP% | `100` (0-100) |
| `attacker/defender_tera_type` | 太晶属性 | `'水'` / `'Water'` |
| `attacker/defender_is_terastallized` | 是否开启太晶化 | `True` / `False` |
| `attacker/defender_form` | 形态（自动拆分，通常无需手动指定） | `'hero'` / `'f'` |
| `weather` | 天气 | `'大雨'`/`'大晴天'`/`'沙暴'`/`'雪'` |
| `terrain` | 场地 | `'电气场地'`/`'青草场地'`/`'精神场地'`/`'薄雾场地'` |
| `is_critical_hit` | 急所 | `True` / `False` |
| `is_reflect` / `is_light_screen` | 壁 | `True` / `False` |
| `is_aurora_veil` | 极光幕 | `True` / `False` |
| `generation` | 世代 | `10`（默认，Champions）|
| `mode` | 对战模式 | `'Singles'`（单打）/ `'Doubles'`（双打，默认）|

### 返回结果

```python
{
    'success': True,
    'damage': [183, 184, ...],       # 16个可能的伤害值
    'damageRange': [183, 216],       # 最小/最大伤害
    'description': '252 SpA ...',    # 完整描述
    'kochance': {'text': 'guaranteed OHKO'},  # 击杀概率
    'attacker': {'name': '...', 'stats': {...}},
    'defender': {'name': '...', 'stats': {...}, 'hp': 341},
}
```

## 名称匹配机制（normalize）

Python 端和 JS 端通过 **normalize**（只保留英文字母 + 小写）消除大小写、连字符、空格等格式差异：

```
DB name_en          Python normalize     JS normalize         NCP 真实 key
─────────────       ─────────────────    ─────────────────    ───────────────
light-of-ruin    →  lightofruin       =  lightofruin       →  Light of Ruin
will-o-wisp      →  willowisp         =  willowisp         →  Will-O-Wisp
charizard-mega-y →  megacharizardy    =  megacharizardy    →  Mega Charizard Y
kyogre-primal    →  primalkyogre      =  primalkyogre      →  Primal Kyogre
slowking-galar   →  slowkinggalar     =  slowkinggalar     →  Slowking-Galar
```

- **Python**：`_normalize_name()` 去除非字母字符并小写；`_normalize_pokemon_name()` 额外处理 mega/primal 后缀→前缀
- **JS**：`buildNormalizeMaps()` 在 `setGeneration()` 末尾构建 8 个反向映射表（moves/pokedex/natures/abilities/items/weather/terrain/status）

### 多形态宝可梦 form 拆分

部分宝可梦在 DB 中以 `base-form` 格式存储（如 `basculegion-male`），normalize 后无法直接匹配 NCP key（如 `Basculegion`）。通过 pokedex_id 分组拆分 base + form：

```
DB name_en                  base          form              JS 匹配逻辑
─────────────────           ──────────    ────────────      ─────────────────
basculegion-male         →  basculegion   (默认形态,空)   →  basculegion → Basculegion
basculegion-female       →  basculegion   f               →  basculegionf → Basculegion-F
palafin-hero             →  palafin       hero            →  palafinhero → Palafin-Hero
tauros-paldea-combat-breed→ tauros        paldeacombat    →  taurospaldeacombat → Tauros-Paldea-Combat
aegislash-blade          →  aegislash     blade           →  aegislashblade → Aegislash-Blade
```

- **Python `_split_form()`**：mega/primal 走正则（保持前缀式转换），其余多形态按首个 `-` 拆分
- **Python `_process_form()`**：默认形态（male/disguised/busted 等）→ 空；`female` → `f`；`-breed` 后缀去掉
- **JS `buildPokemon()`**：依次尝试 `name+form`（后缀式）→ `form+name`（前缀式）→ `name`（兜底）
- 参数通过 `attacker_form` / `defender_form` 传递

## 依赖

- **Node.js**：运行 cale/calculator.js
- **Python 3.9+**：运行 Python 层
- 无需 npm 包（NCP 引擎为纯 JS，已内置在 `cale/` 目录）

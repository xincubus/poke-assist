根据用户的描述，调用宝可梦伤害计算器计算对战伤害。

## 计算器位置

计算器路径：c:/Users/xincu/Desktop/pokemon/damage_calculator/

## 调用方式

### 方式一：CLI 快捷调用（简单场景）

```bash
cd c:/Users/xincu/Desktop/pokemon && python damage_calculator/calc_cli.py "攻击方对防御方使用招式"
```

注意：CLI 方式使用硬编码的默认努力值（攻击方: 252特攻/252速度/4HP 胆小，防御方: 252HP/4特防/252速度），适合快速估算。

### 方式二：Python 调用（精确控制参数）

```python
import sys
sys.path.insert(0, 'c:/Users/xincu/Desktop/pokemon')
from damage_calculator.chinese_calculator import ChineseDamageCalculator

calc = ChineseDamageCalculator(
    mapping_file='c:/Users/xincu/Desktop/pokemon/damage_calculator/name_mappings.json'
)
result = calc.calculate_chinese(
    attacker_name='攻击方中文名',
    defender_name='防御方中文名',
    move_name='招式中文名',
    # 以下为可选参数
    attacker_evs={'hp': 0, 'atk': 0, 'def': 0, 'spa': 252, 'spd': 0, 'spe': 252},
    defender_evs={'hp': 252, 'atk': 0, 'def': 0, 'spa': 0, 'spd': 4, 'spe': 252},
    attacker_nature='胆小',        # 性格
    defender_nature='胆小',
    attacker_ability='始源之海',    # 特性
    defender_ability='日照',
    attacker_item='讲究眼镜',      # 道具
    defender_item='突击背心',
    attacker_boosts={'spa': 1},    # 能力变化（-6 到 +6）
    defender_boosts={},
    attacker_status='',            # 状态：烧伤/麻痹/中毒/剧毒/睡眠/冰冻
    defender_status='',
    attacker_cur_hp=100,           # 当前HP百分比（0-100）
    defender_cur_hp=100,
    attacker_tera_type='水',       # 太晶属性
    defender_tera_type='',
    weather='大雨',                # 天气：大晴天/大雨/沙暴/雪/终极强光/始源大海
    terrain='',                    # 场地：电气场地/青草场地/精神场地/薄雾场地
    is_critical_hit=False,         # 是否急所
    is_reflect=False,              # 是否有反射壁
    is_light_screen=False,         # 是否有光墙
    generation=9,                  # 世代（默认9）
)
```

### 方式三：英文接口调用

```python
from damage_calculator.pokemon_damage_calculator import PokemonDamageCalculator
calc = PokemonDamageCalculator(
    node_script_path='c:/Users/xincu/Desktop/pokemon/damage_calculator/calculator.js'
)
result = calc.calculate(
    attacker_name='Kyogre-Primal',
    defender_name='Koraidon',
    move_name='Water Spout',
    weather='Heavy Rain',
    # ... 其他英文参数
)
```

## 返回结果结构

```python
{
    'success': True/False,
    'damage': [...],              # 原始伤害数组（16个可能的伤害值）
    'damageRange': [min, max],    # 伤害范围
    'description': '...',         # 完整伤害描述文本
    'kochance': {'text': '...'},  # 击杀概率描述
    'attacker': {'name': '...', 'stats': {...}},
    'defender': {'name': '...', 'stats': {...}, 'hp': ...},
    'error': '...'                # 仅在 success=False 时存在
}
```

## 支持的中文名称映射

映射文件：`damage_calculator/name_mappings.json`，包含：
- pokemon_names：宝可梦中文名 → 英文名
- move_names：招式中文名 → 英文名
- ability_names：特性中文名 → 英文名
- item_names：道具中文名 → 英文名
- nature_names：性格中文名 → 英文名
- weather_names：天气中文名 → 英文名
- terrain_names：场地中文名 → 英文名
- status_names：状态中文名 → 英文代码
- type_names：属性中文名 → 英文名

注意：如果用户提到的名称不在映射文件中，需要先在 pokemonData.db 中查询英文名，然后使用英文接口调用。

## 任务

解析用户描述中的攻击方、防御方、招式、努力值、性格、道具、特性、天气、场地等信息，用合适的参数调用计算器。如果用户没有指定某些参数，使用合理的 VGC 对战默认值。

## 输出格式

以自然对话的语气回复，而不是直接展示原始数据。回复需包含以下要素：

1. **伤害范围**：用百分比表示（如"大约能打 85%~100% 的血量"）
2. **击杀概率**：用口语化表达（如"有很大概率一发带走"、"基本上两下就倒了"、"一发是打不死的"）
3. **关键条件说明**：简要提及使用的默认配置（如性格、努力值、道具等），特别是当这些会显著影响结果时
4. **对战建议**（可选）：如果结果有明显的对战含义，可以简短补充（如"建议换一只来挡"、"带个气腰就稳了"）

### 示例回复风格

> 盖欧卡（胆小 252特攻）对固拉多（252HP/4特防）使用冲浪的话，大约能打 **78.2%~92.5%** 的血量，一发是打不死的，但如果对面有消耗的话两下基本稳了。不过要注意固拉多的日照特性会削弱水系招式的威力，实际对战中如果盖欧卡先上场抢到天气会更好。

用户输入：$ARGUMENTS

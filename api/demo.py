"""
完整的 API 演示和测试
"""
import sys
import os

# Windows 控制台编码修复
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 设置路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "damage_calculator"))

print("=" * 70)
print("宝可梦助手 API - 功能演示")
print("=" * 70)
print()

# 导入服务
from api.query_service import PokemonQueryService
from api.chat_service import ChatService
from chinese_calculator import ChineseDamageCalculator

# 初始化服务
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")

query_service = PokemonQueryService(db_path=DB_PATH)
damage_calc = ChineseDamageCalculator(db_path=DB_PATH)
chat_service = ChatService(query_service=query_service, damage_calc=damage_calc)

# 演示 1: 查询服务
print("【演示 1】查询宝可梦信息")
print("-" * 70)
result = query_service.search_pokemon("喷火龙")
if result:
    pokemon = result[0]
    print(f"名称: {pokemon['name_zh']} ({pokemon['name_en']})")
    print(f"属性: {pokemon['type1']}" + (f"/{pokemon['type2']}" if pokemon['type2'] else ""))
    print(f"种族值: HP{pokemon['hp']} 攻{pokemon['attack']} 防{pokemon['defense']} "
          f"特攻{pokemon['sp_attack']} 特防{pokemon['sp_defense']} 速{pokemon['speed']}")
    print(f"总和: {pokemon['total_stats']}")
print()

# 演示 2: 招式查询
print("【演示 2】查询招式信息")
print("-" * 70)
result = query_service.search_moves("地震")
if result:
    move = result[0]
    print(f"招式: {move['name_zh']} ({move['name_en']})")
    print(f"属性: {move['type']} | 分类: {move['damage_class']}")
    print(f"威力: {move['power']} | 命中: {move['accuracy']} | PP: {move['pp']}")
    print(f"说明: {move['description_zh']}")
print()

# 演示 3: 伤害计算
print("【演示 3】伤害计算")
print("-" * 70)
try:
    result = damage_calc.calculate_chinese(
        attacker_name="盖欧卡",
        defender_name="固拉多",
        move_name="冲浪"
    )
    if result.get("success"):
        print(result.get("description"))
        print(result.get("kochance", {}).get("text", ""))
    else:
        print(f"计算失败: {result.get('error')}")
except Exception as e:
    print(f"计算出错: {e}")
print()

# 演示 4: 聊天服务 - 伤害计算意图
print("【演示 4】聊天服务 - 伤害计算")
print("-" * 70)
result = chat_service.process_message("盖欧卡对固拉多使用冲浪")
print(f"识别类型: {result['type']}")
print(f"响应: {result['response']}")
print()

# 演示 5: 聊天服务 - 查询意图
print("【演示 5】聊天服务 - 查询意图")
print("-" * 70)
result = chat_service.process_message("查询喷火龙的种族值")
print(f"识别类型: {result['type']}")
print(f"响应: {result['response']}")
print()

# 演示 6: 属性克制查询
print("【演示 6】属性克制查询")
print("-" * 70)
result = query_service.get_type_effectiveness("火")
print("火属性的克制关系:")
for row in result[:5]:  # 只显示前5个
    eff = row['effectiveness']
    symbol = "✓✓" if eff == 2 else "✓" if eff == 1 else "✗" if eff == 0.5 else "✗✗"
    print(f"  {symbol} 对{row['defender_type']}: {eff}x")
print()

print("=" * 70)
print("演示完成！")
print("=" * 70)
print()
print("要启动完整的 API 服务，请运行:")
print("  python main.py")
print()
print("然后访问: http://localhost:8000/docs")

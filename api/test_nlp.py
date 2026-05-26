"""
测试自然语言解析
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

from api.query_service import PokemonQueryService
from api.chat_service import ChatService
from chinese_calculator import ChineseDamageCalculator

# 初始化服务
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")

query_service = PokemonQueryService(db_path=DB_PATH)
damage_calc = ChineseDamageCalculator(db_path=DB_PATH)
chat_service = ChatService(query_service=query_service, damage_calc=damage_calc)

print("=" * 70)
print("自然语言解析测试")
print("=" * 70)
print()

# 测试用例
test_cases = [
    "盖欧卡对固拉多使用冲浪",
    "头戴太火故勒顿使用闪焰冲锋能秒密勒顿吗",
    "故勒顿闪焰冲锋能秒密勒顿吗",
    "252特攻胆小盖欧卡的根源波动打固拉多",
    "盖欧卡的冲浪能秒固拉多吗",
]

for i, test in enumerate(test_cases, 1):
    print(f"【测试 {i}】{test}")
    print("-" * 70)

    # 解析参数
    intent, params = chat_service.parse_intent(test)
    print(f"意图: {intent}")
    print(f"解析结果:")
    for key, value in params.items():
        print(f"  {key}: {value}")

    # 处理消息
    result = chat_service.process_message(test)
    print(f"响应类型: {result['type']}")
    print(f"成功: {result['success']}")
    if result['success']:
        print(f"响应: {result['response'][:100]}...")
    else:
        print(f"错误: {result['response']}")

    print()

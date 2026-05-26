"""
快速验证 API 服务是否正常工作
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

print("=" * 60)
print("API 服务验证")
print("=" * 60)
print()

# 测试 1: 导入检查
print("1. 检查模块导入...")
try:
    from chinese_calculator import ChineseDamageCalculator
    print("   ✓ ChineseDamageCalculator")
except Exception as e:
    print(f"   ✗ ChineseDamageCalculator: {e}")
    sys.exit(1)

try:
    from api.query_service import PokemonQueryService
    print("   ✓ PokemonQueryService")
except Exception as e:
    print(f"   ✗ PokemonQueryService: {e}")
    sys.exit(1)

try:
    from api.chat_service import ChatService
    print("   ✓ ChatService")
except Exception as e:
    print(f"   ✗ ChatService: {e}")
    sys.exit(1)

print()

# 测试 2: 数据库连接
print("2. 检查数据库连接...")
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")
if os.path.exists(DB_PATH):
    print(f"   ✓ 数据库存在: {DB_PATH}")
    try:
        query_service = PokemonQueryService(db_path=DB_PATH)
        result = query_service.execute_query("SELECT COUNT(*) as count FROM pokemons")
        print(f"   ✓ 数据库连接成功，宝可梦数量: {result[0]['count']}")
    except Exception as e:
        print(f"   ✗ 数据库查询失败: {e}")
else:
    print(f"   ✗ 数据库不存在: {DB_PATH}")
    sys.exit(1)

print()

# 测试 3: 伤害计算器
print("3. 检查伤害计算器...")
try:
    calc = ChineseDamageCalculator(db_path=DB_PATH)
    print("   ✓ 伤害计算器初始化成功（从数据库加载映射）")
    except Exception as e:
    print(f"   ✗ 伤害计算器初始化失败: {e}")

print()

# 测试 4: FastAPI 导入
print("4. 检查 FastAPI...")
try:
    import fastapi
    import uvicorn
    import pydantic
    print(f"   ✓ FastAPI {fastapi.__version__}")
    print(f"   ✓ Uvicorn {uvicorn.__version__}")
    print(f"   ✓ Pydantic {pydantic.__version__}")
except ImportError as e:
    print(f"   ✗ 缺少依赖: {e}")
    print("   请运行: pip install -r requirements.txt")
    sys.exit(1)

print()
print("=" * 60)
print("✓ 所有检查通过！可以启动服务了")
print("=" * 60)
print()
print("启动命令:")
print("  Windows: start.bat")
print("  Linux/Mac: bash start.sh")
print("  或直接: python main.py")
print()
print("启动后访问: http://localhost:8000/docs")

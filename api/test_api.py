"""
API 测试脚本
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_root():
    """测试根路径"""
    print("=" * 50)
    print("测试 1: 根路径")
    print("=" * 50)
    response = requests.get(f"{BASE_URL}/")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_chat_greeting():
    """测试聊天 - 问候"""
    print("=" * 50)
    print("测试 2: 聊天接口 - 问候")
    print("=" * 50)
    data = {
        "message": "你好"
    }
    response = requests.post(f"{BASE_URL}/api/chat", json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_chat_damage_calc():
    """测试聊天 - 伤害计算"""
    print("=" * 50)
    print("测试 3: 聊天接口 - 伤害计算")
    print("=" * 50)
    data = {
        "message": "盖欧卡对固拉多使用根源波动"
    }
    response = requests.post(f"{BASE_URL}/api/chat", json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_query():
    """测试查询接口"""
    print("=" * 50)
    print("测试 4: 查询接口")
    print("=" * 50)
    data = {
        "query": "查询喷火龙的种族值"
    }
    response = requests.post(f"{BASE_URL}/api/query", json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_damage_calc():
    """测试伤害计算接口"""
    print("=" * 50)
    print("测试 5: 伤害计算接口")
    print("=" * 50)
    data = {
        "attacker_name": "盖欧卡",
        "defender_name": "固拉多",
        "move_name": "冲浪",
        "attacker_evs": {"spa": 252, "spe": 252, "hp": 4},
        "attacker_nature": "胆小"
    }
    response = requests.post(f"{BASE_URL}/api/damage-calc", json=data)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"错误: {response.text}")
    print()

if __name__ == "__main__":
    print("\n开始测试 API...\n")

    try:
        test_root()
        test_chat_greeting()
        test_chat_damage_calc()
        test_query()
        test_damage_calc()

        print("=" * 50)
        print("所有测试完成！")
        print("=" * 50)

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器！")
        print("请先启动服务: cd api && python main.py")
    except Exception as e:
        print(f"❌ 测试出错: {str(e)}")

"""
命令行伤害计算工具
用法: python calc_cli.py "原始盖欧卡对故勒顿使用喷水"
"""

import sys
from chinese_calculator import ChineseDamageCalculator


def parse_simple_query(query: str) -> dict:
    """
    简单解析用户查询
    格式: "攻击方对防御方使用招式"
    """
    # 简单的字符串解析
    if '对' in query and '使用' in query:
        parts = query.split('对')
        attacker = parts[0].strip()

        parts2 = parts[1].split('使用')
        defender = parts2[0].strip()
        move = parts2[1].strip()

        return {
            'attacker_name': attacker,
            'defender_name': defender,
            'move_name': move,
        }
    else:
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python calc_cli.py \"原始盖欧卡对故勒顿使用喷水\"")
        print("\n示例:")
        print("  python calc_cli.py \"原始盖欧卡对故勒顿使用喷水\"")
        print("  python calc_cli.py \"密勒顿对卡璞·鸣鸣使用流星群\"")
        sys.exit(1)

    query = sys.argv[1]
    print(f"查询: {query}")
    print("=" * 60)

    # 解析查询
    params = parse_simple_query(query)
    if not params:
        print("错误: 无法解析查询，请使用格式 \"攻击方对防御方使用招式\"")
        sys.exit(1)

    # 创建计算器
    calc = ChineseDamageCalculator()

    # 计算（使用默认配置）
    result = calc.calculate_chinese(
        attacker_name=params['attacker_name'],
        attacker_evs={'spa': 252, 'spe': 252, 'hp': 4},  # 默认特攻配置
        attacker_nature='胆小',

        defender_name=params['defender_name'],
        defender_evs={'hp': 252, 'spd': 4, 'spe': 252},  # 默认耐久配置

        move_name=params['move_name'],
    )

    if result['success']:
        print(f"\n[OK] 计算成功")
        print(f"\n攻击方: {result['attacker']['name']}")
        print(f"  实际能力值: HP={result['attacker']['stats']['hp']}, "
              f"特攻={result['attacker']['stats']['spa']}, "
              f"速度={result['attacker']['stats']['spe']}")

        print(f"\n防御方: {result['defender']['name']}")
        print(f"  实际能力值: HP={result['defender']['stats']['hp']}, "
              f"特防={result['defender']['stats']['spd']}, "
              f"速度={result['defender']['stats']['spe']}")

        print(f"\n[伤害] 范围: {result['damageRange'][0]} - {result['damageRange'][1]}")
        min_percent = result['damageRange'][0] / result['defender']['hp'] * 100
        max_percent = result['damageRange'][1] / result['defender']['hp'] * 100
        print(f"       百分比: {min_percent:.1f}% - {max_percent:.1f}%")

        print(f"\n[击杀] 概率: {result['kochance']['text']}")

        print(f"\n[描述] {result['description']}")

    else:
        print(f"\n[ERROR] 计算失败: {result['error']}")
        print("\n可能的原因:")
        print("  1. 宝可梦名称不正确（请检查 name_mappings.json）")
        print("  2. 招式名称不正确")
        print("  3. 其他参数错误")


if __name__ == '__main__':
    main()

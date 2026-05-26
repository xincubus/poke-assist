"""
为 abilities/moves/natures 表新增 name_ncp 字段并填充数据

NCP 名称格式：
- abilities: kebab-case -> Title Case (如 speed-boost -> Speed Boost)
- moves: kebab-case -> Title Case (如 karate-chop -> Karate Chop)
- natures: 已经是 Title Case (如 Hardy -> Hardy)
"""
import sqlite3
import os

# 数据库路径（从脚本目录向上 4 级到项目根目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR))))
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")


def kebab_to_title(name: str) -> str:
    """将 kebab-case 转换为 Title Case"""
    if not name:
        return name
    return name.replace("-", " ").title()


def add_ncp_fields():
    """为 abilities/moves/natures 表新增 name_ncp 字段并填充数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. abilities 表
    print("处理 abilities 表...")
    try:
        cursor.execute("ALTER TABLE abilities ADD COLUMN name_ncp TEXT")
        print("  新增 name_ncp 字段")
    except sqlite3.OperationalError:
        print("  name_ncp 字段已存在")

    # 填充 abilities.name_ncp
    cursor.execute("SELECT id, name_en FROM abilities WHERE name_en IS NOT NULL")
    abilities = cursor.fetchall()
    for ability_id, name_en in abilities:
        name_ncp = kebab_to_title(name_en)
        cursor.execute("UPDATE abilities SET name_ncp = ? WHERE id = ?", (name_ncp, ability_id))
    print(f"  更新 {len(abilities)} 条记录")

    # 2. moves 表
    print("\n处理 moves 表...")
    try:
        cursor.execute("ALTER TABLE moves ADD COLUMN name_ncp TEXT")
        print("  新增 name_ncp 字段")
    except sqlite3.OperationalError:
        print("  name_ncp 字段已存在")

    # 填充 moves.name_ncp
    cursor.execute("SELECT id, name_en FROM moves WHERE name_en IS NOT NULL")
    moves = cursor.fetchall()
    for move_id, name_en in moves:
        name_ncp = kebab_to_title(name_en)
        cursor.execute("UPDATE moves SET name_ncp = ? WHERE id = ?", (name_ncp, move_id))
    print(f"  更新 {len(moves)} 条记录")

    # 3. natures 表
    print("\n处理 natures 表...")
    try:
        cursor.execute("ALTER TABLE natures ADD COLUMN name_ncp TEXT")
        print("  新增 name_ncp 字段")
    except sqlite3.OperationalError:
        print("  name_ncp 字段已存在")

    # 填充 natures.name_ncp（已经是 Title Case，直接复制）
    cursor.execute("SELECT id, name_en FROM natures WHERE name_en IS NOT NULL")
    natures = cursor.fetchall()
    for nature_id, name_en in natures:
        # natures 的 name_en 已经是 Title Case，直接使用
        cursor.execute("UPDATE natures SET name_ncp = ? WHERE id = ?", (name_en, nature_id))
    print(f"  更新 {len(natures)} 条记录")

    # 提交更改
    conn.commit()

    # 验证结果
    print("\n验证结果：")
    cursor.execute("SELECT COUNT(*) FROM abilities WHERE name_ncp IS NOT NULL")
    print(f"  abilities: {cursor.fetchone()[0]} 条有 name_ncp")

    cursor.execute("SELECT COUNT(*) FROM moves WHERE name_ncp IS NOT NULL")
    print(f"  moves: {cursor.fetchone()[0]} 条有 name_ncp")

    cursor.execute("SELECT COUNT(*) FROM natures WHERE name_ncp IS NOT NULL")
    print(f"  natures: {cursor.fetchone()[0]} 条有 name_ncp")

    # 显示示例数据
    print("\n示例数据：")
    cursor.execute("SELECT name_en, name_ncp FROM abilities WHERE name_ncp IS NOT NULL LIMIT 5")
    print("  abilities:")
    for row in cursor.fetchall():
        print(f"    {row[0]} -> {row[1]}")

    cursor.execute("SELECT name_en, name_ncp FROM moves WHERE name_ncp IS NOT NULL LIMIT 5")
    print("  moves:")
    for row in cursor.fetchall():
        print(f"    {row[0]} -> {row[1]}")

    cursor.execute("SELECT name_en, name_ncp FROM natures WHERE name_ncp IS NOT NULL LIMIT 5")
    print("  natures:")
    for row in cursor.fetchall():
        print(f"    {row[0]} -> {row[1]}")

    conn.close()
    print("\n完成！")


if __name__ == "__main__":
    add_ncp_fields()

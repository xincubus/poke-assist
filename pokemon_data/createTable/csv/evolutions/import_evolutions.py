#!/usr/bin/env python3
"""
将 evolutions.csv 导入到 pokemonData.db 的 evolutions 表

用法：python import_evolutions.py
"""

import sqlite3
import csv
import os

# 路径配置
DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'pokemonData.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'evolutions.csv')

# 建表 SQL
CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS evolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_pokemon_id INTEGER NOT NULL,
    to_pokemon_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    level INTEGER,
    item_id INTEGER,
    condition TEXT,
    is_mega BOOLEAN DEFAULT 0,
    is_gmax BOOLEAN DEFAULT 0,
    FOREIGN KEY (from_pokemon_id) REFERENCES pokemons(id),
    FOREIGN KEY (to_pokemon_id) REFERENCES pokemons(id),
    FOREIGN KEY (item_id) REFERENCES items(id)
);
'''

CREATE_INDEX_SQL = [
    'CREATE INDEX IF NOT EXISTS idx_evolutions_from ON evolutions(from_pokemon_id);',
    'CREATE INDEX IF NOT EXISTS idx_evolutions_to ON evolutions(to_pokemon_id);',
    'CREATE INDEX IF NOT EXISTS idx_evolutions_method ON evolutions(method);',
]


def main():
    print('=== 导入进化关系数据 ===')

    # 检查 CSV 文件是否存在
    if not os.path.exists(CSV_PATH):
        print(f'错误: CSV 文件不存在: {CSV_PATH}')
        return

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 创建表
    print('创建 evolutions 表...')
    cur.execute(CREATE_TABLE_SQL)

    # 创建索引
    print('创建索引...')
    for sql in CREATE_INDEX_SQL:
        cur.execute(sql)

    # 清空现有数据
    cur.execute('DELETE FROM evolutions')
    print('已清空现有数据')

    # 读取 CSV 并插入
    print('读取 CSV 文件...')
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f'共 {len(rows)} 条记录')

    # 插入数据
    insert_sql = '''
    INSERT INTO evolutions (
        from_pokemon_id, to_pokemon_id, method,
        level, item_id, condition, is_mega, is_gmax
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    '''

    inserted = 0
    skipped = 0

    for row in rows:
        try:
            # 验证数据
            from_id = int(row['from_pokemon_id'])
            to_id = int(row['to_pokemon_id'])
            method = row['method']
            level = int(row['level']) if row['level'] else None
            item_id = int(row['item_id']) if row['item_id'] else None
            condition = row['condition'] if row['condition'] else None
            is_mega = int(row['is_mega'])
            is_gmax = int(row['is_gmax'])

            # 验证外键
            cur.execute('SELECT id FROM pokemons WHERE id = ?', (from_id,))
            if not cur.fetchone():
                print(f'警告: from_pokemon_id={from_id} 不存在，跳过')
                skipped += 1
                continue

            cur.execute('SELECT id FROM pokemons WHERE id = ?', (to_id,))
            if not cur.fetchone():
                print(f'警告: to_pokemon_id={to_id} 不存在，跳过')
                skipped += 1
                continue

            if item_id:
                cur.execute('SELECT id FROM items WHERE id = ?', (item_id,))
                if not cur.fetchone():
                    print(f'警告: item_id={item_id} 不存在，设为 NULL')
                    item_id = None

            # 插入数据
            cur.execute(insert_sql, (
                from_id, to_id, method,
                level, item_id, condition, is_mega, is_gmax
            ))
            inserted += 1

        except Exception as e:
            print(f'错误: {e}, 跳过该行')
            skipped += 1

    # 提交
    conn.commit()

    # 验证
    cur.execute('SELECT COUNT(*) FROM evolutions')
    total = cur.fetchone()[0]

    print(f'\n=== 导入完成 ===')
    print(f'成功插入: {inserted} 条')
    print(f'跳过: {skipped} 条')
    print(f'表中总计: {total} 条')

    # 统计
    cur.execute('SELECT method, COUNT(*) FROM evolutions GROUP BY method ORDER BY COUNT(*) DESC')
    print('\n=== method 统计 ===')
    for method, count in cur.fetchall():
        print(f'  {method}: {count}')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()

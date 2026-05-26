"""
名词库加载器 - 从数据库动态加载宝可梦相关名词
"""
import os
import sqlite3
from typing import Dict, List, Any


class VocabularyLoader:
    """名词库加载器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.vocabulary = {}

    def load_all(self) -> Dict[str, Any]:
        """加载所有名词库"""
        conn = sqlite3.connect(self.db_path)

        self.vocabulary = {
            'pokemons': self._load_pokemons(conn),
            'moves': self._load_moves(conn),
            'items': self._load_items(conn),
            'abilities': self._load_abilities(conn),
            'natures': self._load_natures(conn),
            'battle_terms': self._load_battle_terms(conn),
        }

        conn.close()
        return self.vocabulary

    def _load_pokemons(self, conn) -> List[Dict[str, str]]:
        """加载宝可梦名词"""
        cursor = conn.execute("""
            SELECT DISTINCT name_zh, name_en
            FROM pokemons
            WHERE name_zh IS NOT NULL AND name_en IS NOT NULL
            ORDER BY name_zh
        """)
        return [{'zh': row[0], 'en': row[1]} for row in cursor.fetchall()]

    def _load_moves(self, conn) -> List[Dict[str, str]]:
        """加载招式名词"""
        cursor = conn.execute("""
            SELECT DISTINCT name_zh, name_en, type, damage_class
            FROM moves
            WHERE name_zh IS NOT NULL AND name_en IS NOT NULL
            ORDER BY name_zh
        """)
        return [
            {'zh': row[0], 'en': row[1], 'type': row[2], 'class': row[3]}
            for row in cursor.fetchall()
        ]

    def _load_items(self, conn) -> List[Dict[str, str]]:
        """加载道具名词"""
        cursor = conn.execute("""
            SELECT DISTINCT name_zh, name_en
            FROM items
            WHERE name_zh IS NOT NULL AND name_en IS NOT NULL
            ORDER BY name_zh
        """)
        return [{'zh': row[0], 'en': row[1]} for row in cursor.fetchall()]

    def _load_abilities(self, conn) -> List[Dict[str, str]]:
        """加载特性名词"""
        cursor = conn.execute("""
            SELECT DISTINCT name_zh, name_en
            FROM abilities
            WHERE name_zh IS NOT NULL AND name_en IS NOT NULL
            ORDER BY name_zh
        """)
        return [{'zh': row[0], 'en': row[1]} for row in cursor.fetchall()]

    def _load_natures(self, conn) -> List[Dict[str, str]]:
        """加载性格名词"""
        cursor = conn.execute("""
            SELECT name_zh, name_en, increased_stat_zh, decreased_stat_zh
            FROM natures
            ORDER BY name_zh
        """)
        return [
            {
                'zh': row[0],
                'en': row[1],
                'plus': row[2] or '',
                'minus': row[3] or ''
            }
            for row in cursor.fetchall()
        ]

    def _load_battle_terms(self, conn) -> List[Dict[str, Any]]:
        """加载对战术语"""
        cursor = conn.execute("""
            SELECT term, aliases, category, definition, related_field, related_value
            FROM battle_terms
            WHERE language = 'zh'
            ORDER BY category, term
        """)
        terms = []
        for row in cursor.fetchall():
            term_data = {
                'term': row[0],
                'aliases': [a.strip() for a in row[1].split(',') if a.strip()] if row[1] else [],
                'category': row[2],
                'definition': row[3],
            }
            # 解析 related_field 和 related_value
            if row[4]:
                term_data['fields'] = row[4].split(',')
            if row[5]:
                term_data['value'] = row[5]
            terms.append(term_data)
        return terms

    def build_llm_prompt(self) -> str:
        """构建给 LLM 的名词库提示词（精简版）"""
        lines = []

        # 宝可梦（只列举常见的，避免提示词过长）
        if self.vocabulary.get('pokemons'):
            common_pokemons = [p['zh'] for p in self.vocabulary['pokemons'][:50]]
            lines.append(f"- 常见宝可梦：{', '.join(common_pokemons)}...")

        # 对战术语（重点）
        if self.vocabulary.get('battle_terms'):
            lines.append("\n- 对战术语：")
            for term in self.vocabulary['battle_terms']:
                aliases_str = f"（别名：{', '.join(term['aliases'])}）" if term['aliases'] else ""
                lines.append(f"  * {term['term']}{aliases_str}: {term['definition']}")

        # 性格
        if self.vocabulary.get('natures'):
            lines.append("\n- 性格：")
            for nature in self.vocabulary['natures']:
                if nature['plus'] and nature['minus']:
                    lines.append(f"  * {nature['zh']}（+{nature['plus']} -{nature['minus']}）")

        return '\n'.join(lines)


if __name__ == '__main__':
    # 测试
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pokemon_data', 'pokemonData.db')
    loader = VocabularyLoader(db_path)
    vocab = loader.load_all()

    print(f"加载完成：")
    print(f"  宝可梦: {len(vocab['pokemons'])} 个")
    print(f"  招式: {len(vocab['moves'])} 个")
    print(f"  道具: {len(vocab['items'])} 个")
    print(f"  特性: {len(vocab['abilities'])} 个")
    print(f"  性格: {len(vocab['natures'])} 个")
    print(f"  对战术语: {len(vocab['battle_terms'])} 个")

    print("\n生成的提示词：")
    print(loader.build_llm_prompt())

"""
HOME 使用率查询 Mixin：排名、单宝可梦详情、热门队伍
"""
import os
import sqlite3
from typing import Dict, Any

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_BASE_DIR, "pokemon_data", "pokemonData.db")
CHAMPIONS_USAGE_DB = os.path.join(_BASE_DIR, "home", "champions", "champions_usage.db")

_JA_TYPE_TO_ZH = {
    "ノーマル": "一般", "かくとう": "格斗", "ひこう": "飞行", "どく": "毒",
    "じめん": "地面", "いわ": "岩石", "むし": "虫", "ゴースト": "幽灵",
    "はがね": "钢", "ほのお": "火", "みず": "水", "くさ": "草",
    "でんき": "电", "エスパー": "超能力", "こおり": "冰", "ドラゴン": "龙",
    "あく": "恶", "フェアリー": "妖精",
}


class HomeQueryMixin:
    """HOME 对战使用率查询"""

    def _query_home_rankings(self, params: Dict[str, Any]) -> str:
        """get_home_rankings 工具：查询 HOME 对战使用率排名。"""
        if not os.path.exists(CHAMPIONS_USAGE_DB):
            return "HOME 对战数据不存在"

        season = params.get("season", 0)
        rule = params.get("rule", 0)
        limit = params.get("limit", 30)

        conn = sqlite3.connect(CHAMPIONS_USAGE_DB)
        conn.row_factory = sqlite3.Row
        try:
            # 确定赛季
            if season <= 0:
                row = conn.execute("SELECT MAX(season) FROM pokemon_rankings").fetchone()
                season = row[0] if row and row[0] else 1

            rows = conn.execute(
                "SELECT rank, pokemon_id, pokemon_name FROM pokemon_rankings "
                "WHERE season = ? AND rule = ? ORDER BY rank LIMIT ?",
                (season, rule, limit)
            ).fetchall()
            if not rows:
                return f"赛季 {season} 规则 {rule} 无排名数据"

            # 日→中映射
            ja_to_zh = self._build_home_pokemon_zh_map([r["pokemon_name"] for r in rows])

            lines = [f"【HOME 对战使用率排名】赛季 {season} | {'双打' if rule else '单打'}"]
            for r in rows:
                zh = ja_to_zh.get(r["pokemon_name"], r["pokemon_name"])
                lines.append(f"#{r['rank']} {zh}")
            return "\n".join(lines)
        finally:
            conn.close()

    def _query_pokemon_home_usage(self, params: Dict[str, Any]) -> str:
        """get_pokemon_home_usage 工具：查询单个宝可梦的 HOME 使用率详情。"""
        if not os.path.exists(CHAMPIONS_USAGE_DB):
            return "HOME 对战数据不存在"

        pokemon_name = params.get("pokemon_name", "")
        if not pokemon_name:
            return "请提供宝可梦名称"

        season = params.get("season", 0)
        rule = params.get("rule", 0)

        # 通过 pokemonData.db 找 home_id
        main_conn = sqlite3.connect(DB_PATH)
        main_conn.row_factory = sqlite3.Row
        try:
            poke_row = main_conn.execute(
                "SELECT home_id, name_zh, name_home FROM pokemons WHERE name_zh = ? OR name_en = ? OR name_home = ?",
                (pokemon_name, pokemon_name, pokemon_name)
            ).fetchone()
            if not poke_row:
                # 模糊匹配
                poke_row = main_conn.execute(
                    "SELECT home_id, name_zh, name_home FROM pokemons WHERE name_zh LIKE ? OR name_en LIKE ?",
                    (f"%{pokemon_name}%", f"%{pokemon_name}%")
                ).fetchone()
            if not poke_row:
                return f"未找到宝可梦「{pokemon_name}」"

            home_id = poke_row["home_id"]
            zh_name = poke_row["name_zh"]
            if not home_id:
                return f"「{zh_name}」没有 HOME 对战数据"

            conn = sqlite3.connect(CHAMPIONS_USAGE_DB)
            conn.row_factory = sqlite3.Row
            try:
                # 确定赛季
                if season <= 0:
                    row = conn.execute("SELECT MAX(season) FROM pokemon_usage").fetchone()
                    season = row[0] if row and row[0] else 1

                # 查排名
                rank_row = conn.execute(
                    "SELECT rank FROM pokemon_rankings WHERE season=? AND rule=? AND pokemon_id=?",
                    (season, rule, home_id)
                ).fetchone()

                # 查使用率详情
                usage_rows = conn.execute(
                    "SELECT data_type, name, usage_rate FROM pokemon_usage "
                    "WHERE season=? AND rule=? AND pokemon_id=? ORDER BY data_type, usage_rate DESC",
                    (season, rule, home_id)
                ).fetchall()

                if not usage_rows:
                    return f"「{zh_name}」在赛季 {season} {'双打' if rule else '单打'} 中无使用率数据"

                # 日→中映射（道具/特性/招式/性格）
                ja_names_by_type = {}
                for r in usage_rows:
                    ja_names_by_type.setdefault(r["data_type"], set()).add(r["name"])

                ja_to_zh_all = {}
                for dtype, ja_names in ja_names_by_type.items():
                    table_map = {"items": "items", "abilities": "abilities", "moves": "moves", "personalities": "natures"}
                    table = table_map.get(dtype)
                    if table and ja_names:
                        ja_to_zh_all.update(self._build_ja_to_zh_map(table, list(ja_names)))

                # Group by data_type
                type_labels = {
                    "abilities": "特性", "items": "道具", "moves": "招式",
                    "personalities": "性格",
                }

                lines = [f"【{zh_name} HOME 对战使用率】赛季 {season} | {'双打' if rule else '单打'}"]
                if rank_row:
                    lines.append(f"排名：#{rank_row['rank']}")
                lines.append("")

                for dtype in ["moves", "abilities", "items", "personalities"]:
                    type_rows = [r for r in usage_rows if r["data_type"] == dtype]
                    if not type_rows:
                        continue
                    label = type_labels.get(dtype, dtype)
                    lines.append(f"【{label}使用率】")
                    for r in type_rows[:10]:  # 每类最多显示 10 个
                        name_zh = ja_to_zh_all.get(r["name"], r["name"])
                        lines.append(f"  {name_zh}: {r['usage_rate']:.1f}%")
                    lines.append("")

                return "\n".join(lines).rstrip()
            finally:
                conn.close()
        finally:
            main_conn.close()

    def _query_home_teams(self, params: Dict[str, Any]) -> str:
        """get_home_teams 工具：查询 HOME 对战热门队伍。"""
        if not os.path.exists(CHAMPIONS_USAGE_DB):
            return "HOME 对战数据不存在"

        season = params.get("season", 0)
        rule = params.get("rule", 0)
        limit = params.get("limit", 10)

        conn = sqlite3.connect(CHAMPIONS_USAGE_DB)
        conn.row_factory = sqlite3.Row
        try:
            # 确定赛季
            if season <= 0:
                row = conn.execute("SELECT MAX(season) FROM team_rankings").fetchone()
                season = row[0] if row and row[0] else 1

            team_rows = conn.execute(
                "SELECT rank, rating FROM team_rankings "
                "WHERE season = ? AND rule = ? ORDER BY rank LIMIT ?",
                (season, rule, limit)
            ).fetchall()
            if not team_rows:
                return f"赛季 {season} 规则 {rule} 无队伍数据"

            # 批量查队伍成员
            ranks = [t["rank"] for t in team_rows]
            ph = ",".join(["?"] * len(ranks))
            pokemon_rows = conn.execute(
                f"SELECT rank, slot, pokemon_name, form, type1, type2, item "
                f"FROM team_pokemon WHERE season=? AND rule=? AND rank IN ({ph}) "
                f"ORDER BY rank, slot",
                [season, rule] + ranks
            ).fetchall()

            # 日→中映射
            ja_names = set(r["pokemon_name"] for r in pokemon_rows)
            ja_to_zh = self._build_home_pokemon_zh_map(list(ja_names))

            # 道具映射
            item_ja_names = set(r["item"] for r in pokemon_rows if r["item"])
            item_map = {}
            if item_ja_names:
                item_map = self._build_ja_to_zh_map("items", list(item_ja_names))

            # 按 rank 分组
            teams_by_rank = {}
            for r in pokemon_rows:
                teams_by_rank.setdefault(r["rank"], []).append(r)

            lines = [f"【HOME 对战热门队伍】赛季 {season} | {'双打' if rule else '单打'}"]
            for t in team_rows:
                rank = t["rank"]
                rating = t["rating"]
                lines.append(f"\n#{rank} (Rating: {rating:.0f})")
                members = teams_by_rank.get(rank, [])
                for m in members:
                    zh_name = ja_to_zh.get(m["pokemon_name"], m["pokemon_name"])
                    item_zh = item_map.get(m["item"], m["item"]) if m["item"] else ""
                    t1 = _JA_TYPE_TO_ZH.get(m["type1"], m["type1"])
                    t2 = _JA_TYPE_TO_ZH.get(m["type2"], m["type2"]) if m["type2"] else ""
                    type_str = f"{t1}/{t2}" if t2 else t1
                    item_str = f" @ {item_zh}" if item_zh else ""
                    lines.append(f"  {zh_name} ({type_str}){item_str}")

            return "\n".join(lines)
        finally:
            conn.close()

    def _build_home_pokemon_zh_map(self, ja_names: list) -> dict:
        """构建 HOME 日文宝可梦名 → 中文名映射。优先 name_home 精确匹配，fallback LIKE 模糊。"""
        if not ja_names:
            return {}
        ja_to_zh = {}
        main_conn = sqlite3.connect(DB_PATH)
        main_conn.row_factory = sqlite3.Row
        try:
            ph = ",".join(["?"] * len(ja_names))
            # 精确匹配
            rows = main_conn.execute(
                f"SELECT name_home, name_zh FROM pokemons WHERE name_home IN ({ph})",
                ja_names
            ).fetchall()
            for r in rows:
                if r["name_home"]:
                    ja_to_zh[r["name_home"]] = r["name_zh"]
            # LIKE 模糊 fallback（处理带性别/形态后缀的情况）
            unmatched = [n for n in ja_names if n not in ja_to_zh]
            for name in unmatched:
                row = main_conn.execute(
                    "SELECT name_home, name_zh FROM pokemons WHERE name_home LIKE ? AND home_id IS NOT NULL LIMIT 1",
                    (f"{name}%",)
                ).fetchone()
                if row:
                    ja_to_zh[name] = row["name_zh"]
        finally:
            main_conn.close()
        return ja_to_zh

    def _build_ja_to_zh_map(self, table: str, ja_names: list) -> dict:
        """构建日文名 → 中文名映射（道具/特性/招式/性格）。优先 name_home，fallback name_ja。"""
        if not ja_names:
            return {}
        ja_to_zh = {}
        main_conn = sqlite3.connect(DB_PATH)
        main_conn.row_factory = sqlite3.Row
        try:
            ph = ",".join(["?"] * len(ja_names))
            # name_home 匹配
            rows = main_conn.execute(
                f"SELECT name_home, name_zh FROM {table} WHERE name_home IN ({ph})",
                ja_names
            ).fetchall()
            for r in rows:
                if r["name_home"]:
                    ja_to_zh[r["name_home"]] = r["name_zh"]
            # fallback: name_ja
            unmatched = [n for n in ja_names if n not in ja_to_zh]
            if unmatched:
                ph2 = ",".join(["?"] * len(unmatched))
                rows2 = main_conn.execute(
                    f"SELECT name_ja, name_zh FROM {table} WHERE name_ja IN ({ph2})",
                    unmatched
                ).fetchall()
                for r in rows2:
                    if r["name_ja"]:
                        ja_to_zh[r["name_ja"]] = r["name_zh"]
        finally:
            main_conn.close()
        return ja_to_zh

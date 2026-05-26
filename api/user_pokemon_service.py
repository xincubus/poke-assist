"""
用户宝可梦/队伍同步服务
存储在 users.db，按 user_id 隔离
"""
import os
import sqlite3
from typing import List, Dict, Any, Optional


class UserPokemonService:
    def __init__(self, db_path: str):
        db_dir = os.path.dirname(db_path)
        self.db_path = os.path.join(db_dir, "users.db")
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_pokemon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    name_en TEXT,
                    base_hp INT, base_attack INT, base_defense INT,
                    base_sp_attack INT, base_sp_defense INT, base_speed INT,
                    ev_hp INT DEFAULT 0, ev_attack INT DEFAULT 0, ev_defense INT DEFAULT 0,
                    ev_sp_attack INT DEFAULT 0, ev_sp_defense INT DEFAULT 0, ev_speed INT DEFAULT 0,
                    nature TEXT, ability TEXT, item TEXT,
                    move1 TEXT, move2 TEXT, move3 TEXT, move4 TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    members TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def sync_pokemon(self, user_id: int, pokemon_list: List[Dict[str, Any]]):
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM user_pokemon WHERE user_id = ?", (user_id,))
            for p in pokemon_list:
                conn.execute("""
                    INSERT INTO user_pokemon
                    (user_id, name, name_en,
                     base_hp, base_attack, base_defense, base_sp_attack, base_sp_defense, base_speed,
                     ev_hp, ev_attack, ev_defense, ev_sp_attack, ev_sp_defense, ev_speed,
                     nature, ability, item, move1, move2, move3, move4)
                    VALUES (?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?,?)
                """, (
                    user_id, p.get("name", ""), p.get("name_en", ""),
                    p.get("base_hp", 0), p.get("base_attack", 0), p.get("base_defense", 0),
                    p.get("base_sp_attack", 0), p.get("base_sp_defense", 0), p.get("base_speed", 0),
                    p.get("ev_hp", 0), p.get("ev_attack", 0), p.get("ev_defense", 0),
                    p.get("ev_sp_attack", 0), p.get("ev_sp_defense", 0), p.get("ev_speed", 0),
                    p.get("nature", ""), p.get("ability", ""), p.get("item", ""),
                    p.get("move1", ""), p.get("move2", ""), p.get("move3", ""), p.get("move4", ""),
                ))
            conn.commit()
        finally:
            conn.close()

    def sync_teams(self, user_id: int, team_list: List[Dict[str, Any]]):
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM user_teams WHERE user_id = ?", (user_id,))
            for t in team_list:
                members = t.get("members", "")
                if isinstance(members, list):
                    members = ",".join(members)
                conn.execute(
                    "INSERT INTO user_teams (user_id, name, members) VALUES (?,?,?)",
                    (user_id, t.get("name", ""), members)
                )
            conn.commit()
        finally:
            conn.close()

    def get_user_pokemon(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM user_pokemon WHERE user_id = ?", (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_user_teams(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM user_teams WHERE user_id = ?", (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def format_user_context(self, user_id: int) -> Optional[str]:
        pokemon_list = self.get_user_pokemon(user_id)
        team_list = self.get_user_teams(user_id)
        if not pokemon_list and not team_list:
            return None

        parts = []
        if pokemon_list:
            lines = ["【用户已保存的宝可梦配置】"]
            for p in pokemon_list:
                sps = f"HP{p['ev_hp']}/攻击{p['ev_attack']}/防御{p['ev_defense']}/特攻{p['ev_sp_attack']}/特防{p['ev_sp_defense']}/速度{p['ev_speed']}"
                moves = ", ".join(m for m in [p["move1"], p["move2"], p["move3"], p["move4"]] if m)
                line = f"- {p['name']}"
                if p.get("name_en"):
                    line += f"({p['name_en']})"
                line += f" | 性格:{p['nature']} | 特性:{p['ability']}"
                if p.get("item"):
                    line += f" | 道具:{p['item']}"
                line += f" | 能力点数:{sps}"
                if moves:
                    line += f" | 招式:{moves}"
                lines.append(line)
            parts.append("\n".join(lines))

        if team_list:
            lines = ["【用户的队伍】"]
            for t in team_list:
                lines.append(f"- {t['name']}: {t['members']}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

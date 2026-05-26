"""
搜索路由：宝可梦、招式、道具搜索 + Mega 石查询
"""
import sqlite3

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["搜索"])

# 服务引用（由 init_services 设置）
_DB_PATH = None


def init_services(db_path: str):
    """注入数据库路径"""
    global _DB_PATH
    _DB_PATH = db_path


def _resolve_aliases(cur, keyword: str, category: str) -> list:
    """从 battle_terms 查别名，返回匹配到的 related_value 列表（英文名）"""
    cur.execute("""
        SELECT related_value FROM battle_terms
        WHERE category = ?
          AND (term LIKE ? OR aliases LIKE ?
               OR term_pinyin LIKE ? OR term_pinyin_abbr LIKE ?
               OR aliases_pinyin LIKE ? OR aliases_pinyin_abbr LIKE ?)
          AND related_value IS NOT NULL AND related_value != ''
    """, (category, f"%{keyword}%", f"%{keyword}%",
          f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
    names = []
    for row in cur.fetchall():
        for v in row[0].split(','):
            v = v.strip()
            if v:
                names.append(v)
    return names


@router.get("/pokemon/search")
async def search_pokemon(keyword: str, limit: int = 20):
    """搜索宝可梦（中英日名称模糊匹配）"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        alias_names = _resolve_aliases(cur, keyword, 'pokemon_alias')
        alias_clause = ""
        contain = f"%{keyword}%"
        prefix = f"{keyword}%"
        params = [contain] * 5
        if alias_names:
            placeholders = ','.join(['?'] * len(alias_names))
            alias_clause = f" OR p.name_en IN ({placeholders})"
            params.extend(alias_names)
        params.extend([prefix, prefix, prefix, limit])
        cur.execute(f"""
            SELECT p.id, p.pokedex_id, p.pokeapi_id, p.is_default_form,
                   p.name_zh, p.name_en, p.name_ja,
                   p.type1, p.type2,
                   t1.name_zh AS type1_zh, t1.color AS type1_color,
                   t2.name_zh AS type2_zh, t2.color AS type2_color,
                   COALESCE(a1.name_zh, p.ability1_name) AS ability1_name,
                   COALESCE(a2.name_zh, p.ability2_name) AS ability2_name,
                   COALESCE(ah.name_zh, p.hidden_ability_name) AS hidden_ability_name,
                   p.hp, p.attack, p.defense, p.sp_attack, p.sp_defense, p.speed
            FROM pokemons p
            LEFT JOIN abilities a1 ON p.ability1_name = a1.name_en
            LEFT JOIN abilities a2 ON p.ability2_name = a2.name_en
            LEFT JOIN abilities ah ON p.hidden_ability_name = ah.name_en
            LEFT JOIN types t1 ON LOWER(t1.name_en) = p.type1
            LEFT JOIN types t2 ON LOWER(t2.name_en) = p.type2
            WHERE p.name_zh LIKE ? OR p.name_en LIKE ? OR p.name_ja LIKE ?
               OR p.name_pinyin LIKE ? OR p.name_pinyin_abbr LIKE ?
               {alias_clause}
            ORDER BY CASE WHEN p.name_zh LIKE ? THEN 0
                          WHEN p.name_pinyin LIKE ? THEN 1
                          WHEN p.name_pinyin_abbr LIKE ? THEN 2
                          ELSE 3 END, p.pokedex_id
            LIMIT ?
        """, params)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            name_en = (d.get("name_en") or "").lower()
            if d.get("is_default_form"):
                img_id = f"{d.get('pokedex_id', 0):03d}"
            else:
                img_id = str(d.get("pokeapi_id", 0))
            d["image_official_artwork"] = f"pokemonImage/{img_id}-{name_en}-officialArtwork.png"
            rows.append(d)
        conn.close()
        return {"results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pokemon/{pokemon_id}/mega-stone")
async def get_mega_stone(pokemon_id: int):
    """查询宝可梦对应的 Mega 石道具（若为 Mega 形态）"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT i.name_zh, i.name_en
            FROM evolutions e
            JOIN items i ON e.item_id = i.id
            WHERE e.to_pokemon_id = ? AND e.item_id IS NOT NULL
            AND (e.is_mega = 1 OR e.method = 'hold-item')
        """, (pokemon_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            name = row["name_zh"] or row["name_en"]
            return {"item_name": name}
        return {"item_name": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pokemon/{pokedex_id}")
async def get_pokemon(pokedex_id: int):
    """通过图鉴编号获取宝可梦完整数据"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT p.pokedex_id, p.pokeapi_id, p.is_default_form,
                   p.name_zh, p.name_en, p.name_ja,
                   p.type1, p.type2,
                   t1.name_zh AS type1_zh, t1.color AS type1_color,
                   t2.name_zh AS type2_zh, t2.color AS type2_color,
                   COALESCE(a1.name_zh, p.ability1_name) AS ability1_name,
                   COALESCE(a2.name_zh, p.ability2_name) AS ability2_name,
                   COALESCE(ah.name_zh, p.hidden_ability_name) AS hidden_ability_name,
                   p.hp, p.attack, p.defense, p.sp_attack, p.sp_defense, p.speed
            FROM pokemons p
            LEFT JOIN abilities a1 ON p.ability1_name = a1.name_en
            LEFT JOIN abilities a2 ON p.ability2_name = a2.name_en
            LEFT JOIN abilities ah ON p.hidden_ability_name = ah.name_en
            LEFT JOIN types t1 ON LOWER(t1.name_en) = p.type1
            LEFT JOIN types t2 ON LOWER(t2.name_en) = p.type2
            WHERE p.pokedex_id = ?
        """, (pokedex_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="未找到该宝可梦")
        d = dict(row)
        name_en = (d.get("name_en") or "").lower()
        if d.get("is_default_form"):
            img_id = f"{d.get('pokedex_id', 0):03d}"
        else:
            img_id = str(d.get("pokeapi_id", 0))
        d["image_official_artwork"] = f"pokemonImage/{img_id}-{name_en}-officialArtwork.png"
        return d
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moves/search")
async def search_moves(keyword: str, pokedex_id: int = 0, limit: int = 20):
    """搜索招式（可按宝可梦图鉴编号过滤可学招式）"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        prefix = f"{keyword}%"
        contain = f"%{keyword}%"
        order_cols = """CASE WHEN {t}name_zh LIKE ? THEN 0
                             WHEN {t}name_pinyin LIKE ? THEN 1
                             WHEN {t}name_pinyin_abbr LIKE ? THEN 2
                             ELSE 3 END, {t}name_zh"""
        if pokedex_id > 0:
            order = order_cols.format(t="m.")
            cur.execute(f"""
                SELECT DISTINCT m.id, m.name_zh, m.name_en, m.name_ja,
                       m.type, m.damage_class, m.power, m.accuracy
                FROM moves m
                JOIN pokemon_moves pm ON m.id = pm.move_id
                WHERE pm.pokedex_id = ?
                  AND (m.name_zh LIKE ? OR m.name_en LIKE ? OR m.name_ja LIKE ?
                       OR m.name_pinyin LIKE ? OR m.name_pinyin_abbr LIKE ?)
                ORDER BY {order}
                LIMIT ?
            """, (pokedex_id, contain, contain, contain, contain, contain, prefix, prefix, prefix, limit))
        else:
            order = order_cols.format(t="")
            cur.execute(f"""
                SELECT id, name_zh, name_en, name_ja,
                       type, damage_class, power, accuracy
                FROM moves
                WHERE name_zh LIKE ? OR name_en LIKE ? OR name_ja LIKE ?
                   OR name_pinyin LIKE ? OR name_pinyin_abbr LIKE ?
                ORDER BY {order}
                LIMIT ?
            """, (contain, contain, contain, contain, contain, prefix, prefix, prefix, limit))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items/search")
async def search_items(keyword: str, limit: int = 20):
    """搜索道具（中英日名称模糊匹配）"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        alias_names = _resolve_aliases(cur, keyword, 'item_alias')
        alias_clause = ""
        contain = f"%{keyword}%"
        prefix = f"{keyword}%"
        params = [contain] * 5
        if alias_names:
            placeholders = ','.join(['?'] * len(alias_names))
            alias_clause = f" OR name_en IN ({placeholders})"
            params.extend(alias_names)
        params.extend([prefix, prefix, prefix, limit])
        cur.execute(f"""
            SELECT id, name_zh, name_en, name_ja, category, image_path
            FROM items
            WHERE (name_zh LIKE ? OR name_en LIKE ? OR name_ja LIKE ?
                   OR name_pinyin LIKE ? OR name_pinyin_abbr LIKE ?
                   {alias_clause})
              AND name_zh != ''
            ORDER BY CASE WHEN name_zh LIKE ? THEN 0
                          WHEN name_pinyin LIKE ? THEN 1
                          WHEN name_pinyin_abbr LIKE ? THEN 2
                          ELSE 3 END, name_zh
            LIMIT ?
        """, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_name(name: str) -> str:
    """标准化名称：小写，去掉单引号、连字符、空格"""
    if not name:
        return ""
    return name.lower().replace("'", "").replace("-", "").replace(" ", "")


@router.get("/translate")
async def translate_names(names: str, table: str):
    """
    批量翻译英文名→中文名（大小写不敏感，同时查 name_en 和 name_ncp，忽略特殊字符）
    table: moves / abilities / items
    names: 逗号分隔的英文名
    """
    if table not in ("moves", "abilities", "items"):
        raise HTTPException(400, "table must be moves/abilities/items")
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        return {"translations": {}}
    try:
        conn = sqlite3.connect(_DB_PATH)
        cur = conn.cursor()
        # 查所有记录，用 Python 做模糊匹配
        try:
            cur.execute(f"SELECT name_en, name_ncp, name_zh FROM {table}")
        except:
            cur.execute(f"SELECT name_en, name_en, name_zh FROM {table}")
        # 建立标准化→(name_en, name_ncp, name_zh) 的映射
        db_rows = cur.fetchall()
        norm_map = {}
        for row in db_rows:
            name_en = row[0] or ""
            name_ncp = row[1] if len(row) > 1 else None
            name_zh = row[2] if len(row) > 2 else row[1]
            if name_zh:
                norm_en = _normalize_name(name_en)
                if norm_en:
                    norm_map[norm_en] = (name_en, name_ncp, name_zh)
                if name_ncp:
                    norm_ncp = _normalize_name(name_ncp)
                    if norm_ncp:
                        norm_map[norm_ncp] = (name_en, name_ncp, name_zh)
        # 匹配
        translations = {}
        for orig in name_list:
            norm = _normalize_name(orig)
            if norm in norm_map:
                translations[orig] = norm_map[norm][2]  # name_zh
        conn.close()
        return {"translations": translations}
    except Exception as e:
        raise HTTPException(500, str(e))

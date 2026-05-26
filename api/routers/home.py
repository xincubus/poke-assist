"""
HOME 路由：使用率排名、宝可梦详情
"""
import os
import sqlite3

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["HOME"])

# 服务引用（由 init_services 设置）
_DB_PATH = None
_PROJECT_ROOT = None


def init_services(db_path: str, project_root: str):
    """注入数据库路径和项目根目录"""
    global _DB_PATH, _PROJECT_ROOT
    _DB_PATH = db_path
    _PROJECT_ROOT = project_root


@router.get("/home/usage")
async def get_home_usage(source: str = "champions", season: int = 0, rule: int = 0):
    """
    获取宝可梦使用率排名数据

    Args:
        source: 数据源，"champions" 或 "sv"
        season: 赛季号，0 表示最新赛季
        rule: 0=单打, 1=双打
    """
    try:
        if source == "sv":
            db_path = os.path.join(_PROJECT_ROOT, "home", "sv", "pokemon_usage.db")
            img_base = "https://s3-ap-northeast-1.amazonaws.com/pokedb.tokyo/sv/assets/pokemon/thumbs_128"
            img_ext = "png"
        else:
            db_path = os.path.join(_PROJECT_ROOT, "home", "champions", "champions_usage.db")
            img_base = "https://s3-ap-northeast-1.amazonaws.com/pokedb.tokyo/champs/assets/pokemon/icons_128"
            img_ext = "webp"

        if not os.path.exists(db_path):
            raise HTTPException(status_code=404, detail=f"数据源 {source} 不存在")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 获取可用赛季列表
        cur.execute("SELECT DISTINCT season FROM pokemon_rankings ORDER BY season DESC")
        seasons = [r["season"] for r in cur.fetchall()]

        if not seasons:
            conn.close()
            return {"seasons": [], "rankings": [], "source": source, "rule": rule}

        # 确定赛季
        target_season = season if season > 0 else seasons[0]

        # 获取排名数据
        cur.execute("""
            SELECT rank, pokemon_id, pokemon_name
            FROM pokemon_rankings
            WHERE season = ? AND rule = ?
            ORDER BY rank
        """, (target_season, rule))

        ranking_rows = cur.fetchall()
        conn.close()

        # 从主数据库批量查询中文名 + 图片路径
        pokemon_ids = [r["pokemon_id"] for r in ranking_rows]
        ja_names = [r["pokemon_name"] for r in ranking_rows]
        id_to_zh = {}
        id_to_img = {}
        ja_to_zh = {}
        ja_to_img = {}
        try:
            main_conn = sqlite3.connect(_DB_PATH)
            main_conn.row_factory = sqlite3.Row
            main_cur = main_conn.cursor()
            # 优先：用 home_id 精确匹配
            placeholders = ",".join(["?"] * len(pokemon_ids))
            main_cur.execute(f"""
                SELECT home_id, name_zh, image_path
                FROM pokemons WHERE home_id IN ({placeholders})
            """, pokemon_ids)
            for row in main_cur.fetchall():
                if row["home_id"]:
                    id_to_zh[row["home_id"]] = row["name_zh"]
                    if row["image_path"]:
                        id_to_img[row["home_id"]] = f"/static/{row['image_path']}"
            # fallback：用 name_home 匹配未命中的
            matched_ids = set(id_to_zh.keys())
            unmatched_entries = [(r["pokemon_id"], r["pokemon_name"]) for r in ranking_rows if r["pokemon_id"] not in matched_ids]
            if unmatched_entries:
                unmatched_names = [e[1] for e in unmatched_entries]
                ph2 = ",".join(["?"] * len(unmatched_names))
                main_cur.execute(f"""
                    SELECT name_home, name_zh, image_path
                    FROM pokemons WHERE name_home IN ({ph2})
                """, unmatched_names)
                for row in main_cur.fetchall():
                    ja_to_zh[row["name_home"]] = row["name_zh"]
                    if row["image_path"]:
                        ja_to_img[row["name_home"]] = f"/static/{row['image_path']}"
            main_conn.close()
        except Exception:
            pass

        rankings = []
        for r in ranking_rows:
            pokemon_id = r["pokemon_id"]
            ja_name = r["pokemon_name"]
            zh_name = id_to_zh.get(pokemon_id, ja_to_zh.get(ja_name, ja_name))
            img_url = id_to_img.get(pokemon_id, ja_to_img.get(ja_name, f"{img_base}/pokemon-{pokemon_id}.{img_ext}"))
            rankings.append({
                "rank": r["rank"],
                "pokemon_id": pokemon_id,
                "pokemon_name": zh_name,
                "image_url": img_url,
            })

        return {
            "seasons": seasons,
            "current_season": target_season,
            "rankings": rankings,
            "source": source,
            "rule": rule,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/home/pokemon-detail")
async def get_pokemon_detail(
    pokemon_id: str,
    source: str = "champions",
    season: int = 0,
    rule: int = 0,
):
    """
    获取单个宝可梦的详细使用率数据（种族值、特性、道具、招式、性格、太晶属性）

    Args:
        pokemon_id: 格式 "0445-00"，来自 pokemon_rankings 表
        source: "champions" 或 "sv"
        season: 赛季号，0=最新
        rule: 0=单打, 1=双打
    """
    try:
        # 1. 从使用率 DB 获取该宝可梦的名称（日文）
        if source == "sv":
            usage_db = os.path.join(_PROJECT_ROOT, "home", "sv", "pokemon_usage.db")
        else:
            usage_db = os.path.join(_PROJECT_ROOT, "home", "champions", "champions_usage.db")

        if not os.path.exists(usage_db):
            raise HTTPException(status_code=404, detail=f"数据源 {source} 不存在")

        usage_conn = sqlite3.connect(usage_db)
        usage_conn.row_factory = sqlite3.Row
        usage_cur = usage_conn.cursor()

        # 获取可用赛季
        usage_cur.execute("SELECT DISTINCT season FROM pokemon_rankings ORDER BY season DESC")
        seasons = [r["season"] for r in usage_cur.fetchall()]
        target_season = season if season > 0 else (seasons[0] if seasons else 1)

        # 获取该宝可梦的日文名和排名
        usage_cur.execute(
            "SELECT rank, pokemon_name FROM pokemon_rankings WHERE pokemon_id=? AND season=? AND rule=?",
            (pokemon_id, target_season, rule),
        )
        rank_row = usage_cur.fetchone()
        ja_name = rank_row["pokemon_name"] if rank_row else None
        rank = rank_row["rank"] if rank_row else None

        # 2. 从主数据库查询宝可梦信息
        pokedex_id = int(pokemon_id.split("-")[0])

        main_conn = sqlite3.connect(_DB_PATH)
        main_conn.row_factory = sqlite3.Row
        main_cur = main_conn.cursor()

        # 查找当前形态
        pokemon_row = None
        if ja_name:
            main_cur.execute("SELECT * FROM pokemons WHERE home_id=?", (pokemon_id,))
            pokemon_row = main_cur.fetchone()

        # fallback：用 name_home 匹配
        if not pokemon_row and ja_name:
            main_cur.execute(
                "SELECT * FROM pokemons WHERE name_home=? AND pokedex_id=?",
                (ja_name, pokedex_id),
            )
            pokemon_row = main_cur.fetchone()

        # 再 fallback：默认形态
        if not pokemon_row:
            main_cur.execute(
                "SELECT * FROM pokemons WHERE pokedex_id=? AND is_default_form=1",
                (pokedex_id,),
            )
            pokemon_row = main_cur.fetchone()

        if not pokemon_row:
            usage_conn.close()
            main_conn.close()
            raise HTTPException(status_code=404, detail=f"宝可梦 {pokemon_id} 未找到")

        # 3. 获取同 dex id 的所有形态（用于形态切换）
        main_cur.execute(
            "SELECT pokedex_id, home_id, name_zh, name_en, name_home, image_path, "
            "hp, attack, defense, sp_attack, sp_defense, speed, total_stats, "
            "type1, type2, ability1_name, ability2_name, hidden_ability_name, "
            "is_default_form, pokeapi_id FROM pokemons WHERE pokedex_id=?",
            (pokedex_id,),
        )
        all_forms = main_cur.fetchall()

        # 查询哪些形态有独立技能池
        moves_table = "pokemon_moves_champions" if source == "champions" else "pokemon_moves_sv"
        pokeapi_ids = [f["pokeapi_id"] for f in all_forms]
        forms_with_moves = set()
        if pokeapi_ids:
            ph = ",".join(["?"] * len(pokeapi_ids))
            main_cur.execute(
                f"SELECT DISTINCT pokeapi_id FROM {moves_table} WHERE pokeapi_id IN ({ph})",
                pokeapi_ids,
            )
            for row in main_cur.fetchall():
                forms_with_moves.add(row[0])

        # 收集所有形态的特性名，批量查中文
        ability_names = set()
        for f in all_forms:
            for k in ("ability1_name", "ability2_name", "hidden_ability_name"):
                if f[k]:
                    ability_names.add(f[k])
        ability_zh = {}
        if ability_names:
            ph = ",".join(["?"] * len(ability_names))
            main_cur.execute(
                f"SELECT LOWER(name_en), name_zh FROM abilities WHERE LOWER(name_en) IN ({ph})",
                list(ability_names),
            )
            for row in main_cur.fetchall():
                ability_zh[row[0]] = row[1]

        # 属性颜色+中文映射
        main_cur.execute("SELECT LOWER(name_en), name_zh, color FROM types")
        type_info = {}
        for row in main_cur.fetchall():
            zh = row[1].replace("属性", "") if row[1] else row[1]
            type_info[row[0]] = {"zh": zh, "color": row[2]}

        forms = []
        for f in all_forms:
            t1 = f["type1"].lower() if f["type1"] else ""
            t2 = f["type2"].lower() if f["type2"] else ""
            ti1 = type_info.get(t1, {})
            ti2 = type_info.get(t2, {}) if t2 else {}
            forms.append({
                "home_id": f["home_id"],
                "name_zh": f["name_zh"],
                "name_en": f["name_en"],
                "name_home": f["name_home"],
                "image_url": f"/static/{f['image_path']}" if f["image_path"] else None,
                "has_moves": f["pokeapi_id"] in forms_with_moves,
                "hp": f["hp"],
                "attack": f["attack"],
                "defense": f["defense"],
                "sp_attack": f["sp_attack"],
                "sp_defense": f["sp_defense"],
                "speed": f["speed"],
                "total_stats": f["total_stats"],
                "type1": ti1.get("zh", f["type1"]),
                "type1_color": ti1.get("color", "#888"),
                "type2": ti2.get("zh", f["type2"]) if f["type2"] else None,
                "type2_color": ti2.get("color", "#888") if f["type2"] else None,
                "ability1": ability_zh.get(f["ability1_name"].lower(), f["ability1_name"]) if f["ability1_name"] else None,
                "ability2": ability_zh.get(f["ability2_name"].lower(), f["ability2_name"]) if f["ability2_name"] else None,
                "hidden_ability": ability_zh.get(f["hidden_ability_name"].lower(), f["hidden_ability_name"]) if f["hidden_ability_name"] else None,
                "is_default": bool(f["is_default_form"]),
            })

        # 4. 从使用率 DB 获取各项数据
        data_types = ("abilities", "items", "moves", "personalities") if source == "champions" else ("abilities", "items", "moves", "personalities", "tera_types")
        usage_data = {}
        for dtype in data_types:
            usage_cur.execute(
                "SELECT name, usage_rate FROM pokemon_usage "
                "WHERE pokemon_id=? AND season=? AND rule=? AND data_type=? "
                "ORDER BY usage_rate DESC",
                (pokemon_id, target_season, rule, dtype),
            )
            usage_data[dtype] = [
                {"name": r["name"], "rate": r["usage_rate"]}
                for r in usage_cur.fetchall()
            ]

        # 日文名→中文名映射
        def _build_ja_map(table, ja_col="name_ja", zh_col="name_zh", en_col="name_en"):
            all_ja = set()
            for dtype in usage_data:
                for item in usage_data[dtype]:
                    all_ja.add(item["name"])
            if not all_ja:
                return {}, {}
            placeholders = ",".join(["?"] * len(all_ja))
            ja_to_zh, ja_to_en = {}, {}
            try:
                main_cur.execute(
                    f"SELECT name_home, {zh_col}, {en_col} FROM {table} WHERE name_home IN ({placeholders})",
                    list(all_ja),
                )
                for row in main_cur.fetchall():
                    if row["name_home"]:
                        ja_to_zh[row["name_home"]] = row[zh_col]
                        ja_to_en[row["name_home"]] = row[en_col]
            except Exception:
                pass
            unmatched = [n for n in all_ja if n not in ja_to_zh]
            if unmatched:
                ph2 = ",".join(["?"] * len(unmatched))
                try:
                    main_cur.execute(
                        f"SELECT {ja_col}, {zh_col}, {en_col} FROM {table} WHERE {ja_col} IN ({ph2})",
                        unmatched,
                    )
                    for row in main_cur.fetchall():
                        ja_to_zh[row[ja_col]] = row[zh_col]
                        ja_to_en[row[ja_col]] = row[en_col]
                except Exception:
                    pass
            return ja_to_zh, ja_to_en

        # 招式映射
        moves_zh, moves_en = _build_ja_map("moves")
        for m in usage_data["moves"]:
            m["name_zh"] = moves_zh.get(m["name"], m["name"])
            m["name_en"] = moves_en.get(m["name"], "")

        # 特性映射
        ab_zh, _ = _build_ja_map("abilities")
        for m in usage_data["abilities"]:
            m["name_zh"] = ab_zh.get(m["name"], m["name"])

        # 道具映射
        item_zh, _ = _build_ja_map("items")
        for m in usage_data["items"]:
            m["name_zh"] = item_zh.get(m["name"], m["name"])

        # 性格映射
        nature_zh, _ = _build_ja_map("natures")
        for m in usage_data["personalities"]:
            m["name_zh"] = nature_zh.get(m["name"], m["name"])

        # 太晶属性映射
        if "tera_types" in usage_data:
            type_zh, _ = _build_ja_map("types")
            for m in usage_data["tera_types"]:
                zh = type_zh.get(m["name"], m["name"])
                m["name_zh"] = zh.replace("属性", "") if zh else zh

        # 5. 从主数据库获取该宝可梦可学招式
        moves_table = "pokemon_moves_champions" if source == "champions" else "pokemon_moves_sv"
        default_en = pokemon_row["name_en"]
        main_cur.execute(
            f"SELECT DISTINCT pm.move_name_zh, pm.move_name_en, pm.learn_method, "
            f"m.type, m.damage_class, m.power, m.accuracy "
            f"FROM {moves_table} pm "
            f"LEFT JOIN moves m ON pm.move_id = m.id "
            f"WHERE LOWER(pm.pokemon_name_en)=LOWER(?) "
            f"ORDER BY pm.move_name_zh",
            (default_en,),
        )
        all_moves = main_cur.fetchall()

        class_zh_map = {"physical": "物理", "special": "特殊", "status": "变化"}

        moves_list = []
        if all_moves:
            for m in all_moves:
                t = m["type"].lower() if m["type"] else ""
                ti = type_info.get(t, {})
                moves_list.append({
                    "name_zh": m["move_name_zh"],
                    "name_en": m["move_name_en"],
                    "learn_method": m["learn_method"],
                    "type": ti.get("zh", m["type"]),
                    "type_color": ti.get("color", "#888"),
                    "damage_class": class_zh_map.get(m["damage_class"], m["damage_class"]) if m["damage_class"] else None,
                    "power": m["power"],
                    "accuracy": m["accuracy"],
                })

        usage_conn.close()
        main_conn.close()

        return {
            "pokemon_id": pokemon_id,
            "rank": rank,
            "current_form": {
                "name_zh": pokemon_row["name_zh"],
                "name_en": pokemon_row["name_en"],
            },
            "forms": forms,
            "usage": usage_data,
            "moves": moves_list,
            "seasons": seasons,
            "current_season": target_season,
            "source": source,
            "rule": rule,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

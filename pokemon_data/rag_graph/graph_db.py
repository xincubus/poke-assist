"""图数据库核心模块 - SQLite 存储 + CRUD 操作"""
import json
import os
import sqlite3
from datetime import datetime, timezone

# 图数据库路径（独立于 pokemonData.db）
DB_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPH_DB_PATH = os.path.join(DB_DIR, "graph.db")


class GraphDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or GRAPH_DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        # 节点表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id     TEXT PRIMARY KEY,
                node_type   TEXT NOT NULL,
                name_zh     TEXT,
                name_en     TEXT,
                name_ja     TEXT,
                properties  TEXT,
                source      TEXT DEFAULT 'structured',
                source_page TEXT,
                embedding   BLOB,
                created_at  TEXT,
                updated_at  TEXT
            )
        """)
        # 边表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id      TEXT NOT NULL,
                target_id      TEXT NOT NULL,
                edge_type      TEXT NOT NULL,
                weight         REAL DEFAULT 1.0,
                properties     TEXT,
                source         TEXT DEFAULT 'structured',
                created_at     TEXT,
                evidence_count INTEGER DEFAULT 1,
                contexts       TEXT,
                UNIQUE(source_id, target_id, edge_type)
            )
        """)
        # 兼容已存在的旧表：补齐 Step 5 新增的两列
        existing_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(graph_edges)")}
        if 'evidence_count' not in existing_cols:
            self.conn.execute("ALTER TABLE graph_edges ADD COLUMN evidence_count INTEGER DEFAULT 1")
        if 'contexts' not in existing_cols:
            self.conn.execute("ALTER TABLE graph_edges ADD COLUMN contexts TEXT")
        # 别名表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_entity_aliases (
                alias       TEXT NOT NULL,
                node_id     TEXT NOT NULL,
                alias_type  TEXT DEFAULT 'exact',
                confidence  REAL DEFAULT 1.0,
                PRIMARY KEY (alias, node_id)
            )
        """)
        # 抽取日志表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_extraction_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id       INTEGER,
                section_id    INTEGER,
                status        TEXT DEFAULT 'pending',
                model         TEXT,
                input_tokens  INTEGER,
                output_tokens INTEGER,
                error_msg     TEXT,
                created_at    TEXT
            )
        """)
        # 索引
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_gn_type ON graph_nodes(node_type)",
            "CREATE INDEX IF NOT EXISTS idx_gn_zh ON graph_nodes(name_zh)",
            "CREATE INDEX IF NOT EXISTS idx_gn_en ON graph_nodes(name_en)",
            "CREATE INDEX IF NOT EXISTS idx_ge_src ON graph_edges(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_ge_tgt ON graph_edges(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_ge_type ON graph_edges(edge_type)",
            "CREATE INDEX IF NOT EXISTS idx_gea_node ON graph_entity_aliases(node_id)",
        ]:
            self.conn.execute(idx_sql)
        self.conn.commit()

    def add_node(self, node_id, node_type, name_zh=None, name_en=None,
                 name_ja=None, properties=None, source='structured',
                 source_page=None):
        """插入或忽略节点"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        props_json = json.dumps(properties, ensure_ascii=False) if properties else None
        self.conn.execute("""
            INSERT OR IGNORE INTO graph_nodes
            (node_id, node_type, name_zh, name_en, name_ja, properties,
             source, source_page, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (node_id, node_type, name_zh, name_en, name_ja, props_json,
              source, source_page, now, now))

    def add_edge(self, source_id, target_id, edge_type, weight=1.0,
                 properties=None, source='structured'):
        """插入或忽略边（去重：source_id+target_id+edge_type）"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        props_json = json.dumps(properties, ensure_ascii=False) if properties else None
        self.conn.execute("""
            INSERT OR IGNORE INTO graph_edges
            (source_id, target_id, edge_type, weight, properties, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source_id, target_id, edge_type, weight, props_json, source, now))

    def upsert_edge(self, source_id, target_id, edge_type, context=None,
                    weight=1.0, properties=None, source='llm_extracted',
                    max_contexts=3):
        """UPSERT 边：存在则 evidence_count+1、累加前 max_contexts 条 context；
        不存在则插入。用于 Step 5 LLM 抽取结果去重。
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        props_json = json.dumps(properties, ensure_ascii=False) if properties else None
        ctx = (context or '').replace('|', '／').strip()
        self.conn.execute("""
            INSERT INTO graph_edges
            (source_id, target_id, edge_type, weight, properties, source,
             created_at, evidence_count, contexts)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(source_id, target_id, edge_type)
            DO UPDATE SET
                evidence_count = evidence_count + 1,
                contexts = CASE
                    WHEN evidence_count < ?
                      THEN COALESCE(contexts || '|', '') || excluded.contexts
                    ELSE contexts
                END
        """, (source_id, target_id, edge_type, weight, props_json, source,
              now, ctx, max_contexts))

    def add_alias(self, alias, node_id, alias_type='exact', confidence=1.0):
        """插入或忽略别名"""
        self.conn.execute("""
            INSERT OR IGNORE INTO graph_entity_aliases
            (alias, node_id, alias_type, confidence)
            VALUES (?, ?, ?, ?)
        """, (alias, node_id, alias_type, confidence))

    def get_node(self, node_id):
        """获取单个节点"""
        row = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE node_id=?", (node_id,)
        ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM graph_nodes LIMIT 0").description]
        return dict(zip(cols, row))

    def get_neighbors(self, node_id, edge_types=None, direction='both',
                      limit=100):
        """获取邻居节点（支持方向和边类型过滤）"""
        results = []
        if direction in ('out', 'both'):
            sql = """
                SELECT e.edge_type, e.weight, e.properties,
                       n.node_id, n.node_type, n.name_zh, n.name_en, n.properties
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.target_id
                WHERE e.source_id = ?
            """
            params = [node_id]
            if edge_types:
                placeholders = ','.join('?' * len(edge_types))
                sql += f" AND e.edge_type IN ({placeholders})"
                params.extend(edge_types)
            sql += f" LIMIT {limit}"
            for row in self.conn.execute(sql, params).fetchall():
                results.append({
                    'edge_type': row[0], 'weight': row[1],
                    'edge_props': json.loads(row[2]) if row[2] else {},
                    'node_id': row[3], 'node_type': row[4],
                    'name_zh': row[5], 'name_en': row[6],
                    'node_props': json.loads(row[7]) if row[7] else {},
                    'direction': 'out'
                })
        if direction in ('in', 'both'):
            sql = """
                SELECT e.edge_type, e.weight, e.properties,
                       n.node_id, n.node_type, n.name_zh, n.name_en, n.properties
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.source_id
                WHERE e.target_id = ?
            """
            params = [node_id]
            if edge_types:
                placeholders = ','.join('?' * len(edge_types))
                sql += f" AND e.edge_type IN ({placeholders})"
                params.extend(edge_types)
            sql += f" LIMIT {limit}"
            for row in self.conn.execute(sql, params).fetchall():
                results.append({
                    'edge_type': row[0], 'weight': row[1],
                    'edge_props': json.loads(row[2]) if row[2] else {},
                    'node_id': row[3], 'node_type': row[4],
                    'name_zh': row[5], 'name_en': row[6],
                    'node_props': json.loads(row[7]) if row[7] else {},
                    'direction': 'in'
                })
        return results

    def find_nodes_by_alias(self, alias, limit=10):
        """通过别名查找节点"""
        rows = self.conn.execute("""
            SELECT n.* FROM graph_entity_aliases a
            JOIN graph_nodes n ON n.node_id = a.node_id
            WHERE a.alias = ?
            ORDER BY a.confidence DESC
            LIMIT ?
        """, (alias, limit)).fetchall()
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM graph_nodes LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    def find_nodes_by_name(self, name, limit=10):
        """通过名称模糊查找节点"""
        rows = self.conn.execute("""
            SELECT * FROM graph_nodes
            WHERE name_zh LIKE ? OR name_en LIKE ? OR name_zh = ? OR name_en = ?
            LIMIT ?
        """, (f"%{name}%", f"%{name}%", name, name, limit)).fetchall()
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM graph_nodes LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

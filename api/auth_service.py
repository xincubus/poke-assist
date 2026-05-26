"""
用户认证服务
提供注册、登录、JWT Token 生成与验证
"""
import os
import sqlite3
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError


# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "pokemon-assistant-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 天


def _hash_password(password: str) -> str:
    """密码哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class AuthService:
    def __init__(self, db_path: str):
        # 用户数据独立存储，避免 Pokemon 数据导入时丢失用户记录
        db_dir = os.path.dirname(db_path)
        self.db_path = os.path.join(db_dir, "users.db")
        self._init_users_table()
        # 从旧数据库迁移已有用户（一次性）
        self._migrate_from_old_db(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_users_table(self):
        """创建 users 表（如果不存在）"""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _migrate_from_old_db(self, old_db_path: str):
        """从旧的 pokemonData.db 迁移用户数据（一次性）"""
        if not os.path.exists(old_db_path):
            return
        try:
            old_conn = sqlite3.connect(old_db_path)
            old_conn.row_factory = sqlite3.Row
            # 检查旧库是否有 users 表
            table = old_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            if not table:
                old_conn.close()
                return
            old_users = old_conn.execute(
                "SELECT username, password_hash, created_at FROM users"
            ).fetchall()
            old_conn.close()
            if not old_users:
                return
            # 插入到新库，跳过已存在的
            new_conn = self._get_conn()
            migrated = 0
            for u in old_users:
                try:
                    new_conn.execute(
                        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                        (u["username"], u["password_hash"], u["created_at"])
                    )
                    migrated += 1
                except sqlite3.IntegrityError:
                    pass  # 已存在，跳过
            new_conn.commit()
            new_conn.close()
            if migrated > 0:
                print(f"已从 pokemonData.db 迁移 {migrated} 个用户到 users.db")
        except Exception as e:
            print(f"用户迁移跳过: {e}")

    def register(self, username: str, password: str) -> dict:
        """
        注册新用户
        返回 {"success": True} 或抛出异常
        """
        if not username or not username.strip():
            raise ValueError("用户名不能为空")
        if not password or len(password) < 6:
            raise ValueError("密码长度至少为 6 位")

        username = username.strip()
        password_hash = _hash_password(password)

        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
            conn.commit()
            return {"success": True}
        except sqlite3.IntegrityError:
            raise ValueError("用户名已存在")
        finally:
            conn.close()

    def login(self, username: str, password: str) -> dict:
        """
        用户登录
        返回 {"token": "...", "username": "..."} 或抛出异常
        """
        if not username or not password:
            raise ValueError("用户名和密码不能为空")

        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username.strip(),)
            ).fetchone()

            if not row:
                raise ValueError("用户名或密码错误")

            if not _verify_password(password, row["password_hash"]):
                raise ValueError("用户名或密码错误")

            # 生成 JWT Token
            token = self._create_token(user_id=row["id"], username=row["username"])
            return {
                "token": token,
                "username": row["username"]
            }
        finally:
            conn.close()

    def _create_token(self, user_id: int, username: str) -> str:
        """生成 JWT Token"""
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        payload = {
            "sub": str(user_id),
            "username": username,
            "exp": expire
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> dict:
        """
        验证 JWT Token
        返回 {"user_id": ..., "username": ...} 或抛出异常
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return {
                "user_id": int(payload["sub"]),
                "username": payload["username"]
            }
        except JWTError:
            raise ValueError("无效的 Token")

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

try:
    import aiosqlite
    AIOSQLITE_OK = True
except ImportError:
    AIOSQLITE_OK = False

logger = logging.getLogger("discord")

DB_PATH = os.environ.get("DB_PATH", "aegisbot.db")

class Database:

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._db: Optional["aiosqlite.Connection"] = None

    async def init(self) -> None:
        if not self._db:
            return 0
        await self._db.execute(
            "INSERT INTO warnings (user_id, guild_id, reason, moderator) VALUES (?, ?, ?, ?)",
            (str(user_id), str(guild_id), reason, moderator)
        )
        await self._db.commit()
        return await self.count_warnings(user_id, guild_id)

    async def get_warnings(self, user_id: int, guild_id: int) -> list[dict]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY created_at DESC",
            (str(user_id), str(guild_id))
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def count_warnings(self, user_id: int, guild_id: int) -> int:
        if not self._db:
            return 0
        async with self._db.execute(
            "SELECT COUNT(*) as n FROM warnings WHERE user_id = ? AND guild_id = ?",
            (str(user_id), str(guild_id))
        ) as cur:
            row = await cur.fetchone()
            return row["n"] if row else 0

    async def delete_warning(self, warning_id: int, guild_id: int) -> bool:
        if not self._db:
            return False
        async with self._db.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, str(guild_id))
        ) as cur:
            await self._db.commit()
            return cur.rowcount > 0

    async def reset_warnings(self, user_id: int, guild_id: int) -> int:
        if not self._db:
            return 0
        async with self._db.execute(
            "DELETE FROM warnings WHERE user_id = ? AND guild_id = ?",
            (str(user_id), str(guild_id))
        ) as cur:
            await self._db.commit()
            return cur.rowcount

    async def add_temp_action(self, guild_id: int, user_id: int,
                               action: str, expires_at: datetime,
                               reason: str = "", moderator: str = "") -> int:
        if not self._db:
            return -1
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        async with self._db.execute(
            """INSERT INTO temp_actions (guild_id, user_id, action, expires_at, reason, moderator)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(guild_id), str(user_id), action, expires_str, reason, moderator)
        ) as cur:
            await self._db.commit()
            return cur.lastrowid or -1

    async def get_pending_actions(self) -> list[dict]:
        if not self._db:
            return []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with self._db.execute(
            "SELECT * FROM temp_actions WHERE done = 0 AND expires_at <= ?", (now,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def mark_action_done(self, action_id: int) -> None:
        if not self._db:
            return
        await self._db.execute(
            "UPDATE temp_actions SET done = 1 WHERE id = ?", (action_id,)
        )
        await self._db.commit()

    async def migrate_from_json(self, server_config: dict, reportes: dict) -> None:
        if not self._db:
            return
        async with self._db.execute("SELECT COUNT(*) as n FROM guild_config") as cur:
            row = await cur.fetchone()
            if row and row["n"] > 0:
                return  # Ya migrado

        logger.info("Migrando datos JSON → SQLite...")
        for gid, cfg in server_config.items():
            if gid.startswith("__"):
                continue
            await self.set_config(int(gid), cfg)

        for uid, info in reportes.items():
            try:
                await self._db.execute(
                    """INSERT OR IGNORE INTO reports (user_id, reason, server, server_id)
                       VALUES (?, ?, ?, ?)""",
                    (uid, info.get("motivo", ""), info.get("servidor", ""), info.get("servidor_id", ""))
                )
            except Exception:
                pass
        await self._db.commit()
        logger.info(f"Migración completada: {len(server_config)} guilds, {len(reportes)} reportes")

# Instancia global — se inicializa en on_ready
db = Database()

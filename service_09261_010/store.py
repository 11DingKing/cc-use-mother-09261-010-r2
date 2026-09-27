"""SQLite 状态仓储。"""
import sqlite3


class SQLiteStore:
    """案例仓储：每次写入都在单条事务中完成，异常时整体回滚，不留半条记录。"""

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cases("
            "id TEXT PRIMARY KEY,"
            "actor TEXT NOT NULL,"
            "state TEXT NOT NULL,"
            "version INTEGER NOT NULL,"
            "idempotency_key TEXT UNIQUE)"
        )
        self.db.commit()

    def insert_case(self, rec):
        """原子写入新案例；任何异常都会回滚，库中不会出现半条记录。"""
        with self.db:
            self.db.execute(
                "INSERT INTO cases(id,actor,state,version,idempotency_key) VALUES(?,?,?,?,?)",
                (rec["id"], rec["actor"], rec["state"], rec["version"], rec.get("idempotency_key")),
            )

    def update_case(self, rec):
        """原子更新既有案例；目标不存在时抛错且不改写任何行。"""
        with self.db:
            cur = self.db.execute(
                "UPDATE cases SET actor=?,state=?,version=? WHERE id=?",
                (rec["actor"], rec["state"], rec["version"], rec["id"]),
            )
            if cur.rowcount != 1:
                raise KeyError(rec["id"])

    def load_cases(self):
        """按写入顺序读出全部案例，用于服务恢复后重建内存状态。"""
        rows = self.db.execute(
            "SELECT id,actor,state,version,idempotency_key FROM cases ORDER BY rowid"
        ).fetchall()
        return [
            {"id": r[0], "actor": r[1], "state": r[2], "version": r[3], "idempotency_key": r[4]}
            for r in rows
        ]

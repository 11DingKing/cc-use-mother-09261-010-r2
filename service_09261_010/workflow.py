"""版本化业务工作流。"""
import re
from dataclasses import dataclass, asdict


class ValidationError(ValueError):
    """提交材料未通过入口格式校验。"""


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_TEXT = 128


def _check_text(field, value, pattern=None):
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise ValidationError("invalid %s" % field)
    if pattern is not None and not pattern.match(value):
        raise ValidationError("invalid %s" % field)


def validate_submission(id, actor, key=None):
    """提交入口的格式校验：任何一项不合格都抛 ValidationError，不产生任何记录。"""
    _check_text("id", id, _ID_RE)
    _check_text("actor", actor)
    if key is not None:
        _check_text("idempotency_key", key)


@dataclass(frozen=True)
class Case:
    id: str
    actor: str
    state: str
    version: int = 1

    def move(self, state, actor):
        allowed = {"draft": {"reviewing", "cancelled"}, "reviewing": {"approved", "rejected"}, "rejected": {"draft"}, "approved": {"archived"}}
        if state not in allowed.get(self.state, set()):
            raise ValueError("invalid transition")
        return Case(self.id, actor, state, self.version + 1)


class Workflow:
    """先校验、再落库、后入内存：任何一步失败都不留半成品记录。"""

    def __init__(self, store=None):
        self.store = store
        self.rows = {}
        self.keys = {}
        if store is not None:
            for rec in store.load_cases():
                self.rows[rec["id"]] = Case(rec["id"], rec["actor"], rec["state"], rec["version"])
                if rec["idempotency_key"]:
                    self.keys[rec["idempotency_key"]] = rec["id"]

    def create(self, id, actor, key=None):
        validate_submission(id, actor, key)
        if key in self.keys:
            return self.rows[self.keys[key]]
        if id in self.rows:
            raise ValueError("duplicate")
        row = Case(id, actor, "draft")
        if self.store is not None:
            self.store.insert_case({**asdict(row), "idempotency_key": key})
        self.rows[id] = row
        if key:
            self.keys[key] = id
        return row

    def move(self, id, state, actor):
        _check_text("state", state)
        _check_text("actor", actor)
        if id not in self.rows:
            raise KeyError(id)
        row = self.rows[id].move(state, actor)
        if self.store is not None:
            self.store.update_case(asdict(row))
        self.rows[id] = row
        return row

    def snapshot(self):
        return [asdict(self.rows[k]) for k in sorted(self.rows)]

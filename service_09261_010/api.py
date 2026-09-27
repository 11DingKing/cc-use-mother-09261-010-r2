"""JSON API 适配器。"""
from dataclasses import asdict

from .workflow import ValidationError


def _err(status, msg):
    return status, {"error": msg}


def dispatch(flow, method, path, body=None):
    body = body or {}
    if not isinstance(body, dict):
        return _err(400, "invalid body")
    if method == "POST" and path == "/cases":
        try:
            row = flow.create(body.get("id"), body.get("actor"), body.get("idempotency_key"))
        except ValidationError as e:
            return _err(422, str(e))
        except ValueError:
            return _err(409, "duplicate")
        except Exception:
            return _err(500, "internal")
        return 201, asdict(row)
    if method == "POST" and path.endswith("/move"):
        parts = path.split("/")
        if len(parts) != 4 or parts[1] != "cases" or not parts[2]:
            return _err(404, "not_found")
        try:
            row = flow.move(parts[2], body.get("state"), body.get("actor"))
        except ValidationError as e:
            return _err(422, str(e))
        except KeyError:
            return _err(404, "not_found")
        except ValueError:
            return _err(409, "invalid transition")
        except Exception:
            return _err(500, "internal")
        return 200, asdict(row)
    if method == "GET" and path == "/cases":
        return 200, flow.snapshot()
    return _err(404, "not_found")

"""JSON API 适配器。"""
from dataclasses import asdict
from .workflow import ValidationError,DuplicateError,TransitionError,NotFoundError
def dispatch(flow,method,path,body=None):
 body=body if body is not None else {}
 if not isinstance(body,dict): return 400,{"error":"invalid_body"}
 try:
  if method=="POST" and path=="/cases": return 201,asdict(flow.create(body.get("id"),body.get("actor"),body.get("material"),body.get("idempotency_key")))
  if method=="POST" and path.endswith("/move"): return 200,asdict(flow.move(path.split("/")[2],body.get("state"),body.get("actor")))
  if method=="GET" and path=="/cases": return 200,flow.snapshot()
  return 404,{"error":"not_found"}
 except ValidationError as e: return 400,{"error":"validation","message":str(e)}
 except (DuplicateError,TransitionError) as e: return 409,{"error":"conflict","message":str(e)}
 except NotFoundError as e: return 404,{"error":"not_found","message":str(e)}
 except Exception as e: return 500,{"error":"internal","message":str(e)}

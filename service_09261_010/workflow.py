"""版本化业务工作流。"""
import copy,threading
from dataclasses import dataclass,field,asdict
class ValidationError(ValueError): pass
class DuplicateError(ValueError): pass
class TransitionError(ValueError): pass
class NotFoundError(LookupError): pass
def _require_text(value,name):
 if not isinstance(value,str) or not value.strip(): raise ValidationError("%s must be a non-empty string"%name)
 return value.strip()
def _validate_material(material):
 if not isinstance(material,dict) or not material: raise ValidationError("material must be a non-empty object")
 title=material.get("title")
 if not isinstance(title,str) or not title.strip(): raise ValidationError("material.title must be a non-empty string")
 isbn=material.get("isbn")
 if not isinstance(isbn,str): raise ValidationError("material.isbn must be a string")
 digits=isbn.replace("-","").replace(" ","")
 if len(digits)==10: ok=digits[:9].isdigit() and (digits[9].isdigit() or digits[9] in "Xx")
 elif len(digits)==13: ok=digits.isdigit()
 else: ok=False
 if not ok: raise ValidationError("material.isbn must be ISBN-10 or ISBN-13 digits")
 return copy.deepcopy(material)
@dataclass(frozen=True)
class Case:
 id:str; actor:str; state:str; material:dict=field(default_factory=dict); version:int=1
 def move(self,state,actor):
  allowed={"draft":{"reviewing","cancelled"},"reviewing":{"approved","rejected"},"rejected":{"draft"},"approved":{"archived"}}
  if state not in allowed.get(self.state,set()): raise TransitionError("invalid transition")
  return Case(self.id,actor,state,copy.deepcopy(self.material),self.version+1)
class Workflow:
 def __init__(self,store=None):
  self.store=store; self.rows={}; self.keys={}; self.lock=threading.RLock()
  if store is not None: self._restore()
 def _restore(self):
  data=self.store.latest()
  rows=data.get("rows",[]) if isinstance(data,dict) else data
  keys=data.get("keys",{}) if isinstance(data,dict) else {}
  for raw in rows or []:
   raw=dict(raw); raw.setdefault("material",{}); row=Case(**raw); self.rows[row.id]=row
  self.keys=dict(keys or {})
 def _persist(self):
  if self.store is not None: self.store.save({"rows":self.snapshot(),"keys":dict(self.keys)})
 def create(self,id,actor,material,key=None):
  id=_require_text(id,"id"); actor=_require_text(actor,"actor")
  if key is not None: key=_require_text(key,"idempotency_key")
  material=_validate_material(material)
  with self.lock:
   if key is not None and key in self.keys: return self.rows[self.keys[key]]
   if id in self.rows: raise DuplicateError("duplicate")
   row=Case(id,actor,"draft",material); self.rows[id]=row
   if key is not None: self.keys[key]=id
   try: self._persist()
   except Exception:
    del self.rows[id]
    if key is not None: del self.keys[key]
    raise
   return row
 def move(self,id,state,actor):
  state=_require_text(state,"state"); actor=_require_text(actor,"actor")
  with self.lock:
   if id not in self.rows: raise NotFoundError("not_found")
   old=self.rows[id]; row=old.move(state,actor); self.rows[id]=row
   try: self._persist()
   except Exception:
    self.rows[id]=old; raise
   return row
 def snapshot(self):
  with self.lock: return [asdict(self.rows[k]) for k in sorted(self.rows)]

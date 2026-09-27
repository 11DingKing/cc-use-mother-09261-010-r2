import os,tempfile,unittest
from service_09261_010.workflow import Workflow,ValidationError,DuplicateError,TransitionError,NotFoundError
from service_09261_010.store import SQLiteStore
from service_09261_010.api import dispatch
MATERIAL={"title":"高等数学","isbn":"978-7-04-000000-0"}
class FailingStore:
 def __init__(self): self.fail=True; self.saved=[]
 def save(self,value):
  if self.fail: raise IOError("disk full")
  self.saved.append(value)
 def latest(self): return self.saved[-1] if self.saved else []
class TestFlow(unittest.TestCase):
 def test_flow(self):
  f=Workflow(); self.assertEqual(f.create("c1","a",MATERIAL,"k").state,"draft"); self.assertEqual(f.create("c1","a",MATERIAL,"k").version,1); self.assertEqual(f.move("c1","reviewing","b").state,"reviewing")
 def test_material_validation(self):
  f=Workflow()
  for bad in (None,{},[],"x",{"title":"x"},{"isbn":"9787040000000"},{"title":" ","isbn":"9787040000000"},{"title":"x","isbn":"123"},{"title":"x","isbn":"abcdefghij"},{"title":"x","isbn":123}):
   with self.assertRaises(ValidationError): f.create("c1","a",bad)
  self.assertEqual(f.snapshot(),[]); self.assertEqual(f.keys,{})
 def test_identity_validation(self):
  f=Workflow()
  for id,actor in ((None,"a"),("","a"),("  ","a"),(1,"a"),("c1",None),("c1",""),("c1",2)):
   with self.assertRaises(ValidationError): f.create(id,actor,MATERIAL)
  with self.assertRaises(ValidationError): f.create("c1","a",MATERIAL,key=123)
  self.assertEqual(f.snapshot(),[])
 def test_failed_create_leaves_no_residue(self):
  f=Workflow()
  with self.assertRaises(ValidationError): f.create("c1","a",None,"k")
  self.assertEqual(f.create("c1","a",MATERIAL,"k").state,"draft"); self.assertEqual(len(f.snapshot()),1)
 def test_duplicate_rejected(self):
  f=Workflow(); f.create("c1","a",MATERIAL,"k1")
  with self.assertRaises(DuplicateError): f.create("c1","b",MATERIAL,"k2")
  self.assertEqual(len(f.snapshot()),1); self.assertNotIn("k2",f.keys)
 def test_replay_returns_original(self):
  f=Workflow(); f.create("c1","a",MATERIAL,"k"); r=f.create("c1","a",MATERIAL,"k")
  self.assertEqual((r.state,r.version),("draft",1)); self.assertEqual(len(f.snapshot()),1)
 def test_write_interruption_is_atomic(self):
  s=FailingStore(); f=Workflow(s)
  with self.assertRaises(IOError): f.create("c1","a",MATERIAL,"k")
  self.assertEqual(f.snapshot(),[]); self.assertEqual(f.keys,{})
  s.fail=False; f.create("c1","a",MATERIAL,"k"); self.assertEqual(len(f.snapshot()),1)
 def test_move_write_failure_keeps_state(self):
  s=FailingStore(); s.fail=False; f=Workflow(s); f.create("c1","a",MATERIAL,"k"); s.fail=True
  with self.assertRaises(IOError): f.move("c1","reviewing","b")
  self.assertEqual((f.rows["c1"].state,f.rows["c1"].version),("draft",1))
 def test_invalid_transition_leaves_no_trace(self):
  s=FailingStore(); s.fail=False; f=Workflow(s); f.create("c1","a",MATERIAL,"k"); n=len(s.saved)
  with self.assertRaises(TransitionError): f.move("c1","approved","b")
  self.assertEqual(f.rows["c1"].state,"draft"); self.assertEqual(len(s.saved),n)
 def test_move_unknown_case(self):
  with self.assertRaises(NotFoundError): Workflow().move("nope","reviewing","b")
 def test_recovery_restores_todos_and_keys(self):
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"s.db"); f1=Workflow(SQLiteStore(path))
   f1.create("c1","a",MATERIAL,"k1"); f1.create("c2","a",MATERIAL); f1.move("c1","reviewing","b")
   f2=Workflow(SQLiteStore(path)); self.assertEqual(f2.snapshot(),f1.snapshot())
   r=f2.create("c1","a",MATERIAL,"k1")
   self.assertEqual((r.state,r.version),("reviewing",2)); self.assertEqual(len(f2.snapshot()),2)
class TestAPI(unittest.TestCase):
 def setUp(self): self.f=Workflow()
 def test_create_and_list(self):
  s,b=dispatch(self.f,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL,"idempotency_key":"k"})
  self.assertEqual(s,201); self.assertEqual(b["state"],"draft"); self.assertEqual(b["material"],MATERIAL)
  s,b=dispatch(self.f,"GET","/cases"); self.assertEqual(s,200); self.assertEqual([r["id"] for r in b],["c1"])
 def test_validation_400(self):
  self.assertEqual(dispatch(self.f,"POST","/cases",{"id":"c1","actor":"a","material":{"title":"x","isbn":"bad"}})[0],400)
  self.assertEqual(dispatch(self.f,"POST","/cases",{"actor":"a","material":MATERIAL})[0],400)
  self.assertEqual(dispatch(self.f,"GET","/cases")[1],[])
 def test_bad_body_400(self):
  self.assertEqual(dispatch(self.f,"POST","/cases",["not","a","dict"])[0],400)
 def test_move_flow(self):
  dispatch(self.f,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL})
  s,b=dispatch(self.f,"POST","/cases/c1/move",{"state":"reviewing","actor":"b"})
  self.assertEqual((s,b["state"],b["version"]),(200,"reviewing",2))
  self.assertEqual(dispatch(self.f,"POST","/cases/c1/move",{"state":"draft","actor":"b"})[0],409)
  self.assertEqual(dispatch(self.f,"POST","/cases/c1/move",{"actor":"b"})[0],400)
 def test_move_not_found(self):
  self.assertEqual(dispatch(self.f,"POST","/cases/nope/move",{"state":"reviewing","actor":"b"})[0],404)
 def test_duplicate_409(self):
  dispatch(self.f,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL})
  self.assertEqual(dispatch(self.f,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL})[0],409)
 def test_unknown_route(self):
  self.assertEqual(dispatch(self.f,"GET","/nope")[0],404)
 def test_recovery_keeps_todos_matching(self):
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"s.db"); f1=Workflow(SQLiteStore(path))
   dispatch(f1,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL,"idempotency_key":"k1"})
   dispatch(f1,"POST","/cases",{"id":"c2","actor":"a","material":MATERIAL})
   f2=Workflow(SQLiteStore(path))
   self.assertEqual([r["id"] for r in dispatch(f2,"GET","/cases")[1]],["c1","c2"])
   self.assertEqual(dispatch(f2,"POST","/cases",{"id":"c1","actor":"a","material":MATERIAL,"idempotency_key":"k1"})[0],201)
   self.assertEqual(len(dispatch(f2,"GET","/cases")[1]),2)
if __name__=="__main__": unittest.main()

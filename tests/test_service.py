import os
import sqlite3
import tempfile
import unittest

from service_09261_010.api import dispatch
from service_09261_010.store import SQLiteStore
from service_09261_010.workflow import ValidationError, Workflow


class TestFlow(unittest.TestCase):
    def test_flow(self):
        f = Workflow()
        self.assertEqual(f.create("c1", "a", "k").state, "draft")
        self.assertEqual(f.create("c1", "a", "k").version, 1)
        self.assertEqual(f.move("c1", "reviewing", "b").state, "reviewing")


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteStore()
        self.flow = Workflow(self.store)

    def test_malformed_submission_rejected_without_residue(self):
        bad = [
            ("", "leader", None), ("bad id", "leader", None), ("_c1", "leader", None),
            (None, "leader", None), (123, "leader", None), ("x" * 65, "leader", None),
            ("c1", "", None), ("c1", "  ", None), ("c1", None, None),
            ("c1", "leader", ""), ("c1", "leader", 123),
        ]
        for id, actor, key in bad:
            with self.assertRaises(ValidationError, msg=repr((id, actor, key))):
                self.flow.create(id, actor, key)
        self.assertEqual(self.flow.snapshot(), [])
        self.assertEqual(self.store.load_cases(), [])

    def test_malformed_material_cannot_enter_review_queue(self):
        status, payload = dispatch(self.flow, "POST", "/cases", {"id": "bad id", "actor": "leader"})
        self.assertEqual(status, 422)
        self.assertIn("error", payload)
        status, rows = dispatch(self.flow, "GET", "/cases")
        self.assertEqual((status, rows), (200, []))


class TestAtomicity(unittest.TestCase):
    def test_create_interrupted_write_leaves_no_partial_record(self):
        class BrokenStore(SQLiteStore):
            def insert_case(self, rec):
                raise IOError("write interrupted")

        flow = Workflow(BrokenStore())
        with self.assertRaises(IOError):
            flow.create("c1", "leader", "k1")
        self.assertEqual(flow.rows, {})
        self.assertEqual(flow.keys, {})
        self.assertEqual(flow.snapshot(), [])

    def test_move_interrupted_write_keeps_previous_state(self):
        class FlakyStore(SQLiteStore):
            fail = False

            def update_case(self, rec):
                if self.fail:
                    raise IOError("write interrupted")
                super().update_case(rec)

        store = FlakyStore()
        flow = Workflow(store)
        flow.create("c1", "leader", "k1")
        store.fail = True
        with self.assertRaises(IOError):
            flow.move("c1", "reviewing", "reviewer")
        self.assertEqual(flow.rows["c1"].state, "draft")
        self.assertEqual(store.load_cases()[0]["state"], "draft")
        store.fail = False
        self.assertEqual(flow.move("c1", "reviewing", "reviewer").state, "reviewing")

    def test_invalid_transition_changes_nothing(self):
        store = SQLiteStore()
        flow = Workflow(store)
        flow.create("c1", "leader")
        with self.assertRaises(ValueError):
            flow.move("c1", "approved", "reviewer")
        self.assertEqual(flow.rows["c1"].state, "draft")
        rec = store.load_cases()[0]
        self.assertEqual((rec["state"], rec["version"]), ("draft", 1))

    def test_store_rolls_back_conflicting_insert(self):
        store = SQLiteStore()
        rec = {"actor": "a", "state": "draft", "version": 1, "idempotency_key": "k"}
        store.insert_case(dict(rec, id="c1"))
        with self.assertRaises(sqlite3.IntegrityError):
            store.insert_case(dict(rec, id="c2"))
        self.assertEqual([r["id"] for r in store.load_cases()], ["c1"])


class TestRecovery(unittest.TestCase):
    def test_todos_match_submissions_after_restart(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            first = Workflow(SQLiteStore(path))
            first.create("c1", "leader1", "k1")
            first.create("c2", "leader2", "k2")
            first.move("c1", "reviewing", "reviewer")
            expected = first.snapshot()
            # 模拟服务重启：从同一数据库恢复
            second = Workflow(SQLiteStore(path))
            self.assertEqual(second.snapshot(), expected)
            # 恢复后幂等重放返回原记录，不产生重复待办
            self.assertEqual(second.create("c1", "leader1", "k1").id, "c1")
            self.assertEqual(second.snapshot(), expected)
            self.assertEqual(len(second.snapshot()), 2)
        finally:
            os.unlink(path)


class TestApi(unittest.TestCase):
    def setUp(self):
        self.flow = Workflow(SQLiteStore())

    def test_create_move_and_listing(self):
        status, row = dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "leader", "idempotency_key": "k1"})
        self.assertEqual((status, row["state"]), (201, "draft"))
        status, row = dispatch(self.flow, "POST", "/cases/c1/move", {"state": "reviewing", "actor": "reviewer"})
        self.assertEqual((status, row["state"], row["version"]), (200, "reviewing", 2))
        status, rows = dispatch(self.flow, "GET", "/cases")
        self.assertEqual(status, 200)
        self.assertEqual([r["id"] for r in rows], ["c1"])

    def test_missing_fields_rejected(self):
        status, payload = dispatch(self.flow, "POST", "/cases", {})
        self.assertEqual(status, 422)
        self.assertIn("error", payload)
        self.assertEqual(self.flow.snapshot(), [])

    def test_non_dict_body_rejected(self):
        status, _ = dispatch(self.flow, "POST", "/cases", ["not-a-dict"])
        self.assertEqual(status, 400)

    def test_duplicate_rejected(self):
        dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "a"})
        status, _ = dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "a"})
        self.assertEqual(status, 409)
        self.assertEqual(len(self.flow.snapshot()), 1)

    def test_idempotent_replay_returns_same_record(self):
        _, first = dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "a", "idempotency_key": "k"})
        _, second = dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "a", "idempotency_key": "k"})
        self.assertEqual(first, second)
        self.assertEqual(len(self.flow.snapshot()), 1)

    def test_invalid_transition_does_not_corrupt(self):
        dispatch(self.flow, "POST", "/cases", {"id": "c1", "actor": "a"})
        status, _ = dispatch(self.flow, "POST", "/cases/c1/move", {"state": "approved", "actor": "b"})
        self.assertEqual(status, 409)
        _, rows = dispatch(self.flow, "GET", "/cases")
        self.assertEqual((rows[0]["state"], rows[0]["version"]), ("draft", 1))

    def test_move_unknown_case_is_404(self):
        status, _ = dispatch(self.flow, "POST", "/cases/nope/move", {"state": "reviewing", "actor": "b"})
        self.assertEqual(status, 404)

    def test_unknown_path_is_404(self):
        status, _ = dispatch(self.flow, "GET", "/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

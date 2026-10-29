import json
import queue
from types import SimpleNamespace
import unittest
from memory_backend import inspect_owner
from test_backend import FakeMemory
from worker import Worker


class Tests(unittest.TestCase):
    def test_snapshot_reads_equipped_definition_without_writing(self):
        mem=FakeMemory()
        snapshot=inspect_owner(mem,mem.vector,[mem.definition])
        self.assertTrue(snapshot['owner_valid'])
        self.assertEqual(snapshot['recognized_items'][0]['kind'],'trinket')
        self.assertTrue(snapshot['trinkets'][0]['allowed'])
        self.assertTrue(snapshot['trinkets'][0]['chosen_definition_valid'])
        self.assertFalse(mem.writes)
        json.dumps(snapshot,allow_nan=False)

    def test_snapshot_distinguishes_stale_definition_cache(self):
        mem=FakeMemory()
        snapshot=inspect_owner(mem,mem.vector,[0x1234])
        self.assertTrue(snapshot['owner_valid'])
        self.assertEqual(snapshot['recognized_items'],[])
        self.assertFalse(snapshot['trinkets'][0]['allowed'])
        self.assertTrue(snapshot['trinkets'][0]['chosen_definition_valid'])
        self.assertFalse(mem.writes)

    def test_snapshot_reports_invalid_owner_without_searching_elsewhere(self):
        mem=FakeMemory()
        snapshot=inspect_owner(mem,0xdead,[mem.definition])
        self.assertFalse(snapshot['owner_valid'])
        self.assertEqual(snapshot['vector'],0xdead)
        self.assertEqual(snapshot['recognized_items'],[])
        self.assertFalse(mem.writes)

    def test_worker_reports_active_target_even_without_restore_records(self):
        worker=Worker(queue.Queue());worker.mem=FakeMemory()
        worker.adjustment=SimpleNamespace(vector=worker.mem.vector)
        worker.capture_diagnostic([worker.mem.definition])
        self.assertEqual(worker.diagnostic_snapshot()['vector'],worker.mem.vector)
        worker.adjustment=None
        worker.capture_diagnostic([worker.mem.definition])
        snapshot=worker.diagnostic_snapshot()
        self.assertIsNone(snapshot['vector'])
        self.assertFalse(snapshot['owner_valid'])
        self.assertFalse(worker.mem.writes)


if __name__=='__main__':unittest.main()

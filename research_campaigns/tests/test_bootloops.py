import tempfile
import unittest
from pathlib import Path
from research_campaigns.core import Ledger, digest, Denied
from research_campaigns.agents import analyse
from research_campaigns.bootloops import seal, verify

class BootLoopsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.tmp.name)/"ledger.sqlite")
        payload={"rows":[{"x":1,"y":3},{"x":2,"y":5},{"x":3,"y":7}]}
        self.source={"payload":payload,"sha256":digest(payload),"kind":"synthetic",
                     "available_at":"2026-01-01T00:00:00Z","captured_at":"2026-01-01T00:00:00Z"}
        self.plan={"method":"ols","x":"x","y":"y","source_key":"toy"}
    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()
    def freeze(self, candidate):
        return seal(self.ledger,"check",self.plan,self.source,candidate,
                    role="study_producer",cutoff="2026-02-01T00:00:00Z")
    def test_existing_analysis_and_resume(self):
        self.freeze(analyse(self.plan,self.source)["result"])
        first=verify(self.ledger,"check")
        self.assertEqual(first["status"],"numerically_checked")
        self.assertEqual(first,verify(self.ledger,"check"))
        self.assertEqual(first["scientific_validity"],"unverified")
        self.ledger.verify()
    def test_corrupted_answer_rejected(self):
        candidate=analyse(self.plan,self.source)["result"]
        candidate["slope"]=3
        self.freeze(candidate)
        self.assertEqual(verify(self.ledger,"check")["status"],"failed")
    def test_immutable_seal(self):
        self.freeze(analyse(self.plan,self.source)["result"])
        with self.assertRaises(Denied):
            self.freeze({"slope":9})
    def test_future_evidence_rejected(self):
        self.source["captured_at"]="2026-03-01T00:00:00Z"
        with self.assertRaises(Denied):
            self.freeze({})
    def test_checksum_rejected(self):
        self.source["payload"]["rows"][0]["y"]=99
        with self.assertRaises(Denied):
            self.freeze({})
    def test_no_unsealed_check(self):
        with self.assertRaises(Denied):
            verify(self.ledger,"missing")

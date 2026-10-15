import sys, unittest; sys.path.insert(0, "backend")
from engine import *

class T(unittest.TestCase):
    def setUp(self): self.db = connect()
    def test_valid_reuse_path(self):
        i = add_item(self.db, "glass jar", "glass", 0.9, "good", "HSR")
        for s in ["assessed", "available_for_reuse", "matched", "transfer_confirmed"]: transition(self.db, i, s, "t")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events WHERE item_id=?", (i,)).fetchone()[0], 5)
    def test_invalid_transition(self):
        i = add_item(self.db, "box", "cardboard", 0.9)
        with self.assertRaises(RuleError): transition(self.db, i, "handover_recorded", "x")
        with self.assertRaises(RuleError): transition(self.db, i, "scanned", "dup")
    def test_battery_abstains_and_cannot_batch(self):
        i = add_item(self.db, "household battery", "unknown", 0.4)
        self.assertEqual(route(self.db, i), "needs_verification")
        with self.assertRaises(RuleError): add_to_batch(self.db, i)
        transition(self.db, i, "specialist_handling", "verified"); 
        with self.assertRaises(RuleError): transition(self.db, i, "recovery_inventory", "x")
    def test_unknown_low_confidence(self):
        i = add_item(self.db, "thing", "plastic", 0.3); self.assertEqual(route(self.db, i), "needs_verification")
    def test_matching_ranks_and_explains(self):
        a = add_item(self.db, "glass jar", "glass", .9, "good", "HSR"); b = add_item(self.db, "glass bowl", "glass", .9, "poor", "BTM")
        for i in (a, b): route(self.db, i); transition(self.db, i, "available_for_reuse", "t")
        m = rank_matches(self.db, {"want": "glass jar", "locality": "HSR"})
        self.assertEqual(m[0]["item_id"], a); self.assertIn("same locality", m[0]["why"])
    def test_batch_totals_and_handover(self):
        ids = [add_item(self.db, "cardboard box", "cardboard", .9) for _ in range(4)]
        for i in ids: route(self.db, i); transition(self.db, i, "recovery_inventory", "t"); bid = add_to_batch(self.db, i)
        t = batch_totals(self.db, bid); self.assertEqual((t["items"], t["est_kg"], t["est_value_inr"]), (4, 1.4, 11.2))
        handover(self.db, bid, "Sample Kabadiwala A")
        with self.assertRaises(RuleError): handover(self.db, bid, "x")
        self.assertEqual(impact(self.db)["recycled_handover"], 4)
    def test_destinations_exclude_nonaccepting(self):
        self.assertTrue(all("glass" in d["accepts"] for d in rank_destinations("glass", 1)))
    def test_impact_omits_env_savings(self): self.assertIsNone(impact(self.db)["env_savings"])

unittest.main()

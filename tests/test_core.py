"""Offline standard-library tests: python3 -m unittest discover -s tests -v"""
import tempfile
import unittest
from pathlib import Path

from finiq.core import connect, import_csv, add_rule, report, to_cents

SAMPLE = """date,description,amount
2026-08-04,NETFLIX,-15.99
2026-09-04,NETFLIX,-15.99
2026-09-05,STARBUCKS,-8.50
2026-09-06,PAYROLL,3000.00
"""

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.temp.name) / "data.sqlite3")
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()
    def test_import_and_duplicate_skip(self):
        first = import_csv(self.db, SAMPLE)
        second = import_csv(self.db, SAMPLE)
        self.assertEqual(first["inserted"], 4)
        self.assertEqual(second["duplicates"], 4)
        self.assertEqual(report(self.db)["transaction_count"], 4)
    def test_financial_summary(self):
        import_csv(self.db, SAMPLE)
        summary = report(self.db)
        self.assertEqual(summary["income_cents"], 300000)
        self.assertEqual(summary["spending_cents"], 4048)
        self.assertEqual(summary["recurring"][0]["merchant"], "NETFLIX")
        self.assertEqual(summary["recurring"][0]["monthly_cents"], 1599)
    def test_custom_rule_and_reclassification(self):
        import_csv(self.db, SAMPLE)
        add_rule(self.db, "STARBUCKS", "Coffee")
        summary = report(self.db)
        self.assertIn("Coffee", [x["name"] for x in summary["categories"]])
    def test_bad_csv_rolls_back(self):
        with self.assertRaises(ValueError):
            import_csv(self.db, "date,description,amount\n2026-01-01,Coffee,-4\nBAD,Oops,3")
        self.assertEqual(report(self.db)["transaction_count"], 0)
    def test_debit_credit(self):
        result = import_csv(self.db,"date,description,debit,credit\n2026-01-01,Groceries,12.30,\n2026-01-02,Salary,,100.00")
        self.assertEqual(result["inserted"],2)
        self.assertEqual(report(self.db)["spending_cents"],1230)
    def test_decimal_amounts(self):
        self.assertEqual(to_cents("(12.50)"),-1250)
        self.assertEqual(to_cents("1,200.00"),120000)

if __name__=="__main__":
    unittest.main()

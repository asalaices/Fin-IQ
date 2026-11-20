"""Manifest validation regression tests, with synthetic (not personal) CSV data."""
import unittest

from finiq.sources import normalize, sources, SourceFormatError
from finiq.core import connect, import_csv, report
import tempfile
from pathlib import Path

WELLS = '11/01/2026,-42.19,*,,"GROCERY STORE"\n11/03/2026,2500.00,*,,"DIRECT DEP PAYROLL"\n11/05/2026,-125.00,*,1024,"CHECK PAYMENT"\n'
MONARCH = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags\n2026-10-05,Netflix,Streaming,Checking,NETFLIX.COM,,-15.99,\n2026-10-07,Payroll,Income,Checking,DIRECT DEP,,2800.00,\n'
class SourceContractTests(unittest.TestCase):
    def test_registry_has_supported_sources(self):
        self.assertEqual({x["id"] for x in sources()}, {"wells_fargo","monarch","generic"})
    def test_wells_headerless_and_check_number(self):
        data=normalize("wells_fargo",WELLS,"Checking")
        self.assertEqual(data["rows"],3)
        self.assertIn("[check 1024]",data["csv"])
        self.assertIn("2026-11-01,GROCERY STORE,-42.19,Checking",data["csv"])
    def test_wells_rejects_header_or_shifted_columns(self):
        for csv in ["Date,Amount,Flag,Check,Description\n"+WELLS,
                    '11/01/2026,-42.19,*,GROCERY STORE\n',
                    '11/01/2026,-42.19,XYZ,,"GROCERY STORE"\n']:
            with self.subTest(csv=csv[:40]),self.assertRaises(SourceFormatError):
                normalize("wells_fargo",csv)
    def test_wells_validates_every_row_before_db_write(self):
        with self.assertRaises(SourceFormatError):
            normalize("wells_fargo",WELLS + 'INVALID,-10.00,*,,"BAD"\n')
    def test_monarch_preserves_category_and_account(self):
        normalized=normalize("monarch",MONARCH)
        self.assertEqual(normalized["rows"],2)
        with tempfile.TemporaryDirectory() as folder:
            with connect(Path(folder)/"t.sqlite3") as db:
                imported=import_csv(db,normalized["csv"],source="monarch")
                self.assertEqual(imported["inserted"],2)
                summary=report(db)
                self.assertIn("Streaming", [c["name"] for c in summary["categories"]])
                self.assertEqual(summary["recent"][0]["account"],"Checking")
    def test_monarch_rejects_missing_header_and_short_row(self):
        for csv in [
            'Date,Merchant,Amount\n2026-10-05,Netflix,-15.99\n',
            'Date,Merchant,Category,Account,Amount\n2026-10-05,Netflix,Streaming,Checking\n'
        ]:
            with self.subTest(csv=csv),self.assertRaises(SourceFormatError):
                normalize("monarch",csv)
    def test_unknown_source_and_generic_validation(self):
        with self.assertRaises(SourceFormatError):
            normalize("unexpected",WELLS)
        with self.assertRaises(SourceFormatError):
            normalize("generic","date,description,amount\n2026-11-01,Groceries\n")
    def test_monarch_column_reordering(self):
        text="Amount,Account,Merchant,Date,Category\n-3.50,Checking,Coffee,2026-10-03,Dining\n"
        self.assertEqual(normalize("monarch",text)["rows"],1)

if __name__=="__main__":
    unittest.main()

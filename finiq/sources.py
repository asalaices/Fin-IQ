"""Manifest-backed CSV adapters. All rows validated before any SQLite mutation."""
import csv
import io
import json
from datetime import datetime
from pathlib import Path
from .core import to_cents

MANIFEST = Path(__file__).resolve().parents[1] / "config" / "data_sources.json"
MAX_BYTES = 5_000_000
MAX_RECORDS = 20_000

class SourceFormatError(ValueError):
    """Import stopped because the bank export does not match its source contract."""

def sources():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("manifest_version") != 1:
        raise SourceFormatError("unsupported source manifest version")
    return data["sources"]

def source_for(source_id):
    return next((item for item in sources() if item["id"] == source_id), None)

def _rows(content):
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
        raise SourceFormatError("invalid CSV or file larger than 5 MB")
    if "\x00" in content:
        raise SourceFormatError("binary/NUL content is not CSV")
    try:
        records = list(csv.reader(io.StringIO(content.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error as exc:
        raise SourceFormatError("CSV quoting/structure invalid") from exc
    records = [r for r in records if r and any(v.strip() for v in r)]
    if not records:
        raise SourceFormatError("empty export")
    if len(records) > MAX_RECORDS + 1:
        raise SourceFormatError("more than 20,000 rows")
    return records

def _date(value, fmts, row):
    for fmt in fmts:
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise SourceFormatError(f"row {row}: invalid date {value!r}")

def _amount(value, row):
    try:
        if not str(value).strip():
            raise ValueError("empty")
        return to_cents(value)
    except ValueError as exc:
        raise SourceFormatError(f"row {row}: invalid amount {value!r}") from exc

def _cell(value):
    value = str(value or "").strip()
    # Avoid CSV formula injection when writing normalized text back to a CSV.
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        value = "'" + value
    return value

def normalize(source_id, content, account="Default"):
    """Return canonical CSV, source ID and preview; never partially apply an import."""
    spec = source_for(source_id)
    if not spec:
        raise SourceFormatError("unknown data source")
    if not isinstance(account, str) or not (1 <= len(account) <= 120):
        raise SourceFormatError("an account label is required")
    rows = _rows(content)
    normalized = []
    if spec["header"] is False:
        width = spec["field_count"]
        for line, cells in enumerate(rows, 1):
            if len(cells) != width:
                raise SourceFormatError(f"row {line}: Wells Fargo requires {width} fields; got {len(cells)}")
            date = _date(cells[0], spec["date_formats"],line)
            cents = _amount(cells[1],line)
            if cells[2].strip() not in spec["fields"][2]["expected"]:
                raise SourceFormatError(f"row {line}: unexpected Wells Fargo status marker")
            if not cells[4].strip():
                raise SourceFormatError(f"row {line}: blank description")
            desc = cells[4].strip()
            if cells[3].strip():
                desc += " [check " + cells[3].strip()[:30] + "]"
            normalized.append((date, desc, f"{cents/100:.2f}", account, ""))
    elif source_id == "monarch":
        headers = [x.strip().casefold() for x in rows[0]]
        if len(headers) != len(set(headers)):
            raise SourceFormatError("duplicate column names")
        required = [x.casefold() for x in spec["required_headers"]]
        missing = [x for x in required if x not in headers]
        if missing:
            raise SourceFormatError("Monarch export missing headers: " + ", ".join(missing))
        indexes = {name:i for i,name in enumerate(headers)}
        for line, cells in enumerate(rows[1:],2):
            if len(cells) != len(headers):
                raise SourceFormatError(f"row {line}: expected {len(headers)} fields; got {len(cells)}")
            row = {k:cells[i].strip() for k,i in indexes.items()}
            date = _date(row["date"],spec["date_formats"],line)
            cents = _amount(row["amount"],line)
            merchant = row["merchant"]
            account_name = row["account"]
            if not merchant or not account_name:
                raise SourceFormatError(f"row {line}: merchant/account required")
            normalized.append((date,merchant,f"{cents/100:.2f}",account_name,row.get("category","")))
    else:
        # Generic exports remain subject to the existing named-header parser.
        headers = [x.strip().casefold() for x in rows[0]]
        if "date" not in headers or "description" not in headers:
            raise SourceFormatError("generic CSV needs date and description columns")
        if not ("amount" in headers or "debit" in headers or "credit" in headers):
            raise SourceFormatError("generic CSV needs amount or debit/credit columns")
        return {"csv":content,"source":source_id,"rows":len(rows)-1,"preview":[]}
    if not normalized:
        raise SourceFormatError("no transaction rows")
    out = io.StringIO()
    writer = csv.writer(out,lineterminator="\n")
    writer.writerow(["date","description","amount","account","category"])
    writer.writerows(normalized)
    return {"csv":out.getvalue(),"source":source_id,"rows":len(normalized),
            "preview":[{"date":r[0],"description":r[1],"amount":r[2],"account":r[3],"category":r[4]} for r in normalized[:5]]}

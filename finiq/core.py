"""Local financial data store, CSV ingestion and conservative pattern analysis."""
import csv
import hashlib
import io
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CATEGORIES = [
    ("Subscriptions", r"NETFLIX|SPOTIFY|HULU|DISNEY\+|APPLE\.COM/BILL|YOUTUBE PREMIUM|CHATGPT|OPENAI|ADOBE|DROPBOX|ICLOUD"),
    ("Groceries", r"KROGER|ALDI|WHOLE FOODS|TRADER JOE|H-E-B|HEB |SAFEWAY|WALMART GROCERY"),
    ("Dining", r"DOORDASH|UBER EATS|GRUBHUB|CHIPOTLE|STARBUCKS|RESTAURANT"),
    ("Transport", r"UBER(?! EATS)|LYFT|SHELL|CHEVRON|EXXON|TESLA SUPERCHARG"),
    ("Utilities", r"ELECTRIC|WATER BILL|ATMOS ENERGY|VERIZON|T-MOBILE|AT&T"),
    ("Housing", r"MORTGAGE|RENT PAYMENT|PROPERTY TAX"),
    ("Insurance", r"ALLSTATE|GEICO|STATE FARM|PROGRESSIVE"),
    ("Shopping", r"AMAZON|TARGET|BEST BUY|COSTCO"),
    ("Health", r"PHARMACY|CVS|WALGREENS|HOSPITAL|MEDICAL"),
]
HEADERS = {
    "date": ("date", "transaction date", "posted date", "posting date"),
    "description": ("description", "merchant", "details", "name", "payee"),
    "amount": ("amount", "transaction amount"),
    "debit": ("debit", "withdrawal", "withdrawals"),
    "credit": ("credit", "deposit", "deposits"),
    "account": ("account", "account name"),
}
DDL = """
CREATE TABLE IF NOT EXISTS transactions(
 id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, posted TEXT NOT NULL,
 description TEXT NOT NULL, amount_cents INTEGER NOT NULL, account TEXT NOT NULL,
 category TEXT NOT NULL, source TEXT NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rules(
 id INTEGER PRIMARY KEY, pattern TEXT NOT NULL, category TEXT NOT NULL,
 priority INTEGER NOT NULL DEFAULT 100
);
CREATE INDEX IF NOT EXISTS tx_posted_idx ON transactions(posted);
"""

def connect(filename):
    path = Path(filename).expanduser()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(DDL)
    return db

def to_cents(raw):
    s = str(raw or "").strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        value = Decimal(s)
        if not value.is_finite() or abs(value) > 10**11:
            raise ValueError("amount out of range")
        return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError("invalid amount: " + repr(raw)) from exc

def parse_date(raw):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("unsupported date: " + repr(raw))

def categorize(db, merchant, amount):
    if amount > 0:
        return "Income"
    for row in db.execute("SELECT pattern, category FROM rules ORDER BY priority, id"):
        if re.search(row["pattern"], merchant, flags=re.I):
            return row["category"]
    for category, pattern in CATEGORIES:
        if re.search(pattern, merchant, flags=re.I):
            return category
    return "Uncategorized"

def import_csv(db, content, account="Default"):
    if len(content.encode("utf-8")) > 5_000_000:
        raise ValueError("CSV exceeds 5 MB")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("CSV requires headers")
    columns = {c.strip().lower(): c for c in reader.fieldnames if c}
    fields = {k: next((columns[a] for a in aliases if a in columns), None) for k, aliases in HEADERS.items()}
    if not fields["date"] or not fields["description"] or not (fields["amount"] or fields["debit"] or fields["credit"]):
        raise ValueError("CSV needs date, description and amount (or debit/credit)")
    rows = []
    for line, row in enumerate(reader, 2):
        if line > 20002:
            raise ValueError("20,000-row import limit")
        if not any(str(v or "").strip() for v in row.values()):
            continue
        try:
            posted = parse_date(row[fields["date"]])
            desc = str(row[fields["description"]] or "").strip()[:500]
            if not desc:
                raise ValueError("missing description")
            if fields["amount"]:
                amount = to_cents(row[fields["amount"]])
            else:
                debit = to_cents(row.get(fields["debit"]) or "0") if fields["debit"] else 0
                credit = to_cents(row.get(fields["credit"]) or "0") if fields["credit"] else 0
                amount = credit - abs(debit)
            acct = str((row.get(fields["account"]) if fields["account"] else None) or account)[:120]
            key = hashlib.sha256(f"{posted}|{desc.casefold()}|{amount}|{acct.casefold()}".encode()).hexdigest()
            rows.append((key, posted, desc, amount, acct, categorize(db, desc, amount), "csv"))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"CSV row {line}: {exc}") from exc
    before = db.total_changes
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO transactions(fingerprint,posted,description,amount_cents,account,category,source) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
    inserted = db.total_changes - before
    return {"rows": len(rows), "inserted": inserted, "duplicates": len(rows)-inserted}

def add_rule(db, pattern, category):
    if not isinstance(pattern, str) or not isinstance(category, str) or not (1 <= len(pattern) <= 120) or not (1 <= len(category) <= 60):
        raise ValueError("invalid rule")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError("invalid regular expression") from exc
    with db:
        db.execute("INSERT INTO rules(pattern,category) VALUES (?,?)", (pattern, category))
        # Reclassify negatives with all active rules, preserving category precedence.
        rows = db.execute("SELECT id,description,amount_cents FROM transactions WHERE amount_cents<0").fetchall()
        for row in rows:
            db.execute("UPDATE transactions SET category=? WHERE id=?",
                       (categorize(db, row["description"], row["amount_cents"]),row["id"]))

def report(db):
    tx = [dict(x) for x in db.execute("SELECT posted,description,amount_cents,category,account FROM transactions ORDER BY posted DESC,id DESC")]
    months = defaultdict(lambda: {"income_cents":0,"spending_cents":0})
    totals = defaultdict(int)
    by_merchant = defaultdict(list)
    merchant_category = {}
    for t in tx:
        amount = t["amount_cents"]
        m = months[t["posted"][:7]]
        m["income_cents"] += max(amount,0)
        m["spending_cents"] += max(-amount,0)
        if amount < 0:
            totals[t["category"]] += -amount
            merchant = re.sub(r"\s+", " ", re.sub(r"\b\d{3,}\b", "", t["description"].upper())).strip()[:80]
            by_merchant[merchant].append((t["posted"][:7],-amount))
            merchant_category[merchant] = t["category"]
    recurring = []
    for merchant, amounts in by_merchant.items():
        observed = {month for month,_ in amounts}
        if len(observed) < 2:
            continue
        values = sorted(v for _,v in amounts)
        median = values[len(values)//2]
        if median > 0 and sum(abs(v-median) <= max(100,median//5) for _,v in amounts) >= 2:
            recurring.append({"merchant":merchant,"monthly_cents":median,"months":len(observed),"category":merchant_category[merchant]})
    recurring.sort(key=lambda x:-x["monthly_cents"])
    monthly = [{"month":name,**v,"net_cents":v["income_cents"]-v["spending_cents"]} for name,v in sorted(months.items())]
    count = max(len(monthly),1)
    cuts = [{"category":key,"savings_monthly_cents":round(totals[key]*0.10/count)} for key in ("Dining","Shopping","Subscriptions","Transport") if totals[key]]
    cuts.sort(key=lambda x:-x["savings_monthly_cents"])
    return {
        "transaction_count":len(tx),
        "income_cents":sum(x["income_cents"] for x in monthly),
        "spending_cents":sum(x["spending_cents"] for x in monthly),
        "monthly":monthly,
        "categories":[{"name":k,"cents":v} for k,v in sorted(totals.items(), key=lambda x:-x[1])],
        "recurring":recurring,"cuts":cuts,
        "suggested_monthly_budget_cents":round(sum(x["spending_cents"] for x in monthly)*.9/count),
        "recent":tx[:100],
    }

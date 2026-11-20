# Source import contracts (schema v1)

`config/data_sources.json` is the versioned registry. Every bank/provider must define a stable source ID, CSV header policy, field mapping, sign convention, accepted date formats, mandatory fields and account scope. `finiq/sources.py` normalizes each provider into the canonical columns `date,description,amount,account,category`; `finiq/core.py` applies deterministic classification, dedupe and SQLite writes.

## Source selection and failure policy

The UI requires selecting the source, running **Validate / preview**, and then explicitly confirming import. No bank CSV is guessed from a filename. All rows are parsed and validated before inserting anything. A malformed/missing field, wrong width, invalid amount/date, or unexpected Wells Fargo marker rejects the entire file with a row-numbered error. CSV strings are parsed with the standard-library CSV module, so quoted merchant text containing commas is not mistaken for a new column.

### Wells Fargo (`wells_fargo`)

Observed third-party documentation indicates **no header row**, exactly 5 positional fields:

| Index | Meaning | Required | Notes |
| --- | --- | --- | --- |
| 0 | Transaction date | Yes | M/D/YYYY or M/D/YY |
| 1 | Signed amount | Yes | Negative withdrawal, positive deposit |
| 2 | Marker | Recognized | Usually `*` or blank |
| 3 | Check number | No | Appended to description for now |
| 4 | Description | Yes | Merchant / bank text |

Synthetic example (not a user's bank data):

```csv
11/01/2026,-42.19,*,,"GROCERY STORE"
11/03/2026,2500.00,*,,"DIRECT DEP PAYROLL"
```

The online **Download Account Activity → Comma Delimited (CSV)** export should be saved without Excel reformatting. This contract is **provisional until compared to a real redacted Wells Fargo export**. Other Wells Fargo products (credit cards, brokerage, business accounts) may use different layouts and should receive distinct source IDs/contracts rather than silently forcing this layout.

### Monarch Money (`monarch`)

Named-header CSV. Required: `Date, Merchant, Amount, Account`. Optional: `Category, Original Statement, Notes, Tags, Transaction ID`. The adapter maps columns case-insensitively regardless of order, preserves category and account, and accepts negative amounts as outflows. Monarch's official documentation confirms a transaction ID may be exported; the initial importer does **not yet** retain that ID in SQLite. A later schema migration should preserve provider IDs, raw statement descriptions and external categories separately from user-edited categories.

### Generic CSV (`generic`)

Named-header dates, descriptions and a signed amount or debit/credit columns. Validated for row width and parseable dates/amounts; legacy aliases remain supported by the core importer.

## Financial interpretation and known limitations

- The source manifest determines *column meaning*, not whether every negative amount is actual consumption. Transfers, credit-card payments and refunds still require account-aware transfer matching to avoid double-counting; this is a **remaining feature**.
- Deduplication is based on date + normalized description + amount + account, which can suppress separate identical same-day transactions. Provider transaction IDs and a user-facing reconciliation preview are future improvements.
- Do not put real bank exports, account identifiers, passwords, browser session cookies or login credentials into this repository or test fixtures.
- For Wells Fargo, validate against a redacted real CSV before enabling unattended Playwright import.
- Update this contract, adapter and regression tests together when a source changes its CSV format.

## Documentation examined

- Wells Fargo export explanation: https://fynnap.com/guides/wells-fargo-csv-export (independent third party, not authoritative Wells Fargo documentation)
- Monarch export: https://help.monarch.com/hc/en-us/articles/15526600975764-Downloading-Transaction-or-Account-History
- Monarch CSV import fields and sign convention: https://help.monarch.com/hc/en-us/articles/4409682789908-Importing-Transactions-Manually

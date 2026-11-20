# Fin-IQ

A local-first, Python-only Mac financial intelligence dashboard inspired by the loopback Execution Desk architecture in [master-01](https://github.com/asalaices/master-01). Plain HTML, Python 3.10+, SQLite, and standard-library HTTP. No Node, no frontend bundler, and no cloud upload of transaction data.

## Install and run

```sh
git clone https://github.com/asalaices/Fin-IQ.git
cd Fin-IQ
bash install.sh
bash server.sh --action start
open http://127.0.0.1:18781/
```

`bash server.sh --action start|stop|restart|status|foreground`.

Installer re-runs are idempotent. Local database and logs live in `~/.local/state/finiq/` (override via `FINIQ_STATE_DIR`). Re-running the installer does not delete SQLite data. Python and SQLite dependencies are standard library; optional `bash install.sh --with-playwright` prepares browser binaries for future bank-specific adapters.

## First features

- CSV ingestion (date, description, amount; or debit/credit), per-account labels and duplicate detection.
- Categorization via built-in rules and user-supplied regex, with existing records reclassified when rules change.
- Monthly cash flow, category spending, merchant repeat-charge candidates, simple 10% discretionary saving scenarios.
- Suggested monthly budget = 90% of observed average monthly spending. This is a starting heuristic, not a personalized or complete budget.
- Six Execution Desk-inspired palettes: Dark, Light, Ocean, Midnight, Plum, Sand.
- Update manager in the local UI: authenticated session checks `git fetch`, and explicit upgrade performs `git pull --ff-only` only on clean `main`. Restart via `bash server.sh --action restart`.

The initial implementation does **not** include automatic bank downloads or credential automation. Provider-specific Playwright adapters should be implemented only after validating the bank site and approved authentication workflow. The app does not perform cancellations. Recurring charges represent review candidates, not verified subscriptions.

## Accepted CSV shape

```csv
date,description,amount
2026-10-01,Payroll,2500.00
2026-10-02,NETFLIX,-15.99
```

Dates: YYYY-MM-DD, MM/DD/YYYY, MM/DD/YY, MM-DD-YYYY, YYYY/MM/DD. Positive amounts count as income, negative as spending. For debit/credit formats, debit is outflow and credit is inflow. Banks that express outflows as positive amounts in a single `amount` column require conversion before import. Identical date/merchant/amount/account records are deduplicated, so a legitimate repeated identical same-day purchase may be omitted. Compare statement totals before relying on reports.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Privacy and operating boundaries

Server binds to `127.0.0.1` only, checks request Host and Origin and requires an in-memory token for mutations. These measures are intended for a trusted local single-user Mac, not an untrusted multi-user machine. Do not port-forward this HTTP service or use it as a public web app. Imported finance data is not tracked by Git; protect local storage and Mac user access. Never commit credentials, bank cookies, or transaction data. Review changes before upgrades. Since updater pulls code from the repository, Git repository write access must be controlled.

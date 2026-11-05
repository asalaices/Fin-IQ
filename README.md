# Fin-IQ

A small finance analysis backend for understanding money movement, identifying
savings opportunities, and estimating a financial outlook from supplied transactions.
No bank integration, external services, or runtime dependencies are required.

## Run

Requires Node.js 22 or later.

```sh
npm start
# Optional: PORT=4000 npm start
npm run check
npm test
```

The service listens on `127.0.0.1:3000`. `GET /health` reports readiness.
`POST /analysis` accepts JSON:

```sh
curl http://127.0.0.1:3000/analysis \
  -H 'Content-Type: application/json' \
  -d '{
    "currency": "USD",
    "openingBalanceCents": 100000,
    "periodStart": "2026-01-01",
    "periodEnd": "2026-01-31",
    "forecastDays": 30,
    "transactions": [
      {"date": "2026-01-01", "amountCents": 300000, "category": "Salary"},
      {"date": "2026-01-02", "amountCents": -150000, "category": "Housing"},
      {"date": "2026-01-15", "amountCents": -20000, "category": "Dining", "discretionary": true}
    ]
  }'
```

### Input and interpretation

- All amounts are safe integer cents: positive for inflows, negative for outflows.
  Supply a single currency with two decimal places per request (`USD` by default);
  there is no currency conversion. The three-letter code is syntax-checked only.
- `openingBalanceCents` is the balance immediately before the observation period.
  Dates must be real `YYYY-MM-DD` dates. Both period boundaries are inclusive;
  every transaction must fall within that period.
- Submit a complete, deduplicated set of settled transactions for the period.
  Exclude internal transfers when analyzing multiple accounts together to avoid
  double-counting income and expenses. Positive refunds count as inflows.
- Categories are supplied by the caller, not inferred. `discretionary` is an
  optional boolean, defaulting to false; flag only expenses that could be reduced.
- `forecastDays` defaults to 30 and must be between 1 and 365.
- Requests are limited to 1 MiB and 10,000 transactions. Invalid inputs or monetary
  overflow return HTTP 400, oversized bodies 413, and unsupported content types 415.

### Analysis

The response contains:

- **`moneyMovement`**: total income, expenses, net cash flow, closing balance, and
  category totals, all in cents.
- **`savingsOpportunities`**: discretionary expense categories ranked by potential
  savings if spending falls by 10% over a comparable observation period. These
  are optional spending-reduction scenarios, not guaranteed savings.
- **`outlook`**: surplus/deficit/balanced trend, projected balance, and a projected
  overdraft flag. The projection adds the observed average daily net cash flow
  times `forecastDays` to the closing balance, rounded to whole cents. All calendar
  days count, including days with no transactions. Empty history assumes zero
  cash flow and leaves the balance unchanged.

For the example above, income is 300000 cents, expenses are 170000 cents,
closing balance is 230000 cents, the Dining savings scenario is 2000 cents,
and the 30-day projected balance is 355806 cents.

## Privacy and limitations

Analysis is stateless: transaction data is neither persisted nor logged, and
responses use `Cache-Control: no-store`. This is a local analysis service, not a
production banking platform. It has no authentication; keep it on loopback.
Before exposing it through a proxy or using it for real customer accounts, add
authentication, authorization, TLS, rate limits, and appropriate operational and
regulatory controls. Do not send account credentials or other identifying data.

Forecasts assume the observed cash flow continues, do not model payment timing,
interest, or market returns, and are not financial advice or a guarantee.
import assert from 'node:assert/strict';
import test from 'node:test';
import { analyze, ValidationError } from '../src/analysis.js';

function sample(overrides = {}) {
  return {
    openingBalanceCents: 100_000,
    periodStart: '2026-01-01',
    periodEnd: '2026-01-10',
    transactions: [
      { date: '2026-01-01', amountCents: 200_000, category: 'Salary' },
      { date: '2026-01-10', amountCents: -50_000, category: 'Rent' },
      { date: '2026-01-05', amountCents: -10_000, category: 'Dining', discretionary: true },
      { date: '2026-01-06', amountCents: -5_000, category: 'Dining', discretionary: true },
      { date: '2026-01-07', amountCents: 1_000, category: 'Dining' },
    ],
    ...overrides,
  };
}

test('summarizes signed cash movements and aggregates categories', () => {
  const result = analyze(sample());
  assert.equal(result.currency, 'USD');
  assert.equal(result.period.observedDays, 10);
  assert.deepEqual(result.moneyMovement, {
    openingBalanceCents: 100_000,
    incomeCents: 201_000,
    expenseCents: 65_000,
    netCashFlowCents: 136_000,
    closingBalanceCents: 236_000,
    byCategory: [
      { category: 'Salary', incomeCents: 200_000, expenseCents: 0 },
      { category: 'Rent', incomeCents: 0, expenseCents: 50_000 },
      { category: 'Dining', incomeCents: 1_000, expenseCents: 15_000 },
    ],
  });
  assert.equal(result.outlook.projectedBalanceCents, 644_000);
  assert.equal(result.outlook.trend, 'surplus');
  assert.equal(result.outlook.projectedOverdraft, false);
});

test('suggests savings only on explicitly discretionary expenses', () => {
  const result = analyze(sample());
  assert.deepEqual(result.savingsOpportunities, [{
    category: 'Dining',
    discretionaryExpenseCents: 15_000,
    potentialSavingsCents: 1_500,
    suggestion: 'Consider reducing discretionary spending in this category by 10%.',
  }]);
});

test('sorts savings suggestions and handles object-like category names safely', () => {
  const result = analyze(sample({ transactions: [
    { date: '2026-01-01', amountCents: -100, category: '__proto__', discretionary: true },
    { date: '2026-01-01', amountCents: -500, category: ' Shopping ', discretionary: true },
  ] }));
  assert.deepEqual(result.savingsOpportunities.map(item => item.category), ['Shopping', '__proto__']);
});

test('empty history produces a balanced, unchanged outlook', () => {
  const result = analyze(sample({ transactions: [] }));
  assert.equal(result.moneyMovement.closingBalanceCents, 100_000);
  assert.equal(result.outlook.projectedBalanceCents, 100_000);
  assert.equal(result.outlook.trend, 'balanced');
  assert.deepEqual(result.savingsOpportunities, []);
});

test('uses all calendar days including leap day and projects deficits', () => {
  const result = analyze(sample({
    openingBalanceCents: 100,
    periodStart: '2024-02-28',
    periodEnd: '2024-03-01',
    forecastDays: 3,
    transactions: [{ date: '2024-02-29', amountCents: -300, category: 'Bills' }],
  }));
  assert.equal(result.period.observedDays, 3);
  assert.equal(result.outlook.projectedBalanceCents, -500);
  assert.equal(result.outlook.trend, 'deficit');
  assert.equal(result.outlook.projectedOverdraft, true);
});

test('single-day forecasts round to whole cents', () => {
  const result = analyze(sample({
    periodEnd: '2026-01-01',
    forecastDays: 1,
    transactions: [{ date: '2026-01-01', amountCents: 1, category: 'Interest' }],
  }));
  assert.equal(result.period.observedDays, 1);
  assert.equal(result.outlook.projectedBalanceCents, 100_002);
});

test('rejects invalid input rather than producing misleading analysis', () => {
  const transaction = sample().transactions[0];
  for (const input of [
    null, [], {},
    sample({ openingBalanceCents: 1.5 }),
    sample({ openingBalanceCents: '100' }),
    sample({ openingBalanceCents: Number.MAX_SAFE_INTEGER + 1 }),
    sample({ periodStart: '2026-02-30' }),
    sample({ periodStart: '01/01/2026' }),
    sample({ periodStart: '2026-01-11' }),
    sample({ forecastDays: 0 }),
    sample({ forecastDays: 366 }),
    sample({ forecastDays: 1.5 }),
    sample({ currency: 'usd' }),
    sample({ transactions: {} }),
    sample({ transactions: Array(10_001).fill(transaction) }),
    ...[
      null, [],
      { ...transaction, date: '2026-01-11' },
      { ...transaction, date: '2026-01-00' },
      { ...transaction, amountCents: 0.1 },
      { ...transaction, category: ' ' },
      { ...transaction, category: 'x'.repeat(101) },
      { ...transaction, discretionary: 'true' },
    ].map(value => sample({ transactions: [value] })),
  ]) {
    assert.throws(() => analyze(input), ValidationError);
  }
});

test('rejects aggregate and projected monetary overflow', () => {
  const huge = { date: '2026-01-01', amountCents: Number.MAX_SAFE_INTEGER, category: 'Income' };
  assert.throws(() => analyze(sample({ transactions: [huge, huge] })), ValidationError);
  assert.throws(() => analyze(sample({ transactions: [huge] })), ValidationError);
  assert.throws(() => analyze(sample({
    openingBalanceCents: 0,
    periodEnd: '2026-01-01',
    forecastDays: 365,
    transactions: [{ ...huge, amountCents: 100_000_000_000_000 }],
  })), ValidationError);
});

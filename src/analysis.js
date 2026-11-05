const DAY_MS = 86_400_000;

export class ValidationError extends Error {}

function requireValue(condition, message) {
  if (!condition) throw new ValidationError(message);
}

function record(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function money(value, field) {
  requireValue(Number.isSafeInteger(value), `${field} must be a safe integer in cents`);
  return value;
}

function date(value, field) {
  requireValue(
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value),
    `${field} must be a valid YYYY-MM-DD date`,
  );
  const timestamp = Date.parse(`${value}T00:00:00.000Z`);
  requireValue(
    Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value,
    `${field} must be a valid YYYY-MM-DD date`,
  );
  return timestamp;
}

export function analyze(input) {
  requireValue(record(input), 'Request must be an object');
  const start = date(input.periodStart, 'periodStart');
  const end = date(input.periodEnd, 'periodEnd');
  requireValue(end >= start, 'periodEnd must not precede periodStart');
  const observedDays = (end - start) / DAY_MS + 1;
  const openingBalanceCents = money(input.openingBalanceCents, 'openingBalanceCents');
  const currency = input.currency ?? 'USD';
  requireValue(typeof currency === 'string' && /^[A-Z]{3}$/.test(currency),
    'currency must be a three-letter uppercase currency code');
  const forecastDays = input.forecastDays ?? 30;
  requireValue(Number.isInteger(forecastDays) && forecastDays >= 1 && forecastDays <= 365,
    'forecastDays must be an integer between 1 and 365');
  requireValue(Array.isArray(input.transactions) && input.transactions.length <= 10_000,
    'transactions must be an array with at most 10000 entries');

  let incomeCents = 0;
  let expenseCents = 0;
  const categories = new Map();
  for (const transaction of input.transactions) {
    requireValue(record(transaction), 'Each transaction must be an object');
    const timestamp = date(transaction.date, 'transaction.date');
    requireValue(timestamp >= start && timestamp <= end,
      'Transaction dates must fall within the observation period');
    const amount = money(transaction.amountCents, 'transaction.amountCents');
    requireValue(typeof transaction.category === 'string' &&
      transaction.category.trim().length > 0 && transaction.category.length <= 100,
    'transaction.category must contain 1 to 100 characters');
    requireValue(transaction.discretionary === undefined ||
      typeof transaction.discretionary === 'boolean', 'transaction.discretionary must be a boolean');
    const category = transaction.category.trim();
    const totals = categories.get(category) ?? {
      category, incomeCents: 0, expenseCents: 0, discretionaryExpenseCents: 0,
    };
    if (amount > 0) {
      incomeCents = money(incomeCents + amount, 'Total income');
      totals.incomeCents = money(totals.incomeCents + amount, 'Category income');
    } else {
      expenseCents = money(expenseCents - amount, 'Total expenses');
      totals.expenseCents = money(totals.expenseCents - amount, 'Category expenses');
      if (transaction.discretionary === true) {
        totals.discretionaryExpenseCents = money(
          totals.discretionaryExpenseCents - amount, 'Discretionary expenses',
        );
      }
    }
    categories.set(category, totals);
  }

  const netCashFlowCents = money(incomeCents - expenseCents, 'Net cash flow');
  const closingBalanceCents = money(openingBalanceCents + netCashFlowCents, 'Closing balance');
  const forecastChangeCents = money(
    Math.round(netCashFlowCents / observedDays * forecastDays), 'Forecast change',
  );
  const projectedBalanceCents = money(
    closingBalanceCents + forecastChangeCents, 'Projected balance',
  );
  const savingsOpportunities = [...categories.values()]
    .filter(category => category.discretionaryExpenseCents >= 10)
    .map(category => ({
      category: category.category,
      discretionaryExpenseCents: category.discretionaryExpenseCents,
      potentialSavingsCents: Math.round(category.discretionaryExpenseCents * 0.1),
      suggestion: 'Consider reducing discretionary spending in this category by 10%.',
    }))
    .sort((a, b) => b.potentialSavingsCents - a.potentialSavingsCents);

  return {
    currency,
    period: { start: input.periodStart, end: input.periodEnd, observedDays },
    moneyMovement: {
      openingBalanceCents, incomeCents, expenseCents, netCashFlowCents, closingBalanceCents,
      byCategory: [...categories.values()].map(({ discretionaryExpenseCents, ...totals }) => totals),
    },
    savingsOpportunities,
    outlook: {
      forecastDays,
      projectedBalanceCents,
      trend: netCashFlowCents > 0 ? 'surplus' : netCashFlowCents < 0 ? 'deficit' : 'balanced',
      projectedOverdraft: projectedBalanceCents < 0,
      assumption: 'Net cash flow continues at the observed daily average; not financial advice.',
    },
  };
}

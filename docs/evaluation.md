# Evaluation — capability coverage

This is **not** a script of hardcoded metric Q&A. The product must compute metrics for unscripted questions in these bands. Use the list to test; do not special-case these **performance** strings in code.

**Exception:** date / FY / quarter / month-as-of-clock questions *are* answered from the demo clock with no LLM. That is intentional (`agentflow.md` §4.0). “How did last quarter look?” is still unscripted SQL.

Set the demo clock (e.g. 14 Sep 2015) before a review so relative language has data.

## Bands a reviewer should be able to ask

Paraphrase freely.

### Clock and FY (deterministic)

- What date is it / what’s today / as of when
- Which FY quarter are we in / what financial year is this
- What is last month / last quarter as a date range

Expected on default clock `2015-09-14`: **FY2015 Q3**, today 14 September 2015. Works even if Ollama/Gemini is down.

### Performance

- How did the business perform last month / last quarter / year to date?
- Money earned per month for the last N months
- Booked vs invoiced, if they distinguish the two (cite grain)

### Geography

- Which region / country / territory grew or shrank?
- Compare two countries the data actually contains

### Customers and products

- Top customers or products this period
- Who dropped off / went quiet
- Mix shift (units vs revenue)

### Purchasing and stock

- Overdue POs, slow suppliers, spend by supplier
- What is at risk of stocking out
- Are we buying enough given recent demand

### Margin and both domains

- Thinnest margin SKUs
- Cost up while price flat

### Forward-looking (suggestion only)

- How might next quarter look, based on what we already see?
- Must name `metrics_used` (run-rate and/or same quarter last year). Must **not** sound like a trained forecast.

### Meta

- What needs attention right now? → live alerts, not a new invented list
- Follow-up on an open tab (“why that SKU?”) without restating the product name

## Bar for “correct”

- Numbers match a hand-run SQL on Postgres at the same clock (± rounding)
- Display sources are real tables
- SQL in the data pane is the query that produced the rows
- Clock change moves “last quarter” and changes totals
- Out-of-scope questions are refused without fake tables

## Design bar

- 1440px: extract-and-split is smooth; tabs for two different drill-downs; chat still accepts input
- No popup/drawer from the HTML mocks
- At least one ember card and one gold card when rules fire

## What failure looks like

- A switch/case on user text
- An insight with no rule_id in `copilot.alerts`
- A next-quarter number with no metrics disclosure
- Using `stock_item_holdings.quantity_on_hand` at a 2015 clock

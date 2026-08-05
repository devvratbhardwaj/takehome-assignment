# Construction Material Inventory Assistant

A conversational assistant for a construction material supplier: check stock, look up
supplier terms, and place orders against live inventory, all in natural language, with
every number coming from the database and never from the model.

Built as a FastAPI + SQLite backend with a LangChain tool-calling agent and a minimal chat
page. Source data is `raw_data/inventory_data.json` (77 SKUs, 9 suppliers), treated as a
read-only ERP feed.

**Live URL:** https://takehome-assignment.onrender.com/

---

## How to run locally

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Clone the repository
git clone https://github.com/devvratbhardwaj/takehome-assignment.git
cd takehome-assignment

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env        # or create .env by hand
# required:
#   OPENAI_API_KEY=sk-...
# optional:
#   OPENAI_MODEL=gpt-4o-mini      (default)
#   LANGSMITH_*                   (tracing, off by default)

# 4. Start the server (ingestion runs automatically at startup)
uv run fastapi dev app/main.py
```

Open <http://localhost:8000> for the chat page. The REST API lives under `/api`
(interactive docs at `/docs`).

The database is disposable by design: a local SQLite file that is dropped and rebuilt from
`raw_data/inventory_data.json` every time the server starts (and effectively in-memory on
the deployed free tier, where the disk is ephemeral). Restarting the server therefore
restores the original stock and clears any orders placed. The same rebuild can be
triggered on a running server, either with the **Reset data** button in the chat page or
directly through the API:

```bash
curl -X POST localhost:8000/api/admin/reset
```

Refreshing the page after a reset is advisable. The button clears the conversation in the
tab it is pressed in, but conversation history is held client-side, so any other open tab
would still be sending figures from before the reset back to the assistant.

Ingestion can also be run standalone; it is idempotent, dropping and rebuilding the tables
from the JSON every time:

```bash
uv run python -m app.ingest
```

Tests (88 of them, no network or API key needed; the agent layer is tested against fakes):

```bash
uv run pytest
```

---

## System flowchart

How a question travels through the system and back:

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Browser: chat page (static/index.html, served at /)                │
│  keeps the conversation history client-side                         │
└──────────────┬───────────────────────────────▲──────────────────────┘
               │  POST /chat                   │  { reply }
               ▼  { message, history }         │  shown in the chat box
┌──────────────────────────────────────────────┴──────────────────────┐
│  FastAPI app (app/main.py)                                          │
│    · GET  /             → chat page                                 │
│    · POST /chat         → runs the agent                            │
│    · /api/materials/…   → REST over the same service layer,         │
│    · /api/suppliers       no LLM involved                           │
│    · /api/orders                                                    │
│  startup: ingest raw_data/inventory_data.json → SQLite              │
└──────────────┬───────────────────────────────▲──────────────────────┘
               │  user message + history       │  phrased answer
               ▼                               │  (numbers from tools)
┌──────────────────────────────────────────────┴──────────────────────┐
│  Tool-calling agent (app/agent.py, LangChain + OpenAI)              │
│    · interprets the question, picks tools, phrases the reply        │
│    · never queries the DB, never computes a number                  │
└──────────────┬───────────────────────────────▲──────────────────────┘
               │  tool call (typed args)       │  structured JSON
               ▼                               │  result / rejection
┌──────────────────────────────────────────────┴──────────────────────┐
│  Tools (app/tools.py): thin wrappers, one per capability            │
│    · search_materials                                               │
│    · get_stock                                                      │
│    · quote_order                                                    │
│    · place_order                                                    │
│    · get_suppliers                                                  │
└──────────────┬───────────────────────────────▲──────────────────────┘
               │  service call                 │  result dict /
               ▼                               │  typed rejection
┌──────────────────────────────────────────────┴──────────────────────┐
│  Service layer (app/services.py): ALL business rules, unit-tested   │
│    · availability = qty_on_hand - qty_reserved (never stored)       │
│    · reject: insufficient stock, discontinued,                      │
│              unknown SKU, invalid quantity                          │
│    · line_total = unit_price × qty (quote_order / place_order)      │
│    · place_order: BEGIN IMMEDIATE → insert order + bump reserved    │
└──────────────┬───────────────────────────────▲──────────────────────┘
               │  SQL reads / writes           │  rows
               ▼                               │
┌──────────────────────────────────────────────┴──────────────────────┐
│  SQLite (inventory.db)                                              │
│    · tables: suppliers, materials, orders, meta                     │
│    · materials_with_availability view derives qty_available on read │
│    · rebuilt at startup from raw_data/inventory_data.json           │
│      (read-only source of truth, never modified)                    │
│    · same rebuild on demand: Reset data button or /api/admin/reset  │
└─────────────────────────────────────────────────────────────────────┘
```

### Where the decisions get made

| Decision | Made by |
|---|---|
| Which tools to call, how to phrase the reply | LLM (agent) |
| Availability math, order accept/reject, pricing, no-match handling | Python service layer (deterministic, tested) |
| What data exists | SQLite, rebuilt at startup |

---

## Approach and design write-up

### Architecture and alternatives considered

The dataset is small and uniform: 77 flat material rows and 9 suppliers. Three
architectures were evaluated.

1. **RAG (chunk, embed, vector search)**: rejected. Embedding provides approximate top-k
   retrieval, whereas the specification requires exact, reproducible figures and complete
   result sets. A vector store cannot compute `qty_on_hand - qty_reserved` or reject an
   order, and placing an order is a write operation (`qty_reserved` increases), which
   retrieval alone does not address.
2. **Text-to-SQL**: a closer fit, but it places the boundary incorrectly. Business rules
   would reside in the prompt, where they can be paraphrased or drift, and model-generated
   SQL against a live database is difficult to test or to trust with writes.
3. **Relational database with typed tools and a tool-calling agent**: selected. The rules
   reside in a deterministic, unit-tested Python service layer, and the model is limited
   to interpreting the question, calling typed tools, and phrasing the structured results.

### Why SQLite

- 77 rows and 9 suppliers need nothing more; a hosted Postgres would add operational
  overhead (connection strings, migrations, a second service) for zero benefit at this
  size.
- A single file plus drop-and-recreate ingestion at startup makes ingestion trivially
  repeatable and keeps the deployment a single container with no external state; the raw
  JSON remains the one source of truth.
- The relational model fits the data directly: keyed rows, a foreign key from materials to
  suppliers, and real transactions for the order path.

The trade-off is that placed orders persist only for the life of the process; a redeploy
or restart rebuilds the database from the JSON.

### Database schema and rationale

Four tables and one view, defined in [app/db.py](app/db.py). The three catalogue tables
mirror the feed; `orders` is the only table the application writes to.

| Object | Key | References | Contents and constraints |
|---|---|---|---|
| `meta` | `key` | | as-of date, currency and definitions from the feed's meta block |
| `suppliers` | `supplier_id` | | lead times and payment terms, mapped directly from the feed |
| `materials` | `sku` | `primary_supplier_id` → `suppliers` | the catalogue; CHECKs keep price and quantities non-negative and `discontinued` boolean |
| `orders` | `order_id`, autoincrement | `sku` → `materials` | one row per accepted order: quantity, unit price, line total, timestamp; CHECK `quantity > 0` |
| `materials_with_availability` | view over `materials` | | adds `qty_available` as `qty_on_hand - qty_reserved` |

`qty_available` is deliberately not a column. It exists only in the view, which makes
business rule 1 ("availability is derived, not stored") structurally impossible to violate:
there is no stored value that can go stale, and every stock lookup in the service layer
selects from the view rather than from `materials` directly.

`orders` records the unit price and line total as they stood when the order was accepted,
rather than deriving them from `materials` on read, so that a later price change cannot
alter the value of an order already placed. Its foreign key means an order against an
unknown SKU cannot be stored at all; because SQLite ignores `REFERENCES` clauses by
default, `get_connection` sets `PRAGMA foreign_keys = ON` for every connection.

Pydantic validates the feed before any insert, so the CHECK constraints are a second line
of defence rather than the primary one. No secondary indexes are defined: at 77 materials
every query is a small scan, and the primary keys cover the lookups that matter.

### Boundary between the LLM and application code

Correctness is implemented in Python; the model is responsible only for interpretation and
phrasing.

- The agent's five tools call the same service layer as the REST endpoints, so both
  interfaces enforce identical behaviour. Every business rule (availability math,
  over-quantity rejection, discontinued rejection, unknown-SKU handling, the customer-side
  `min_order_qty` exemption, and `line_total = unit_price × qty`) is implemented in code
  and covered by tests.
- The system prompt governs relay discipline rather than business logic. It requires that
  every number originate from a tool result, directs price questions to `quote_order`
  (which computes totals without reserving stock), restricts `place_order` to explicit
  order intent, and requires rejections to be relayed with their structured reason rather
  than retried with altered values.
- `quote_order` exists so that the model never performs arithmetic. A question such as
  "what would 500 cost" is answered from a code-computed `line_total`.

### Over-allocated stock

One SKU (`STL-W12X40-A992`) carries more reserved units (6) than on-hand units (4).
`qty_available` is reported as -2 in the database and in API payloads rather than clamped
to zero, because clamping would erase the distinction between a fully reserved item, which
is an expected state, and an over-allocated one, which indicates a data or process problem
that warrants attention.

To keep presentation logic out of the model, every payload carries derived fields
alongside the raw value: `orderable_qty` (`max(0, qty_available)`), an `over_allocated`
flag, and an explanatory note stating that reserved stock exceeds on-hand stock and that
nothing can be promised until existing reservations are resolved. Orders against such an
item are rejected.

### Concurrent order placement

Order placement reads `qty_available` and then increments `qty_reserved`. Without
isolation, two concurrent orders against the same remaining stock could both pass the
availability check and oversell the item.

`place_order` therefore opens its transaction with `BEGIN IMMEDIATE`, acquiring SQLite's
write lock before the availability read, so that the check and the reservation execute as
a single atomic unit. A competing order blocks until the first commits, then re-reads
availability that already reflects the first reservation and is rejected if stock is
exhausted. Any failure rolls back the entire transaction, so the `orders` insert and the
`qty_reserved` increment either both persist or neither does. The behaviour is covered by
a test that races two connections against the same stock.

### Expected failure points under real load

- **Search.** Token-based `LIKE` matching with a hand-curated synonym and plural list is
  sufficient for this catalogue but is the least robust component. New spelling variants,
  unit formats, or fraction styles ("half inch", "2.5" versus "2-1/2") in a larger feed
  would not match. SQLite FTS5 or an embedding-assisted matcher would replace it, with
  retrieval remaining approximate and the rules staying in code.
- **Write throughput.** `BEGIN IMMEDIATE` makes each order atomic but serializes writers
  against a single file. Sustained multi-user ordering would require Postgres.
- **Order durability.** Orders are lost on restart by design. A production deployment
  needs a persistent store and schema migrations in place of drop-and-recreate ingestion.
- **Tool selection.** Tool descriptions required tuning during testing; a `category`
  filter on search was removed after traces showed the model inferring incorrect
  categories and reporting catalogued items as absent. Additional tools or more ambiguous
  questions increase this risk, and an automated eval harness is the mitigation (see
  below).

---

## Business rules implemented and skipped

All seven spec rules are implemented; none skipped.

| # | Rule | Where |
|---|---|---|
| 1 | `qty_available` derived, never stored | SQL view `materials_with_availability`; negative availability reported as-is for over-allocated stock |
| 2 | Ordering increases `qty_reserved`, not `qty_on_hand` | `place_order` inserts into `orders` and increments `qty_reserved` in one transaction |
| 3 | Reject over-quantity, state what is available, no silent partial fulfilment | `insufficient_stock` rejection carries `orderable_qty` |
| 4 | Reject discontinued even with stock | `discontinued` rejection (checked before availability) |
| 5 | Never invent a SKU | strict AND search returns `[]` on no match; prompt and tool docstrings forbid substitution; close matches are labelled as alternatives only |
| 6 | `min_order_qty` is supplier-restock only | not enforced on customer orders; regression tests pin ordering 1 unit of a min-500 item |
| 7 | `line_total = unit_price × quantity`, no tax/discount | computed in `quote_order` / `place_order`, never by the LLM |

Extras beyond the spec: `quote_order` (pricing without reserving), invalid-quantity
rejection (`< 1`), `needs_reorder` flag from `reorder_point`, case-insensitive SKU and
category lookups, and a `POST /api/admin/reset` to re-run ingestion on a live deployment.

---

## Assumptions made

- **Order persistence.** Orders live for the life of the process; the DB is rebuilt from
  the JSON at startup (explicitly allowed by the spec's deployment notes when documented).
- **Quantities are whole units** of the sale unit of measure, end-to-end integers; 2.5 m³
  of concrete is rejected rather than rounded.
- **Question vs order intent.** "What would 500 cost?" or "can you fulfil that?" gets a
  quote; stock is only reserved on clear order intent. Both paths are tested.
- **No customer-side minimum order quantity.** A customer can order a single unit of an
  item whose `min_order_qty` is 500. The feed's meta block describes `min_order_qty` as a
  quantity the supplier will not go below, which reads as an ordering constraint, but rule
  6 of the specification states that it applies to restocking from the supplier only, so
  it is not enforced on customer orders. Both behaviours are covered by regression tests.
- **Stock-state wording.** A catalogued item with zero availability is "out of stock",
  never "not in the catalogue"; a discontinued item still exists and is described as
  discontinued, not missing.
- **Stateless server.** Conversation history is held by the browser and sent with each
  `/chat` request; there is no server-side session store.
- **Single currency.** All prices are CAD per the feed's `meta`; the assistant cites the
  as-of date (2026-08-01) from `meta` rather than implying live data.
- **No auth.** The API and the admin reset endpoint are open, for demo
  convenience.

---

## Tests

88 pytest tests, all runnable offline (`uv run pytest`) with no API key: ingestion
idempotency and feed validation, the availability view including negative availability,
every rejection path (insufficient stock, discontinued, unknown SKU, invalid quantity),
reservation increments, quote-versus-order semantics, the rule 6 regression, search
normalization (plurals, hyphens, unit words and spelling variants), REST status mapping,
and the chat endpoint against a fake agent.

The five specification queries and an additional batch of 11 edge-case queries were also
run against the live agent. Failures identified that way, covering spelling variants,
hyphenated compounds and case-sensitive category filters, were fixed and pinned with
regression tests.

---

## What I would do with another week

- **Hallucination guard.** A post-response verifier that extracts every number, SKU and
  supplier fact from the agent's reply and checks it appears in that turn's tool results;
  on mismatch, regenerate or flag the reply instead of sending it. Today the guarantee is
  prompt discipline plus tool design; this would make it enforced.
- **Automated eval harness.** Run the spec queries and the edge-case batch against the
  live agent on every change, scoring answers against the database, so prompt or tool
  regressions surface before a human notices.
- **Tool-call observability.** Log the tool name, arguments and a result summary for each
  `/chat` request; LangSmith tracing is already wired in via environment variables.
  Diagnosing the early live failures relied on inference rather than recorded evidence.
- **Improved search.** SQLite FTS5 with ranking, plus fraction and decimal normalization
  ("half inch", 1/2 and 0.5), keeping retrieval approximate and the rules exact.
- **Durable orders.** Postgres with migrations; ingestion becomes an upsert of the feed
  instead of drop-and-recreate, so orders survive restarts.
- **Server-side sessions.** Persist conversation history per session instead of
  round-tripping it through the client, enabling longer conversations and audit.
- **Reorder reporting.** A "what needs reordering" listing tool/endpoint; the per-SKU
  `needs_reorder` flag exists, but there is no aggregate view.
- **Auth and rate limiting.** Protect `/api/admin/reset` and order placement before any
  non-demo use; add streaming replies for perceived latency.

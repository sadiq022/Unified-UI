# Unified ERP — Development Roadmap

Companion to `unified_erp_manufacturing_features.md` (the product/feature spec). That
doc defines *what* the product is; this doc sequences *how it gets built* — in an
order where each phase is independently shippable and testable, and nothing gets
built before the thing it depends on exists.

Each phase lists: **goal**, **build**, **depends on**, and **done when** (the
concrete proof it works). Feature-spec section references are in `[§N]`.

---

## Phase 0 — Foundation: tenancy, roles, app separation
*No manufacturing feature yet — this is the plumbing everything else stands on.*

**Goal:** turn the current per-user-private data model into a per-company,
role-scoped one, and stand up ERP as its own app surface. `[§1, §2, §17]`

**Build:**
- `Company` table; `User` gains `company_id` + `role` (or a `CompanyMember`
  join table if a user can belong to >1 company).
- Role enum from `[§2]` (start with a minimal set: Admin, Planner, Operator,
  Storekeeper, Quality, Procurement — add the rest as their modules land).
- An `erp_require_role(*roles)` auth dependency, parallel to the existing
  `get_current_user`, scoping every ERP query by `company_id`.
- New backend package `backend/erp/` with its own router prefix `/api/erp/...`
  — zero imports from `backend/routes/chat.py` or the memory/compaction code.
- New frontend top-level mode switch (Chat / Operations) that swaps the whole
  main content area — not a panel inside the comparison view.
- Company setup screen: create company, invite/create users, assign roles.

**Depends on:** nothing (this *is* the dependency for everything else).

**Done when:** two users in different companies can each log in, see an empty
ERP shell scoped to their own company, and cannot see each other's data —
before a single manufacturing entity exists.

---

## Phase 1 — Master data
*Nothing manufacturing-specific works without this.*

**Goal:** items, units of measure, BOMs, routings, work centers, and physical
locations exist as company-scoped records. `[§4.1, §5.2, §11]`

**Build:**
- `Item` (product/material/finished-good), `UnitOfMeasure` + conversions.
- `Plant`, `Warehouse`, `Location/Bin`.
- `WorkCenter` (line/machine grouping).
- `BOM` + `BOMLine` (component, quantity, scrap %), with a simple revision
  field (full effective-dated versioning can wait for Phase 1b).
- `Routing` + `RoutingOperation` (sequence, work center, standard time).
- CRUD screens for all of the above — plain tables + forms, not fancy yet.

**Depends on:** Phase 0 (company scoping, role checks on who can edit master data).

**Done when:** you can define a finished good, its multi-level BOM down to raw
materials, and a routing through 2-3 work centers, entirely through the UI.

---

## Phase 2 — Inventory core

**Goal:** stock exists and moves, with a real ledger. `[§5.1–§5.4]`

**Build:**
- `StockBalance` (item × warehouse × location × lot, quantity, status:
  available/quarantine/hold).
- `StockMovement` (the append-only ledger: receipt, issue, transfer,
  adjustment — every balance change is derived from movements, never edited
  directly).
- `Lot`/`Batch` entity (serial-level can follow later if the target segment
  needs it — see `[§21]` decision on manufacturing type).
- Manual stock receipt (no PO yet — that's Phase 6) and manual issue/transfer/
  adjustment, each with a reason code and the acting user recorded.
- Basic reorder point / min-max fields on `Item` (surfaced later in Phase 5
  reporting, not acted on yet).

**Depends on:** Phase 1 (items, warehouses, locations must exist).

**Done when:** you can manually receive raw material into a warehouse, see the
on-hand balance update, transfer it to another location, and see full movement
history for that lot.

---

## Phase 3 — Work orders & the production loop
*This is the heart of the system — the first phase where "manufacturing"
actually happens.*

**Goal:** a work order can be created, consume materials, and produce output.
`[§4.3, §4.4]`

**Build:**
- `WorkOrder` (item, quantity, BOM/routing reference, status: planned →
  released → in progress → complete, due date, priority).
- Material reservation against the BOM (checks `StockBalance` availability).
- Material issue to the work order (creates `StockMovement`s, decrements
  reserved/available stock).
- Output recording: good quantity, scrap quantity, scrap reason — on
  completion, creates a `StockMovement` receipt of finished goods into
  inventory (still un-inspected/quarantined — Phase 4 releases it).
- A single operator-facing screen: "my work orders today," start/pause/
  complete, quantity + scrap entry. Desktop-first is fine; the tablet-optimized
  version from `[§4.4]` can follow.

**Depends on:** Phase 1 (BOM/routing) + Phase 2 (stock movements).

**Done when:** you can release a work order, issue its reserved materials,
record output and scrap, and watch raw material stock go down while
(quarantined) finished-good stock goes up.

---

## Phase 4 — Quality basics
*Closes the loop from §19's "recommended first-release scope."*

**Goal:** produced goods get inspected before they're usable stock. `[§7.1, §7.2]`

**Build:**
- `InspectionPlan` (minimal: which item, what to check, pass/fail criteria).
- `InspectionRecord` linked to a work order + lot (measured values, pass/fail,
  inspector, timestamp).
- Accept → moves stock from quarantine to available. Reject → quarantine hold
  or scrap, with a reason.
- A basic `NonconformanceReport` (NCR) — just enough to log a failure and its
  disposition; full CAPA workflow is Phase 7.

**Depends on:** Phase 3 (something has to exist to inspect).

**Done when:** the full loop from §19 works end to end: define product/BOM →
create work order → reserve → issue → record output/scrap → inspect →
accepted stock becomes available finished goods → rejected stock is
quarantined with an NCR.

**This is the milestone worth demoing to a real factory user before building
anything else** — it's the smallest slice that proves the concept.

---

## Phase 5 — Visibility: dashboard, reports, audit trail

**Goal:** the data flowing through Phases 1-4 becomes visible and trustworthy.
`[§3, §13, §16 audit event]`

**Build:**
- Role-scoped dashboard: production today (actual vs. target), open/at-risk
  work orders, low-stock items, open quality holds — pulling from what already
  exists, no new domain entities.
- Core reports: work order status/aging, inventory on-hand & movement history,
  first-pass yield, scrap rate.
- `AuditEvent` log on every state-changing action from Phases 1-4 (who, what,
  when, before/after) — retrofit this now while the number of mutation points
  is still small; it gets much harder to add comprehensively later.
- CSV export on every report table.

**Depends on:** Phases 1-4 (needs real data to visualize).

**Done when:** a plant manager can open the dashboard and answer "what shipped
today, what's stuck, what's low" without querying the database directly, and
every transaction from Phase 3-4 has a traceable audit entry.

---

## Phase 6 — Procurement
*Connects the "materials in" side properly instead of manual stock receipts.*

**Goal:** purchasing has its own workflow feeding Phase 2's stock receipts.
`[§6.1, §6.2]`

**Build:**
- `Supplier`, `PurchaseRequisition`, `PurchaseOrder` + `PurchaseOrderLine`.
- Approval routing on requisitions/POs (uses the role model from Phase 0).
- Goods receipt against a PO (replaces Phase 2's fully-manual receipt for the
  purchased-item case; manual receipt stays available for other cases).
- Incoming inspection hook: receipt can route into the Phase 4 inspection flow
  before stock becomes available.

**Depends on:** Phase 2 (stock receipt mechanism) + Phase 0 (approval roles).

**Done when:** a shortage on an item (from Phase 5's low-stock report) can be
turned into a requisition → approved → PO → received → inspected → available
stock, fully inside the system.

---

## Phase 7 — Extended quality, maintenance
*Matches feature-spec Phase 2 `[§18]`, split so each is independently useful.*

**7a — Full quality workflow:** NCR → root cause → CAPA with owner/due
date/effectiveness check; defect trend reporting. `[§7.3]`

**7b — Maintenance (CMMS-lite):** asset register, preventive maintenance
schedules, breakdown reporting, linking machine downtime to the `WorkCenter`
records from Phase 1 (so Phase 5's dashboards can show downtime against
production). `[§8]`

**Depends on:** Phase 4 (quality foundation) for 7a; Phase 1 (work centers) for 7b.

**Done when:** a recurring defect can be traced through root-cause to a closed
CAPA, and a machine breakdown shows up against the work center it affects.

---

## Phase 8 — Sales & dispatch

**Goal:** the customer-facing side of the loop. `[§9]`

**Build:**
- `Customer`, `SalesOrder` + lines, linked to production (make-to-order) or
  available finished-goods stock (make-to-stock).
- Pick/pack/dispatch records, delivery notes.
- OTIF (on-time-in-full) reporting, feeding back into Phase 5's dashboard.

**Depends on:** Phase 2 (finished-goods stock) + Phase 3 (make-to-order link).

---

## Phase 9 — Notifications & shop-floor UX polish

**Goal:** the system pushes information instead of requiring people to check
dashboards. `[§14]`

**Build:**
- Alert rules on top of existing data: low stock, work order at risk,
  approval pending, quality hold, maintenance due — all derivable from Phases
  1-8, no new domain entities.
- Barcode/QR scan support on the Phase 3 operator screen and Phase 2 stock
  movements. `[§4.4]`

**Depends on:** whichever phases produce the underlying events (mostly 2-6).

---

## Phase 10 — Factory Assistant (AI layer)
*Deliberately built last — it needs real, stable transactional data to be
grounded in, and its read-only nature makes it safe to bolt on once the core
is solid, rather than something to design around from day one.* `[§12]`

**Build:**
- Read-only, permission-scoped query layer over the ERP tables (reuses the
  existing multi-provider LLM abstraction from the chat product, exposed
  through a *new* ERP-specific endpoint — never mixed into the chat UI).
- Natural-language questions answered from live data, always with source
  record links (same citation pattern already built for "generate with
  sources" in the chat product — genuinely reusable here).
- Document extraction for POs/certificates/inspection reports, with mandatory
  human review before anything is written back — no auto-created transactions.
- "AI Model Lab" for comparing models on manufacturing tasks, fully isolated
  from live transactions. `[§12.4]`

**Depends on:** enough of Phases 1-8 to have real data worth asking about.

---

## Phase 11 — Advanced manufacturing
*Matches feature-spec Phase 4 `[§18]` — revisit after real customer usage,
not before.*

MRP and capacity planning, advanced scheduling/bottleneck analysis, full
costing + accounting integration, multi-plant planning, MES/PLC/IoT
integrations, sustainability tracking, forecasting.

---

## Why this order

- **Phases 0-4 are non-negotiable and sequential** — each is a hard dependency
  of the next, and Phase 4's completion is the same "connected manufacturing
  loop" your feature spec's §19 already identifies as the right first
  milestone to validate with a real factory user.
- **Phases 5-9 can reorder based on customer feedback** once the core loop
  works — e.g., a make-to-order shop might want Sales (8) before Maintenance
  (7b); a regulated shop might want full Quality (7a) before Procurement (6).
- **AI (10) is last on purpose** — every AI feature in `[§12]` is either
  read-only reporting or a draft requiring human confirmation, so it adds no
  value until there's real data and workflows to query and assist with.
- **Advanced (11) is explicitly deferred** — your own doc's `[§21]` open
  decisions (segment, manufacturing type, accounting scope) should be answered
  from real usage of Phases 0-9, not guessed upfront.

# Unified ERP — Manufacturing Enterprise Resource Planning

> **Product vision:** Unified ERP is an AI-enabled operations platform designed for manufacturing companies. It helps teams plan and track production, manage materials and inventory, coordinate purchasing, maintain quality, service equipment, fulfill customer orders, and understand operational costs.
>
> **Product separation:** Unified ERP is a dedicated manufacturing workspace, separate from the general-purpose Unified UI chat and multi-model comparison product.

---

## 1. Product structure

### 1.1 Unified UI — General AI workspace
- General-purpose conversations with AI models
- Side-by-side model response comparison
- Document upload and question answering
- Saved conversations and prompt examples
- Writing, coding, research, and learning workflows

### 1.2 Unified ERP — Manufacturing workspace
- Factory operations and business workflows
- Manufacturing-specific master data and transactions
- Role-based dashboards, approvals, and audit trails
- AI assistance grounded in authorized ERP data
- Reports and operational analytics

### 1.3 Workspace separation
- Separate navigation and home dashboards
- Separate permissions, data scope, and business context
- Shared account/login may be supported
- Optional links between products, without mixing general chats with ERP records
- ERP subscriptions and access can be managed separately

---

## 2. User roles and access control

Suggested roles (configurable per company):
- **Company Administrator:** company setup, users, roles, configuration
- **Plant Manager:** plant-wide operations, approvals, performance
- **Production Planner:** demand, capacity, schedules, work orders
- **Production Supervisor:** shift execution, labor, output, downtime
- **Operator:** assigned work instructions and production reporting
- **Storekeeper / Inventory Controller:** receipts, issues, transfers, counts
- **Procurement Officer:** requisitions, RFQs, purchase orders, suppliers
- **Quality Inspector / Quality Manager:** inspections, nonconformances, release/hold
- **Maintenance Manager / Technician:** assets, maintenance plans, breakdowns
- **Sales / Dispatch User:** customer orders, packing, shipping
- **Finance User:** costing, invoices, receivables/payables, accounting integration
- **Auditor / Read-only User:** permitted reports and history

Access principles:
- Role-based access control (RBAC), with optional plant/warehouse-level scope
- Segregation of duties for sensitive approvals
- Approval limits and delegated approvers
- Audit log for critical actions
- Restrict AI answers and actions to the user's authorized data
- Explicit confirmation for consequential transactions

---

## 3. Dashboard and navigation

### 3.1 Main navigation
- Dashboard
- Production
- Inventory & Warehouse
- Procurement
- Quality
- Maintenance
- Sales & Dispatch
- Products & BOM
- Customers & Suppliers
- Finance & Costing
- Analytics
- Reports
- Factory Assistant
- Users & Roles
- Company / Plant Settings

### 3.2 Dashboard KPIs
Show configurable cards based on role and plant:
- Production today: actual vs. target
- Open work orders and work orders at risk
- Low-stock and shortage items
- Quality holds, rejections, and open nonconformances
- Machine downtime and maintenance due
- On-time delivery / dispatch status
- Purchase orders awaiting receipt or approval
- Scrap, yield, and rework
- Cost variance and inventory value (permission-controlled)

### 3.3 Dashboard widgets
- Production performance: planned vs. actual by day, shift, line, or work center
- Inventory composition: raw materials, work in progress (WIP), finished goods
- Shortage and replenishment alerts
- Recent activity and transaction timeline
- Work orders requiring attention
- Upcoming maintenance
- Quality trend and defect Pareto
- Quick actions
- Factory Assistant prompt panel

### 3.4 Quick actions
- Create work order
- Receive materials
- Issue materials to production
- Create purchase requisition
- Record quality inspection
- Report machine breakdown
- Create sales order
- Record production output
- Start stock count
- Create dispatch

---

## 4. Production management

### 4.1 Product and process setup
- Finished goods, semi-finished goods, and intermediate products
- Bill of Materials (BOM), including quantities and scrap factors
- BOM revisions, effective dates, approvals, and version history
- Routings and operation sequences
- Work centers, production lines, and machine assignments
- Standard cycle times and setup times
- Work instructions, drawings, and controlled attachments
- Units of measure and conversions
- Production calendars, shifts, and holidays

### 4.2 Planning and scheduling
- Demand from sales orders, forecasts, or manual plans
- Master production schedule (MPS), where needed
- Material Requirements Planning (MRP)
- Capacity checks by work center and shift
- Planned start/end dates and priorities
- Finite or rough-cut capacity planning (future/advanced)
- Schedule conflict and bottleneck identification
- Rescheduling with impact preview and approval
- Production plan versioning

### 4.3 Work orders
- Create, release, pause, resume, and close work orders
- Work order number, product, quantity, due date, priority, and status
- Link to BOM, routing, sales order, and material reservations
- Allocate work center, machine, shift, and responsible supervisor
- Split or partially complete orders
- Record actual start/end times and quantities
- Record good output, scrap, rework, and reasons
- Track labor and machine time
- Attach instructions and relevant documents
- Work order status history

### 4.4 Shop-floor execution
- Operator-friendly tablet/mobile screens
- Assigned jobs and step-by-step work instructions
- Start/stop/pause operation reporting
- Production quantity and scrap entry
- Material consumption and returns
- Downtime reason capture
- Shift handover notes
- Supervisor review and correction workflow
- Barcode/QR scan support
- Offline/low-connectivity behavior as a later capability

### 4.5 Production reporting
- Planned vs. actual output
- Schedule adherence
- Work-in-progress aging
- Cycle-time and throughput trends
- Scrap and rework rates
- Labor and machine utilization
- Production variance by product, line, work center, and shift

---

## 5. Inventory and warehouse management

### 5.1 Inventory categories
- Raw materials
- Purchased components
- Packaging materials
- Work in progress (WIP)
- Finished goods
- Consumables and maintenance spares
- Scrap and rejected stock

### 5.2 Warehouse operations
- Multiple plants, warehouses, zones, bins, and locations
- Goods receipt and put-away
- Material issue to work orders
- Material return from production
- Stock transfers and inter-plant transfers
- Inventory adjustments with reason codes and approval
- Cycle counts and physical stock counts
- Reservations and allocations
- Stock availability by location and status

### 5.3 Traceability
- Batch/lot and serial number tracking
- Supplier lot and internal lot relationships
- Expiry dates and shelf-life controls, where relevant
- FIFO/FEFO or configured issue rules
- Genealogy: raw material lot → production order → finished goods lot
- Recall and containment support
- Quarantine and quality-hold stock

### 5.4 Inventory controls and reporting
- Reorder points and safety stock
- Min/max stock levels
- Lead-time-aware replenishment suggestions
- Stock aging and slow-moving inventory
- Inventory valuation integration
- Stock accuracy and count variance
- Shortage alerts and material availability checks

---

## 6. Procurement and supplier management

### 6.1 Purchasing workflow
1. Identify requirement from MRP, stock threshold, or user request
2. Create purchase requisition
3. Review and approve requisition
4. Request quotations (RFQ) from suppliers
5. Compare price, lead time, quality, terms, and availability
6. Create and approve purchase order
7. Track supplier acknowledgement and delivery
8. Receive and inspect materials
9. Record supplier invoice / pass to finance
10. Close or manage discrepancies

### 6.2 Procurement features
- Purchase requisitions and approval routing
- RFQs and quotation comparison
- Purchase orders and amendments
- Supplier lead times, minimum order quantities, and terms
- Blanket orders and scheduled releases (later phase)
- Partial deliveries and backorders
- Goods receipt against purchase order
- Supplier returns and claims
- Price history and purchasing analytics
- Supplier scorecards using defined metrics
- Document storage for certificates and contracts

### 6.3 Supplier metrics
- On-time delivery
- Lead-time reliability
- Rejection/defect rate
- Price movement
- Responsiveness and issue closure

---

## 7. Quality management

### 7.1 Inspection plans
- Incoming material inspection
- In-process inspection
- Final product inspection
- Sampling rules and checklists
- Specification limits and measurement units
- Pass/fail criteria
- Calibration status checks for measuring equipment

### 7.2 Quality execution
- Inspection records linked to material lots and work orders
- Record measured values, defects, photos, and notes
- Accept, reject, or quarantine decisions
- Nonconformance reports (NCR)
- Defect codes and severity
- Rework, repair, scrap, and concession workflows
- Customer complaint and return linkage

### 7.3 Corrective action and analytics
- Root-cause investigation
- Corrective and preventive action (CAPA)
- Owner, due date, evidence, and effectiveness check
- Defect trends by product, process, supplier, and work center
- First-pass yield and rejection rates
- Quality cost and scrap reporting
- Controlled quality documents and revision history

---

## 8. Machine and maintenance management

### 8.1 Asset register
- Machine/equipment ID, type, location, and owner
- Manufacturer, model, serial number, and warranty
- Criticality and operating status
- Linked manuals, drawings, and safety documents
- Meter readings and maintenance history

### 8.2 Maintenance planning and execution
- Preventive maintenance schedules by date, runtime, or cycles
- Maintenance work orders
- Breakdown reporting and priority
- Technician assignment and labor tracking
- Spare parts reservation and issue
- Checklists, findings, and repair notes
- Planned vs. unplanned maintenance
- Maintenance approvals and closure

### 8.3 Maintenance KPIs
- Downtime hours and causes
- Mean time between failures (MTBF)
- Mean time to repair (MTTR)
- Preventive maintenance compliance
- Maintenance backlog
- Spare-parts consumption and cost

---

## 9. Sales, customer orders, and dispatch

### 9.1 Customer and order management
- Customer master data and delivery locations
- Quotations and sales orders
- Product, quantity, price, requested date, and terms
- Make-to-stock and make-to-order support
- Order status and production linkage
- Availability-to-promise / delivery-date estimate (as data permits)
- Customer-specific specifications and documents

### 9.2 Fulfillment
- Allocate finished goods
- Pick lists and packing
- Batch/serial selection
- Dispatch planning and shipment records
- Delivery notes and proof of delivery
- Partial shipments and backorders
- Returns, complaints, and replacement orders

### 9.3 Sales reporting
- Order backlog
- On-time-in-full (OTIF) delivery
- Order lead time
- Returns and complaint trends
- Sales by product/customer/period

---

## 10. Finance and manufacturing costing

> Scope can begin with costing and accounting integration; a full accounting ledger is a substantial product area.

### 10.1 Manufacturing costing
- Standard and actual cost per product/order
- Material consumption cost
- Direct labor cost
- Machine time and overhead allocation
- Scrap, rework, and yield impact
- Planned vs. actual cost variance
- Cost roll-up from BOM and routing
- Cost by product, work center, plant, and order

### 10.2 Finance workflows
- Purchase invoice matching (PO, receipt, invoice)
- Sales invoice handoff or generation
- Accounts payable and receivable visibility
- Inventory valuation
- General ledger integration
- Tax and currency configuration, based on jurisdiction
- Financial period controls and approval trail

### 10.3 Financial controls
- Separation of operational and financial permissions
- Approval limits
- Period close controls
- Traceable source transactions
- Integration with established accounting systems where appropriate

---

## 11. Products, BOM, and engineering data

- Product master and item codes
- Product families and categories
- Units of measure and conversion rules
- BOM with component quantities, scrap allowance, and substitutes
- BOM revision control and effective dates
- Routings and operation steps
- Engineering change requests and approvals (advanced)
- Product drawings, specifications, and work instructions
- Approved substitutes and material restrictions
- Configuration/variant support where relevant

---

## 12. Factory Assistant and AI capabilities

### 12.1 Natural-language questions
Users can ask permission-checked questions such as:
- “Why is today's production below target?”
- “Which work orders are at risk of missing their due dates?”
- “Which materials may run out this week?”
- “Show machine downtime by work center this month.”
- “Summarize open quality issues for Product X.”
- “What is the actual cost variance for this production order?”
- “Which purchase orders are overdue?”

### 12.2 AI assistance by module
- **Production:** summarize plan-vs-actual, highlight recorded delays, explain bottlenecks from available data
- **Inventory:** identify shortages, summarize aging, draft replenishment suggestions
- **Procurement:** draft requisitions/RFQs and summarize supplier quotations
- **Quality:** summarize inspection results, cluster recurring defect descriptions, draft NCR/CAPA text
- **Maintenance:** summarize breakdown history and upcoming maintenance
- **Sales/dispatch:** summarize order risks and shipment status
- **Costing:** explain variances using available cost records
- **Documents:** extract structured fields from purchase orders, delivery notes, certificates, and inspection reports for human review

### 12.3 AI safeguards
- Retrieve only data the user is authorized to access
- Show data sources, record links, timestamps, and relevant filters
- Distinguish recorded facts from model-generated interpretation
- State when data is missing, stale, or incomplete
- Require user review for extracted or generated business records
- Require confirmation and authorization before creating or changing transactions
- Never silently approve purchases, release quality holds, adjust stock, alter schedules, or post financial entries
- Log AI-generated drafts and confirmed actions
- Provide feedback and correction mechanisms

### 12.4 Multi-model evaluation
- Optional “AI Model Lab” separate from routine factory workflows
- Compare models on the same approved manufacturing task and dataset
- Evaluate extraction accuracy, consistency, latency, and cost
- Keep model testing away from live transaction execution
- Use synthetic or permission-approved data for evaluation

---

## 13. Reports and analytics

### 13.1 Operational reports
- Production plan vs. actual
- Work order status and aging
- Material availability and shortages
- Inventory on hand, valuation, and aging
- Purchase order status and supplier delivery
- Quality inspection and nonconformance
- Scrap, rework, yield, and first-pass yield
- Machine downtime and maintenance compliance
- Dispatch and OTIF
- Manufacturing cost and variance

### 13.2 Analytics capabilities
- Filters by plant, date, shift, product, work center, supplier, and customer
- Drill-down from KPI to source transactions
- Export to CSV/XLSX/PDF (with permissions)
- Scheduled reports and email delivery (optional)
- Role-based saved views
- Data freshness indicators
- Metric definitions and calculation transparency

---

## 14. Notifications and workflow automation

- Low-stock and projected-shortage alerts
- Work order delayed or at-risk alerts
- Purchase approval and overdue delivery notifications
- Quality hold and failed-inspection notifications
- Preventive maintenance due and breakdown alerts
- Dispatch deadline reminders
- Approval inbox and task assignments
- Escalation rules and reminders
- Configurable notification channels and quiet hours
- Workflow rules with explicit ownership and audit history

---

## 15. Integrations

Potential integrations, prioritized by customer needs:
- Accounting/finance systems
- Barcode scanners and label printers
- Weighing scales and measurement devices
- CAD/PLM or engineering document systems
- MES and shop-floor data collection
- Machine/PLC/SCADA/IoT platforms through approved gateways
- Shipping/carrier systems
- Email and business messaging
- Identity provider / single sign-on
- Import/export from spreadsheets

Integration principles:
- Define system of record for each data domain
- Use authenticated APIs and least-privilege credentials
- Track sync status, errors, retries, and reconciliation
- Avoid assuming every factory has connected machines or reliable internet
- Make manual workflows available where automation is not feasible

---

## 16. Data model — core entities

- Company, plant, warehouse, location/bin
- User, role, permission, approval policy
- Item/product, unit of measure, BOM, BOM revision, routing
- Work center, machine/asset, shift, production calendar
- Demand/forecast, production plan, work order, operation
- Material reservation, issue, return, stock movement, stock count
- Batch/lot, serial number, traceability link
- Supplier, RFQ, supplier quotation, purchase requisition, purchase order, receipt
- Inspection plan, inspection result, defect, nonconformance, CAPA
- Maintenance plan, maintenance work order, downtime event, spare part
- Customer, quotation, sales order, pick/pack/dispatch, return
- Cost record, invoice reference, accounting integration record
- Document, notification, approval, audit event
- AI query, retrieved source references, generated draft, confirmed action log

---

## 17. Non-functional requirements

- Tenant/company data isolation
- Role- and scope-based access control
- Encryption in transit and at rest
- Auditability of important transactions
- Backup, recovery, and retention policies
- Availability and performance targets defined with customers
- Responsive desktop, tablet, and mobile interfaces
- Accessible, operator-friendly shop-floor screens
- Localization: language, timezone, date, number, currency, units
- Configurable units of measure and manufacturing calendars
- Import validation and data-quality tools
- API security, rate limits, and integration monitoring
- Data export and customer offboarding procedures
- Secure handling of AI prompts, retrieved records, and documents

---

## 18. Suggested MVP and roadmap

### Phase 1 — Manufacturing foundation (MVP)
- Company, plant, warehouse, users, and roles
- Product/item master, units, BOMs, and basic routings
- Inventory balances and stock movements
- Production orders and work orders
- Material reservation, issue, and return
- Basic quality inspection records
- Dashboard with core production and stock KPIs
- Essential reports, approvals, and audit trail

### Phase 2 — Connected factory workflows
- Purchase requisitions, suppliers, RFQs, and purchase orders
- Goods receipt and incoming inspection
- More complete quality/NCR workflows
- Machine register, breakdowns, and maintenance work orders
- Barcode/QR workflows
- Notifications and approval inbox
- Sales orders and dispatch basics

### Phase 3 — AI-enabled operations
- Permission-aware Factory Assistant
- Natural-language operational reporting
- Shortage and delay summaries
- Document extraction with review
- AI-generated drafts for requisitions, NCRs, and reports
- AI Model Lab for controlled manufacturing evaluations

### Phase 4 — Advanced manufacturing
- MRP and capacity planning enhancements
- Advanced scheduling and bottleneck analysis
- Manufacturing costing and accounting integrations
- Multi-plant planning
- Machine/MES/IoT integrations
- Energy, scrap, yield, and sustainability tracking
- Forecasting and optimization, validated against real factory data

---

## 19. Recommended first-release scope

For a first customer, choose one manufacturing segment and validate the workflow with factory users. A practical initial workflow is:

1. Define products, BOMs, work centers, and stock locations.
2. Create a production order.
3. Check and reserve required materials.
4. Issue materials to production.
5. Record output, scrap, and downtime.
6. Perform quality inspection.
7. Receive accepted finished goods into inventory.
8. Review plan-vs-actual and material consumption reports.

This creates a connected manufacturing loop before expanding into every ERP function.

---

## 20. Product design principles

- Operations-first: dashboards and transactional screens, not chat-first navigation
- Clear status, ownership, due dates, and next actions
- Fast data entry for operators and storekeepers
- Strong search by item, work order, batch, supplier, and customer
- Drill-down from KPI to source records
- Simple defaults with configurable advanced options
- Consistent approval, exception, and audit patterns
- Show warnings without hiding the underlying data
- AI is an assistant, not an autonomous authority over critical transactions
- Separate general AI conversations from company ERP data and workflows

---

## 21. Decisions to make before implementation

- Target manufacturing segment (e.g., furniture, textile, food, metal, plastics)
- Typical customer size and number of plants
- Make-to-stock, make-to-order, batch, discrete, or process manufacturing needs
- Required accounting and compliance scope
- Whether the product replaces an existing ERP or digitizes spreadsheets
- Required languages, units, currencies, and tax jurisdictions
- Connectivity and shop-floor device constraints
- Required integrations and system-of-record boundaries
- Hosting, data residency, retention, and security expectations
- Commercial packaging: per company, plant, user, module, or usage

---

## Summary

Unified ERP should be a dedicated manufacturing operations system with production, inventory, procurement, quality, maintenance, sales/dispatch, and costing as connected workflows. Its AI layer should answer questions from authorized factory data, help draft and explain work, and leave consequential approvals and transactions under human control. Start with one manufacturing segment and one end-to-end workflow, then expand based on real customer needs.

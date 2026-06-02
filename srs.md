## Software Requirements Specification (SRS)  
### Multi-Tenant, White-Label POS System with ZATCA Compliance  

**Version:** 1.0  
**Date:** [Current Date]  

---

## 1. Introduction

### 1.1 Purpose
This document defines the requirements for a **Modern Point of Sale (POS) System** that supports four languages (Arabic, English, Hindi, Urdu), complies with **ZATCA (Saudi Zakat, Tax and Customs Authority)** e-invoicing rules, and follows a **three-tier distribution model**:
- **Master Admin** (platform owner)
- **Agents (Distributors)** – buy client packages (10, 50, 100 clients)
- **Clients (End Merchants)** – use the POS via web or mobile app

Agents can **white-label** the system (logo, theme, feature selection) for their clients. Clients see only the agent’s brand.

### 1.2 Scope
- One backend server + database
- Four interfaces:
  1. Master Dashboard (web)
  2. Agent Dashboard (web)
  3. Client Dashboard (web + mobile app)
  4. POS terminal (web-based, runs on any device)
- ZATCA Phase 2 compliance (including cryptographic stamping, QR code)
- Multi-language support (RTL for Arabic/Urdu, LTR for English/Hindi)
- Subscription management & automated revenue split

### 1.3 Definitions & Acronyms
| Term | Definition |
|------|-------------|
| **ZATCA** | Saudi Zakat, Tax and Customs Authority |
| **White-label** | Client sees agent’s branding, not the original platform owner |
| **Agent** | Reseller who buys client slots and manages sub‑clients |
| **Client** | Merchant using the POS to sell goods/services |
| **Package** | Prepaid block of client licenses (10, 50, or 100) |
| **CSID** | ZATCA Certificate Signing Request ID for e‑invoicing |

---

## 2. Overall Description

### 2.1 Business Model
- **Master** sets the price per client license (e.g., $10/month).
- **Agents** buy packages of client licenses at wholesale price.
- Agents sell to clients at their own retail price (agent keeps the margin).
- Agent pays Master monthly for active clients (or prepaid package model).
- Master dashboard tracks all agents, clients, and revenue.

### 2.2 User Roles & Relationships
```
Master (Platform Owner)
   │
   ├── Agent A (buys 50-client package)
   │      ├── Client A1 (sees Agent A’s logo/theme)
   │      └── Client A2 (sees Agent A’s logo/theme)
   │
   └── Agent B (buys 10-client package)
          └── Client B1 (sees Agent B’s logo/theme)
```

### 2.3 Key Features per Dashboard

#### Master Dashboard
- Manage agents (create, suspend, delete)
- Define packages (10 / 50 / 100 clients) and pricing
- View all agents, their active client count, revenue
- Configure global ZATCA settings (production/test mode, tax rates)
- Monitor system health, logs, and usage

#### Agent Dashboard
- White-labeling: upload logo, set primary/secondary colors (hex), favicon
- Feature toggles for clients (enable/disable per client or as default):
  - Inventory management
  - Employee roles
  - Discounts & coupons
  - Customer loyalty program
  - ZATCA e‑invoicing (optional per client)
- Manage clients: create, suspend, delete, reset password
- View client subscription status & usage
- Agent’s own payment settings:
  - Stripe / PayPal / bank transfer details (for receiving client payments)
  - Default recurring fee for clients (e.g., $15/month)
- Reports: total active clients, monthly revenue, commission due to Master

#### Client Dashboard (Web + Mobile)
- **Login** using credentials provided by agent
- Upon login, the interface displays **agent’s logo & theme** (fetched from backend).
- **POS terminal** (see section 3.4)
- Sales reports, inventory, customer list (depending on agent-enabled features)
- Subscription details: next billing date, plan name, payment history
- Multi-language toggle (Arabic/English/Hindi/Urdu) – UI text switches instantly.

#### Mobile App (Generic – iOS & Android)
- Single binary for all clients.
- On launch → login screen (email/password).
- After successful login:
  - App requests `GET /api/client/branding` → receives logo URL, theme colors.
  - App applies theme and shows agent’s logo.
  - All screens (POS, reports, settings) reflect agent’s brand.
- Offline mode: POS can store up to 500 transactions and sync when online.

### 2.4 Operating Environment
- **Backend:** Node.js (NestJS) / Laravel / Django + PostgreSQL + Redis
- **Frontend (web):** React / Vue.js (with RTL support)
- **Mobile:** Flutter or React Native (single codebase)
- **POS:** Web-based, responsive (works on touchscreen, tablet, PC)
- **ZATCA integration:** REST API + SDK for cryptographic stamping (e.g., `fatoora` SDK)

### 2.5 Constraints
- Must support **right-to-left (RTL)** UI for Arabic and Urdu.
- Must pass ZATCA Phase 2 compliance (onboarding + e‑invoicing).
- Mobile app must work offline with local SQLite.
- Agent cannot access Master’s financial data; Client cannot see other clients.

---

## 3. System Features & Requirements

### 3.1 Agent Management (Master Dashboard)
| ID | Requirement |
|----|-------------|
| MA-01 | Master can create an agent with company name, email, phone, and assigned package (10/50/100). |
| MA-02 | System deducts one client slot when agent creates a new client. |
| MA-03 | Master sees real‑time used vs. remaining slots per agent. |
| MA-04 | Master can add more slots to an agent (refill package). |
| MA-05 | Master sets global tax rates (VAT, ZATCA fees) that agents inherit (agents cannot override tax rates). |

### 3.2 White-Labeling & Feature Toggles (Agent Dashboard)
| ID | Requirement |
|----|-------------|
| AG-01 | Agent uploads logo (PNG/SVG) – stored in cloud bucket. |
| AG-02 | Agent chooses primary color, secondary color, button radius, font family. |
| AG-03 | Agent decides which features are available to each client (e.g., enable/disable “Inventory” for a specific client). |
| AG-04 | When a client logs into web or mobile, the UI loads agent’s theme dynamically. |

### 3.3 Client Onboarding & Subscription
| ID | Requirement |
|----|-------------|
| CL-01 | Agent creates client → system generates email with login link and temporary password. |
| CL-02 | Client picks language during first login. |
| CL-03 | Agent sets client’s subscription fee (monthly/yearly). |
| CL-04 | Client can view and pay subscription via agent’s payment gateway (Stripe/PayPal). |
| CL-05 | If client fails to pay, agent can suspend client access. |

### 3.4 POS Terminal (Web + Mobile)
| ID | Requirement |
|----|-------------|
| POS-01 | Cart management: add items, quantity, discounts, taxes. |
| POS-02 | Multiple payment methods: cash, card, bank transfer, loyalty points. |
| POS-03 | Print ZATCA-compliant invoice (thermal or A4) with embedded QR code. |
| POS-04 | Send invoice via email/SMS (if client enables customer management). |
| POS-05 | Offline mode (mobile only): transactions stored locally, synced when online. |
| POS-06 | Product search by barcode (camera) or name. |
| POS-07 | Return/refund transactions with ZATCA credit note. |

### 3.5 ZATCA Compliance (Critical)
| ID | Requirement |
|----|-------------|
| ZA-01 | Onboarding: System generates CSR, submits to ZATCA, stores production certificate & secret. |
| ZA-02 | Each invoice includes: seller name, VAT number, timestamp, invoice total, VAT total, cryptographic stamp (generated by SDK). |
| ZA-03 | QR code contains mandatory ZATCA fields (TLV encoding). |
| ZA-04 | All invoices are sequenced per client (unique invoice counter) and hashed to prevent tampering. |
| ZA-05 | System retains invoice history for 6 years (regulatory requirement). |
| ZA-06 | Sandbox environment for testing (ZATCA simulation mode) – available to agents during onboarding. |

### 3.6 Multi-Language Support
| ID | Requirement |
|----|-------------|
| L10N-01 | UI strings stored in JSON locale files (ar, en, hi, ur). |
| L10N-02 | RTL layout for Arabic and Urdu (mirrored UI, right-aligned text). |
| L10N-03 | Number formatting (Arabic-Indic digits for ar/ur, Western digits for en/hi). |
| L10N-04 | Date/time locale-appropriate (Hijri calendar optional, but Gregorian is required). |
| L10N-05 | Agent can set a default language for clients, but client can override. |

---

## 4. External Interface Requirements

### 4.1 User Interfaces
- **Master & Agent Dashboards:** Web-based, responsive (Bootstrap/Tailwind + RTL).
- **Client Web App:** Identical to POS + reports, runs on any modern browser.
- **Mobile App (Client):** Native-like (Flutter) with camera for barcode, offline storage.

### 4.2 Hardware Interfaces
- **Receipt printer:** Supports ESC/POS or thermal printer via Bluetooth (mobile) or network (web).
- **Barcode scanner:** USB or camera-based.

### 4.3 Software Interfaces
- **Payment gateways:** Stripe, PayPal, or local payment (HyperPay, PayTabs) – integrated at agent level.
- **ZATCA SDK:** Use official `fatoora` SDK (Node.js/PHP/Python) for cryptographic stamping.
- **Email/SMS:** SendGrid, Twilio (for invoices and notifications).
- **Cloud storage:** AWS S3 or equivalent for logos, certificates.

### 4.4 Communication Interfaces
- **REST API (JSON)** for web and mobile clients.
- **WebSockets** for real-time sync (offline transaction upload).
- **HTTPS only** with TLS 1.2+.

---

## 5. Non-Functional Requirements

### 5.1 Performance
- POS transaction processing ≤ 1 second (online).
- Mobile offline sync: replayed within 5 seconds after reconnection.
- Dashboard loads under 2 seconds for up to 10,000 clients.

### 5.2 Security
- Passwords hashed with bcrypt.
- JWT with short-lived access tokens + refresh tokens.
- Row-level security: client can only access own data; agent can access only their clients.
- Audit log for all invoice modifications (immutable ledger).
- ZATCA keys stored encrypted (AES-256) – never in logs.

### 5.3 Scalability
- Horizontal scaling: stateless backend, shared database (PostgreSQL).
- Redis for caching agent theme settings (reduces DB load).
- Support for 100+ agents, each with 100 clients (10,000 total clients initially).

### 5.4 Availability
- 99.9% uptime for core POS APIs.
- Offline mode ensures POS never stops working even if internet fails (mobile).

### 5.5 Multi-Tenancy & White-Labeling
- Every API request includes `X-Tenant-ID` (agent ID for client requests).
- Backend returns dynamic CSS variables and logo URL based on tenant.
- No hardcoded brand references in frontend.

---

## 6. Database Design Overview (Key Entities)

```
agents (
  id, company_name, email, package_type (10/50/100), used_slots, 
  logo_url, primary_color, secondary_color, created_at
)

agent_features (
  id, agent_id, feature_name (inventory, coupons, loyalty), is_enabled_default
)

clients (
  id, agent_id, name, email, subscription_fee, is_active, 
  zatca_certificate, invoice_counter, language_preference
)

transactions (
  id, client_id, invoice_number, zatca_qr, total_amount, vat_amount, 
  transaction_date, pos_device_id, is_synced_offline
)

packages (
  id, name (10/50/100), wholesale_price, retail_price (suggested)
)
```

---

## 7. ZATCA Specific Implementation Notes

- **Onboarding Flow per Client:**
  1. Agent initiates “Enable ZATCA” for client.
  2. System generates a private key and CSR.
  3. Calls ZATCA API (sandbox or production) to get certificate.
  4. Stores certificate + secret in client record (encrypted).
- **Invoice Generation:**
  - Before saving invoice, call `Fatoora.generateHash(invoice_data, private_key)`.
  - Encode TLV (Tag-Length-Value) for QR code.
  - Save invoice + hash + QR string.
- **Phase 2 requirement:** All invoices must be reported to ZATCA within 24 hours (use background job).

---

## 8. Sample User Flows

### Agent creates a client:
1. Agent logs into Agent Dashboard.
2. Clicks “Add Client”, fills name/email.
3. Selects which features (e.g., inventory + discounts) this client gets.
4. System deducts 1 from remaining slots.
5. Client receives email: “Your POS account is ready – login at [agent‑subdomain].example.com”.
6. Client logs in → sees agent’s logo, theme, and only enabled features.

### Client makes a sale (online):
1. Cashier adds items to cart.
2. Clicks “Pay” → selects payment method.
3. Backend creates ZATCA-compliant invoice, prints receipt.
4. Inventory decreases (if enabled).
5. Transaction saved to database.

### Mobile app offline sale:
1. Phone loses internet.
2. App stores sale in SQLite with status `pending_sync`.
3. When internet returns, app posts all pending transactions.
4. Backend processes each, returns ZATCA QR codes (app can print later).

---

## 9. Assumptions & Dependencies

- **Assumptions:**
  - Agents have their own payment gateway accounts (Stripe/PayPal) – not provided by Master.
  - ZATCA production certificates require a valid Saudi VAT registration for each client.
  - Master is responsible for providing ZATCA sandbox credentials to agents.
- **Dependencies:**
  - ZATCA API availability & SDK updates.
  - Mobile app stores (Apple, Google) approval for a generic “white-label POS” app.

---

## 10. Appendices

### A. Glossary of ZATCA Terms
- **CSID:** Certificate Signing Request ID
- **PIT:** Phase 2 (mandatory since Dec 4, 2021)
- **TLV:** Tag-Length-Value encoding for QR code
- **ECC:** Elliptic Curve Cryptography used for stamping

### B. Sample ZATCA QR Code Payload (TLV)
```
Tag 1 (Seller Name)      – value
Tag 2 (VAT Number)       – value
Tag 3 (Timestamp)        – value
Tag 4 (Invoice Total)    – value
Tag 5 (VAT Total)        – value
Tag 6 (Cryptographic Hash) – value
```

---

**This SRS serves as the blueprint for development, QA, and deployment. Any changes must be approved by the system architect and Master Admin.**
===========================
addtionally :
to full production-ready status:

🔴 Critical (Must-Have for Production)
Security & Auth
Granular Role Permissions — Fine-grained permissions per staff member (e.g., can process refunds, can view reports, can edit products)
Session Management — Token refresh, forced logout, session timeout
Rate Limiting — API rate limiting to prevent abuse
Input Validation & Sanitization — Server-side validation on all endpoints (beyond basic ORM)
CORS Lockdown — Restrict origins to production domains only
Data Integrity & Reliability
Database Migrations — Proper migration system (Alembic) instead of raw SQL creates
Transaction Atomicity — Ensure POS sales, inventory deductions, and financial records are atomic (rollback on failure)
Data Backup & Recovery — Automated database backups with point-in-time recovery
Audit Trail Completeness — Every data mutation logged (currently partial)
ZATCA Compliance (Full)
E-Invoice Integration API — Connect to ZATCA’s actual Fatoora portal for invoice reporting/clearance (currently only generates QR locally)
Cryptographic Stamp (CSID) — Digital signing of invoices as required by Phase 2
Invoice Sequential Numbering — Tamper-proof sequential invoice counter
🟠 Important (Expected in Production)
Operations & Monitoring
Error Tracking — Sentry or similar for frontend + backend error monitoring
Health Checks & Uptime Monitoring — Automated alerts when services go down
Logging Infrastructure — Structured logging with log aggregation (not just local files)
Performance Monitoring — API response time tracking, slow query detection
Business Features
PDF Receipt/Invoice Export — Generate proper PDF invoices (currently CSV only)
Email Notifications — Send receipts to customers, alerts to managers
Low Stock Alerts — Automated notifications when inventory drops below threshold
Supplier & Purchase Orders — Track inbound stock, cost of goods
Shift/Cash Drawer Management — Opening/closing cash counts, shift reports
Payment Method Breakdown — Track cash vs card vs wallet per transaction
Multi-branch Support — Clients with multiple store locations
User Experience
User Profile & Settings Page — Change password, preferences, notification settings
Bulk Import/Export — CSV upload for products, customers (onboarding large catalogs)
Search & Filtering — Global search across products, customers, transactions
Pagination — All list views need proper server-side pagination (currently loading all)
🟡 Nice-to-Have (Competitive Edge)
Offline POS Mode — Service worker + IndexedDB for sales when internet drops, sync when back
Loyalty/Rewards Program — Points system for repeat customers
Customer-Facing Display — Second screen showing cart total to customer
Receipt Template Customization — Per-agent/client receipt branding
currency — SAR only (Saudi Arabian Riyal)
Thermal Printer Integration — Direct printing via WebUSB/Bluetooth
Mobile-Responsive POS — Tablet-optimized POS layout
API Rate Plans — Per-agent API usage limits tied to their package
White-label Mobile App — React Native companion app per agent
Advanced Analytics — AI-powered sales forecasting, trend detection
Webhook System — Notify external systems on events (sale completed, stock low)
📊 Summary
Category	Items	Effort
🔴 Critical	12 items	~2-3 weeks
🟠 Important	15 items	~3-4 weeks
🟡 Nice-to-Have	10 items	~4-6 weeks
Top 5 priorities I’d recommend tackling first:

ZATCA Phase 2 compliance (legal requirement in Saudi Arabia)
PDF invoice generation
Server-side pagination
Email notifications
Error tracking (Sentry)

also make sure that whatever the system language was receipts and qoutations are always in arabic and following the standards of ZATCA
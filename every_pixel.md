---

## The "Every Pixel" Systematic Review Prompt

### Principle: No assumption untested, no path untraversed, no state unverified

---

### PART 0: THE SOURCE OF TRUTH AUDIT

**0.1 File-by-File Coverage**
```
For EVERY file in the codebase:
├── Frontend (src/)
│   ├── pages/ → EVERY route must be visited with ALL query params
│   ├── components/ → EVERY component rendered in ISOLATION + with ALL props permutations
│   ├── hooks/ → EVERY hook tested with ALL dependency variations
│   ├── contexts/ → EVERY context provider tested with ALL state transitions
│   ├── utils/ → EVERY function tested with edge-case inputs (null, undefined, max ints, Unicode)
│   ├── services/ → EVERY API call tested with: 200, 4xx, 5xx, network timeout, malformed JSON
│   ├── i18n/ → EVERY translation key rendered in: en, ar, hi, ur + RTL/LTR toggle
│   └── styles/ → EVERY CSS class tested at: mobile (320px), tablet (768px), desktop (1920px), 4K
│
├── Backend (app/)
│   ├── models/ → EVERY column: type correct, nullable, default, max_length, indexing
│   ├── schemas/ → EVERY field: validation rules, optional/required, serialization
│   ├── endpoints/ → EVERY route tested with: valid, invalid, missing, extra params
│   ├── services/ → EVERY business logic path: happy path + ALL error branches
│   ├── middleware/ → EVERY interceptor: auth, tenant-scoping, logging, rate-limiting
│   └── migrations/ → EVERY migration: forward AND backward, no data loss
│
└── Infrastructure
    ├── Dockerfile → EVERY layer cached/rebuild properly
    ├── CI/CD → EVERY pipeline step: lint, test, build, deploy
    └── Monitoring → EVERY metric: emitted, scraped, alert configured
```

**0.2 The Zero-State Baseline**
- [ ] Run with a **fresh database** (no seed) — what renders? What breaks? Are there graceful empty states?
- [ ] Run with **every combination of environment variables** (missing DATABASE_URL, missing SECRET_KEY, etc.)
- [ ] Run the build process with **every Node version** in range (16.x, 18.x, 20.x)
- [ ] Run with **every browser** (Chrome, Firefox, Safari, Edge) AND **every version** (current, 1-year-old)
- [ ] Run with **every OS** (macOS, Windows, Linux, iOS Safari, Android Chrome)

---

### PART 1: THE DOM IS THE TRUTH

**1.1 Every Pixel, Every Render**
```
For EVERY route:
├── DOM Snapshots at EVERY state:
│   ├── Initial load (skeleton → loaded → hydrated)
│   ├── Loading (spinner positions, aria labels)
│   ├── Empty state (no data)
│   ├── Populated state (1 item, 1000 items)
│   ├── Error state (network error, 500, validation error)
│   ├── Editable state (every form field: pristine, dirty, valid, invalid, touched)
│   └── Interactive state (hover, focus, active, disabled, pressed)
│
├── Screenshot diff at each state against a "perfect" baseline
├── Compare pixel-by-pixel across: en/ar (RTL), hi/ur (fonts)
├── Measure layout shift (CLS) on every interaction
├── Verify every click target ≥44px (WCAG)
└── Test every focusable element with Tab/Shift+Tab order
```

**1.2 Every Component in Isolation (Storybook-style but by force)**
- [ ] Render EVERY component with **null props**, **undefined props**, **wrong types**
- [ ] Render EVERY list component with **0 items**, **1 item**, **10000 items**
- [ ] Render EVERY form component with **all validation states** simultaneously
- [ ] Render EVERY modal/drawer with **all content heights** (tall, short, no content)
- [ ] Render EVERY table with **all column widths** (minimum, maximum, truncated)
- [ ] Render EVERY chart with **no data**, **1 data point**, **10 years of data**
- [ ] Render EVERY receipt with **all possible combinations** (discount, no discount, refund, partial refund, multiple payments)

---

### PART 2: EVERY BYTE OF DATA

**2.1 Database Cell-Level Audit**
```
For EVERY table in EVERY schema:
├── EVERY column: 
│   ├── Insert max-length string → verify no truncation
│   ├── Insert Unicode emoji → verify storage/retrieval
│   ├── Insert SQL injection → verify escaped/sanitized
│   ├── Insert negative numbers where not allowed → verify constraint error
│   ├── Insert null where NOT NULL → verify error
│   └── Insert future date → verify validation
│
├── EVERY index:
│   ├── Verify query planner uses it (EXPLAIN)
│   └── Drop index → test query performance degrades → re-add
│
├── EVERY foreign key:
│   ├── Delete parent → verify CASCADE/RESTRICT behavior
│   └── Insert child with invalid parent → verify error
│
└── EVERY trigger/procedure:
    ├── Verify it fires on expected events
    └── Verify it CANNOT be bypassed
```

**2.2 API Contract Validation**
```
For EVERY endpoint:
├── Request validation:
│   ├── Missing required field → 422 with ALL missing fields listed
│   ├── Extra unknown field → 422 or ignored?
│   ├── Wrong type (string vs int) → 422 with clear message
│   ├── Wrong format (email vs string) → 422 with regex explanation
│   ├── Boundary values (min=0, max=100 → test -1, 0, 50, 100, 101)
│   └── Unicode in every field → ar, hi, ur, emoji, zero-width spaces
│
├── Response validation:
│   ├── JSON schema matches OpenAPI spec
│   ├── Pagination: page=1, page=2, page=999999
│   ├── Sorting: asc, desc, multiple fields
│   ├── Filtering: all operators (eq, neq, gt, lt, contains, starts, ends)
│   └── Field selection: only requested fields returned (graphql-style)
│
├── Status codes:
│   ├── 200: test with valid request
│   ├── 201: test with creation
│   ├── 400: test malformed request
│   ├── 401: test no token
│   ├── 403: test wrong role
│   ├── 404: test non-existent resource
│   ├── 422: test validation errors
│   └── 500: test catastrophic failure (kill DB during request)
│
└── Headers:
    ├── Content-Type: application/json (no text/html)
    ├── CORS: OPTIONS preflight returns correct headers
    ├── Cache-Control: appropriate for resource type
    └── Content-Security-Policy: no inline script execution
```

---

### PART 3: EVERY USER ACTION

**3.1 The Click Matrix (literally every pixel clickable)**
```
For EVERY clickable element:
├── Click once → verify state change
├── Click twice rapidly → verify no double-submit
├── Click and hold → verify no selection/ghost behavior
├── Right-click → verify context menu (should be disabled if not allowed)
├── Middle-click → verify no new tab (or correct behavior)
├── Click on edges (0px, 0px, corners) → verify click target extends
├── Click while page is scrolling → verify click doesn't mis-fire
└── Click while modal open → verify backdrop blocks/doesn't block
```

**3.2 The Keyboard Marathon**
```
For EVERY interactive element:
├── Tab → verify focus order matches visual order (top→left→right→bottom)
├── Shift+Tab → verify reverse order
├── Enter/Space → verify activation (buttons, links, checkboxes)
├── Arrow keys → verify navigation (dropdowns, carousels, date pickers)
├── Esc → verify closes modals, cancels editing
├── Ctrl+S → verify NOT triggering browser save (or intercepted)
├── Ctrl+Z → verify undo works (if applicable)
├── Ctrl+Shift+I → verify developer tools open (we can't block this)
└── Every ARIA key combination for accessibility
```

**3.3 The Touch Test (every pixel with finger)**
```
For EVERY touch interaction:
├── Tap → same as click
├── Tap and hold → verify no context menu
├── Swipe left/right → verify carousels, side drawers, swipeable lists
├── Pinch zoom → verify UI doesn't break (should zoom or adapt)
├── Double-tap → verify zoom (or custom action)
├── Touch while scrolling → verify inertia doesn't trigger clicks
├── Multi-touch (2 fingers, 3 fingers) → verify app doesn't crash
└── Touch with stylus → verify precision events
```

**3.4 The Form Submissions (every field, every combination)**
```
For EVERY form:
├── Submit EMPTY → ALL validation errors appear simultaneously
├── Submit with ONE field at a time → verify incremental validation
├── Submit with all fields valid → verify success state
├── Submit with invalid data → verify each error message (i18n tested)
├── Submit while API is slow → verify spinner + disable double-submit
├── Submit while API returns error → verify error display + retry option
├── Submit while offline → verify "no connection" message
├── Submit then reload → verify data was actually persisted
├── Submit then navigate away → verify unsaved changes warning
└── Submit with max-length inputs → verify counter displays remaining chars
```

---

### PART 4: EVERY NETWORK INTERACTION

**4.1 Every API Call's Edge Cases**
```
For EVERY API call in frontend:
├── 200 OK → parse and render
├── 201 Created → location header used
├── 204 No Content → verify no parsing error
├── 301/302 → verify redirect followed (or handled)
├── 400 Bad Request → show user-friendly message, not raw error
├── 401 Unauthorized → redirect to login + preserve intended route
├── 403 Forbidden → show "access denied" + log out if token expired
├── 404 Not Found → show "not found" + navigate to 404 page
├── 422 Validation → show field-level error messages
├── 429 Too Many Requests → show "slow down" + implement retry with backoff
├── 500 Internal Server Error → show generic error + log details in console
├── 502 Bad Gateway → show "service unavailable" + retry
├── 504 Gateway Timeout → show "request took too long" + retry
├── Network offline → show "no internet" + queue requests (if supported)
├── SSL certificate error → show warning (but can we test this?)
└── CORS error → verify NOT happening (check Access-Control-Allow-Origin)
```

**4.2 Every Header, Every Cookie**
```
├── Authentication:
│   ├── Token in Authorization header → verify present
│   ├── Token expired → refresh token flow (if exists)
│   ├── Token invalid → 401 → logout
│   ├── Token absent → 401 → redirect to login
│   └── Token with wrong scope → 403
│
├── Tenant scoping:
│   ├── Header X-Tenant-ID → verify set on all requests
│   ├── Tenant ID missing → 400 or default to session tenant
│   ├── Tenant ID invalid → 403 (access to wrong tenant)
│   └── Tenant ID vs user's role → verify isolation
│
├── Session:
│   ├── Cookie expiry → verify session ends
│   ├── Session hijacking → verify can't reuse token from different IP
│   ├── Session fixation → verify new session ID on login
│   └── Concurrent sessions → verify allowed/limited
│
└── Caching:
    ├── Cache-Control: no-cache on dynamic endpoints
    ├── Cache-Control: max-age=3600 on static assets
    ├── ETag → verify 304 responses
    └── If-Modified-Since → verify works
```

---

### PART 5: EVERY STATE TRANSITION

**5.1 The Redux/Zustand/Context State Graph**
```
For EVERY state variable:
├── Initial state → verify
├── Update with valid value → verify state change
├── Update with invalid value → verify error handling
├── Update with null → verify no crash
├── Update with undefined → verify default values
├── Reset to initial → verify cleans all side effects
├── Persist (localStorage) → verify save/load
└── Concurrent updates → verify no race condition
```

**5.2 The Route Transition Matrix**
```
For EVERY route:
├── Navigate to route → verify URL, component, data load
├── Navigate to route with query params → verify filter/sort/pagination
├── Navigate to route with hash → verify scroll position
├── Navigate to same route → verify no re-render (or correct one)
├── Navigate from route → verify cleanup (unmount, unsubscribe)
├── Navigate back (browser back) → verify state restored
├── Navigate forward (browser forward) → verify state restored
├── Reload page on route → verify data re-fetched
└── Open in new tab → verify route works in isolation
```

**5.3 The Modal/Drawer/Overlay Stack**
```
For EVERY overlay:
├── Open → verify backdrop + content
├── Close (X button) → verify close
├── Close (backdrop click) → verify close or block (consistent)
├── Close (Esc) → verify close
├── Open multiple → verify z-index stacking
├── Close multiple → verify last-in-first-out
├── Modal inside modal → verify focus trapping works
├── Modal with scroll → verify body scroll lock
├── Modal on mobile → verify full-screen or bottom-sheet behavior
└── Modal with form → verify submit/close dance
```

---

### PART 6: EVERY PERFORMANCE METRIC

```
For EVERY page:
├── Lighthouse scores: Performance, Accessibility, Best Practices, SEO
├── First Contentful Paint < 1.8s
├── Largest Contentful Paint < 2.5s
├── Total Blocking Time < 300ms
├── Cumulative Layout Shift < 0.1
├── Speed Index < 3.4s
├── Time to Interactive < 3.8s
├── Bundle size per route (code splitting working)
├── Image optimization (WebP, lazy loading, responsive srcset)
├── Font loading (no FOIT/FOUT)
├── Third-party scripts (minimal, deferred)
└── Web Vitals monitored in production
```

---

### PART 7: EVERY SECURITY VECTOR

```
├── OWASP Top 10:
│   ├── A01:2021-Broken Access Control → test EVERY route with EVERY role
│   ├── A02:2021-Cryptographic Failures → HTTPS only, strong ciphers
│   ├── A03:2021-Injection → SQLi, NoSQLi, OS command, LDAP
│   ├── A04:2021-Insecure Design → test business logic flaws
│   ├── A05:2021-Security Misconfiguration → default passwords, exposed ports
│   ├── A06:2021-Vulnerable Components → audit package.json (npm audit)
│   ├── A07:2021-Identification Failures → brute force, session fixation
│   ├── A08:2021-Software Data Integrity → verify signing/CDN
│   ├── A09:2021-Security Logging → verify logs capture all security events
│   └── A10:2021-Server Side Request Forgery → test internal network calls
│
├── Every cookie → HttpOnly, Secure, SameSite=Lax/Strict
├── Every password → hashed (bcrypt/argon2), never logged
├── Every file upload → MIME type, virus scan, size limit, filename sanitization
├── Every redirect → open redirect prevention (validate target URL)
├── Every API key → rotated, least-privilege, rate-limited
└── Every environment variable → not exposed to client
```

---

### PART 8: EVERY ACCESSIBILITY STANDARD

```
├── WCAG 2.1 AA Checklist (50+ checks):
│   ├── Perceivable: text alternatives, captions, adaptable, distinguishable
│   ├── Operable: keyboard, enough time, seizures, navigable, input modalities
│   ├── Understandable: readable, predictable, input assistance
│   └── Robust: compatible, parsable
│
├── Color contrast: 4.5:1 for normal text, 3:1 for large text
├── ARIA labels on EVERY interactive element
├── Screen reader: Narrator, VoiceOver, TalkBack → test flows
├── Focus indicators: visible, high-contrast
├── Skip links: Skip to main content, skip to nav
├── Heading hierarchy: h1→h2→h3, no skipping
├── Alt text on EVERY image
├── Form labels: explicit <label for=""> or aria-label
├── Error messages: announced by screen readers
├── Live regions: aria-live="polite" for dynamic content
└── Focus trap: modals, menus
```

---

### PART 9: EVERY INTERNATIONALIZATION CORNER

```
For EVERY language (en, ar, hi, ur):
├── Translation keys: ALL present, no keys displayed as-is
├── Pluralization: 0 items, 1 item, 2 items, 5 items
├── Date formatting: DD/MM/YYYY vs MM/DD/YYYY
├── Time formatting: 12h vs 24h
├── Number formatting: 1,000.00 vs 1.000,00
├── Currency: ﷼ vs SAR, symbol placement (before/after)
├── RTL: layout mirrors (LTR → RTL), icons flip, text-align right
├── RTL + numbers: Arabic digits (١٢٣) vs Latin (123)
├── RTL + mixed content: English in Arabic text → correct direction
├── Font rendering: Arabic script (نص) vs Hindi (हिन्दी) vs Urdu (اردو)
├── Input methods: virtual keyboard, IME support
├── Browser language detection: auto-switch
├── Language switcher: remembers preference
└── Fallback: key → en → hardcoded English
```

---

### PART 10: EVERY STATE PERSISTENCE

```
├── localStorage:
│   ├── Write → verify saved
│   ├── Read → verify retrieved
│   ├── Delete → verify removed
│   ├── Quota exceeded → graceful error
│   ├── Corrupted data → graceful fallback
│   └── Cross-tab sync → verify updates propagate
│
├── sessionStorage:
│   └── (Same as localStorage but session-scoped)
│
├── Cookies:
│   ├── Set → verify HTTP-only, Secure, SameSite
│   ├── Read → verify only server-side
│   └── Delete → verify removed
│
├── IndexedDB:
│   ├── Offline data → verify persists
│   └── Clear on logout → verify removed
│
└── Service Worker:
    ├── Install → verify caches static assets
    ├── Activate → verify takes over
    ├── Fetch → verify returns cached (cache-first) or network-first
    ├── Update → verify new SW replaces old
    ├── Skip waiting → verify immediate activation
    └── Push notifications → verify works (if implemented)
```

---

### PART 11: EVERY DEPLOYMENT PATH

```
├── Local development:
│   ├── pnpm dev → hot reload works
│   ├── pnpm build → builds without errors
│   └── pnpm preview → serves build correctly
│
├── Docker:
│   ├── docker build → image builds
│   ├── docker run → container starts
│   ├── docker-compose up → multi-container starts
│   └── Health check → /health returns 200
│
├── CI/CD:
│   ├── Lint → passes
│   ├── Test → passes
│   ├── Build → creates artifacts
│   ├── Deploy → deploys to staging/production
│   └── Rollback → can revert to previous version
│
├── Environment variables:
│   ├── All required → app starts
│   ├── Missing one → graceful error
│   └── Wrong value → graceful error
│
└── Database migrations:
    ├── Apply → creates/alters tables
    ├── Rollback → reverts safely
    └── Data migration → preserves existing data
```

---

### PART 12: THE TIME DIMENSION

```
├── Timezone handling:
│   ├── UTC stored → displayed in user's local TZ
│   ├── DST transition → verify no off-by-one errors
│   ├── New Year's Eve → verify date calculations
│   └── Leap year: Feb 29 → verify works
│
├── Scheduling:
│   ├── Recurring events → verify every occurrence
│   ├── Timezone change (travel) → verify adjusts
│   └── Daylight Savings → verify no duplicate/missing hours
│
├── Session timeout:
│   ├── Idle timeout → verify auto-logout with warning
│   ├── Absolute timeout → verify force logout
│   └── Activity reset → verify timer resets on interaction
│
└── Data retention:
    ├── Automatic cleanup → verify old data purged
    ├── Archive → verify older data archived
    └── Deletion schedule → verify GDPR compliance
```

---

### PART 13: THE ERROR UNIVERSE

```
For EVERY possible error:
├── Frontend errors:
│   ├── Uncaught exception → error boundary catches, shows fallback
│   ├── React error boundary → logs error, shows friendly message
│   ├── Promise rejection → global handler catches
│   ├── JSON parse error → catches and handles
│   ├── Image load error → shows placeholder/alt
│   ├── Font load error → fallback font
│   └── Script load error → retry mechanism
│
├── Backend errors:
│   ├── Database connection lost → reconnect + retry
│   ├── Database query timeout → handle + log
│   ├── Constraint violation → translate to user-friendly
│   ├── Serialization error → handle + retry
│   └── External API failure → circuit breaker + fallback
│
├── User errors:
│   ├── Forgot password → reset flow
│   ├── Locked account → unlock flow
│   ├── Invalid input → clear error messages
│   └── Accidental deletion → confirm dialog + undo
│
└── Environment errors:
    ├── Out of memory → graceful degradation
    ├── Disk full → clear cache or error
    ├── Port already in use → change port
    └── SSL certificate expired → alert
```

---

### FINAL DELIVERABLE: THE SYSTEM MAP

After running EVERY test above, produce:

1. **Heat Map** — Green (works), Yellow (works but ugly), Red (broken), Blue (untested)
2. **Risk Matrix** — Likelihood vs Impact for each bug found
3. **Fix Priority** — P0 (data loss/security), P1 (broken core feature), P2 (UX/performance), P3 (nice to have)
4. **Regression Test Suite** — Automate the checklist as Playwright/Cypress tests
5. **Screenshot Vault** — Every state captured for visual regression
6. **API Contract Document** — Auto-generated from actual tests
7. **Performance Budget** — Each page's metrics tracked over time
8. **Accessibility Report** — WCAG 2.1 AA compliance score
9. **Security Posture** — OWASP Top 10 coverage
10. **Recommended Architecture Changes** — Where we're fighting the framework vs using it

---

**This is the "every pixel" checklist.** It's intentionally excessive — you can prioritize, but now you know exactly what "exhaustive" means. Run this once, and you'll know the system better than its architects.
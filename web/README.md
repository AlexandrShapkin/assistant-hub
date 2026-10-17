# Assistant Hub offline UI preview

**Live static synthetic demo:** https://alexandrshapkin.github.io/assistant-hub/
This is not an authenticated product and cannot access real accounts.

Synthetic demo only, owned by Issue #20 (related to #3). No accounts connected.
All names, accounts, events, proposed drafts and device samples are invented.

From the repository root:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:8765` in a browser. Stop the static server with Ctrl+C.
Serve only `web`, not the repository or a directory containing private data.
ES modules require this local static server; opening the HTML as a file is not
supported. No installation, npm packages, credentials or external data are needed.
The local server only delivers the preview files; this is not a backend service.

The interface starts in Russian. Choose RU or EN in the top bar to switch
languages without reloading the page. Language preference remains in memory only
and resets to Russian on refresh. All 12 fictional events have Russian display
texts; source/account/ID and workflow state remain provider-neutral and stable.

Search event content and service names; combine service, account, status and
priority filters. Sort by recency or importance, select an item and organize it
as done, deferred or for review. Proposed actions demonstrate a local draft,
review request and approval/rejection **simulation**. No review grants permission
or dispatches anything. All changes live in JavaScript memory and reset on refresh.
Reset filters clears filtering only, preserving the current in-memory simulation.

Desktop uses three panes; smaller screens stack the inbox and inspector. On
phones, filters start collapsed behind a visible toggle so the inbox is shown
without scrolling through the whole navigation list. Native buttons and form labels support keyboard
navigation; the detail inspector follows the selected item. Local status changes
are announced to assistive technology. Times are fixed synthetic UTC samples.

There are no external APIs, fonts, images, CDNs, application network requests,
analytics, browser storage, service workers or provider-specific parsing.
Only local static HTML, CSS and ES module resources are loaded. The README anchor
is normal local navigation. A restrictive CSP blocks connection and worker use.

Authentication, login/logout, real APIs and browser access to private data
are NOT implemented. A separate GitHub Pages workflow can publicly serve ONLY
the seven allowlisted static demo files after explicit repository setup. The
public preview is not an authenticated application and cannot access accounts. This preview is independent of the Python
security proofs and core policy; do not enter private data or expose it as a real
application. No real decisions take effect.

Run the dependency-free checks with Node 22:

```sh
node --check web/app.mjs
node --check web/view-model.mjs
node --check web/demo-data.mjs
node --check web/i18n.mjs
node --check web/tests/view-model.test.mjs
node --check web/tests/i18n.test.mjs
node --test web/tests/*.test.mjs
```

Tests cover identity separation, filtering, sorting, immutable transitions,
invalid operation denial, generic services and static checks for prohibited
browser APIs, both locales, locale fallback, and identity preservation. Static checks do not replace browser accessibility/visual review.

# DocAgent Directory Governance Cutover Design

Date: 2026-04-15

## Status

Approved in terminal discussion before writing:

- remove dynamic semantic topic-tree architecture from the main product
- remove high-cost LLM add-ons such as result summaries and classification reports
- keep only the enterprise governance main path:
  - public documents / department documents
  - business-category directories
  - permission-aware global search
  - directory-scoped search
  - upload, ledger, admin
- homepage becomes the global directory page
- homepage keeps a simple smart search box, but backend behavior becomes permission-filtered hybrid retrieval without LLM expansion/reporting
- UI uses a mixed explorer pattern:
  - left side directory tree always visible
  - right side shows directory content by default
  - right side switches to result list after search
- search results are file-first with optional lightweight hit snippets
- company department structure is visible, but inaccessible departments are disabled and marked as locked
- access-request workflow is deferred to a later phase
- this phase priority is:
  - delete obsolete architecture first
  - then rebuild the main path cleanly

This design supersedes the active product role previously played by:

- the semantic topic-tree design
- the topic-tree portions of the earlier enterprise document governance design

## Why A New Design Is Needed

The current repository still mixes two conflicting product models:

1. enterprise governance and permission-aware document access
2. older semantic-topic-tree and LLM-heavy exploratory workflows

That leaves the product in an inconsistent state:

- the information architecture still exposes semantic-topic-tree concepts
- frontend search still carries old auxiliary actions and mental models
- backend still keeps topic-tree endpoints and services as first-class product capabilities
- users cannot clearly understand whether the system is a governed enterprise document cabinet or an LLM experimental retrieval UI

The new design resolves that conflict by making the enterprise directory model the only primary architecture.

## Product Principle

The product is not a semantic discovery tool.

It is a governed enterprise document cabinet with search.

The official organization model is:

- level 1 classification:
  - public documents
  - department documents
- level 2 classification:
  - business categories

Everything else is navigation, permission scope, or search context.

These are not formal classification levels:

- my department
- collaborative departments
- global directory
- admin backend

Those are user views and entry points, not taxonomy.

## Scope

### In Scope

- remove semantic topic-tree from frontend and backend main architecture
- remove high-cost LLM add-on UI and API usage
- rebuild homepage into a global directory page
- rebuild search into:
  - global search on homepage
  - directory-scoped search inside folders
- rebuild navigation and page titles around directory governance
- keep file preview and reader capability
- keep permission-aware document retrieval and document ledger
- keep admin pages for categories, users, and audit
- keep upload flow with explicit governance metadata

### Out Of Scope

- access-request and approval workflow
- automatic permission granting after request
- custom multi-step approval engines
- replacing the underlying hybrid retrieval engine itself
- removing every historical backend utility that might still be useful offline unless it is part of the active product path

## Deletion Plan

### Remove From Product Surface Completely

These should no longer be reachable from the user-facing product:

- semantic topic tree page
- topic-tree panel in search
- topic-tree rebuild actions
- search-page summary drawer
- search-page classification report drawer
- result-summary actions
- any frontend wording that implies semantic-topic-tree is the official classification path

### Remove From Active Backend/API Contract

The following backend features should be deleted, not merely hidden:

- topic-tree API endpoints
- topic-tree service as a product-facing dependency
- topic-tree response schemas used only by that flow
- topic-tree related tests

### Remove Frontend API Helpers For Deleted Features

- `getTopicTree`
- `buildTopicTree`
- summary/report helpers that exist only for deleted flows

### Keep But Reframe

The following capabilities remain, but under the new explorer-style directory model:

- permission-aware workspace retrieval
- document reader
- original file preview/download
- upload with governance metadata
- document ledger / document list
- category, user, audit admin

## Target Information Architecture

### Top Navigation

Primary navigation after cutover:

- global directory
- upload documents
- document ledger
- category admin
- user admin
- audit log

Remove from primary product navigation:

- taxonomy
- semantic topic tree
- summary/report actions

### Homepage: Global Directory

The homepage becomes the system root directory.

It contains:

- a simple smart search box
  - searches all documents visible to the current user
  - backend uses permission-filtered hybrid retrieval
  - no LLM query expansion
  - no LLM summary/report generation
- a left directory tree
  - public documents
  - department documents
    - all departments are visible in the structure
    - accessible departments are clickable
    - inaccessible departments are disabled and show a lock marker
- a right content area
  - before search:
    - shows the selected directory contents
    - child directories first
    - documents second
  - after search:
    - shows file-first search results within current scope
    - can show lightweight hit snippets beneath each file

This should feel closer to Windows Explorer than to an LLM chat workspace.

## Directory Model

### Root

- global
  - public documents
  - department documents

### Department Layer

Under department documents, users first see departments as folders.

Behavior:

- all departments appear in the tree
- no-access departments are visible but disabled
- accessible departments can be entered

### Business Category Layer

Inside each accessible department folder, business categories are rendered as child folders.

Business category is not just a filter chip in this design.
It is the second-level directory.

### Document Layer

Inside a business-category folder, the right panel shows documents.

Available actions:

- search only inside this folder
- sort and filter by metadata
- open file preview
- open text reader

## Search Design

### Global Smart Search

Homepage search behavior:

- input is intentionally simple
- no advanced search controls in the root experience
- backend request is still explicit, but product copy should feel simple
- search scope is all visible documents for the current user
- results are file-first
- snippets are secondary and collapsible

### Directory-Scoped Search

When the user enters a folder, search behaves like searching inside a current filesystem location.

That means:

- current directory becomes the search boundary
- search does not silently jump back to global scope
- breadcrumb and directory title must make the scope obvious

Examples:

- in `Public Documents > HR Policies`, search only scans that category
- in `Department Documents > Finance > Budget Management`, search only scans that business-category folder

### Advanced Search

The current independent search page should be repurposed, not preserved as-is.

It becomes a concrete search page for precise retrieval:

- visible scope selector
- department selector when applicable
- business-category selector
- file type
- time range

This page is for intentional, scoped retrieval.
It is no longer the primary landing experience.

## Frontend Changes

### Pages To Remove

- `TaxonomyPage.vue`

### Components To Remove

- `TopicTreePanel.vue`
- `SummaryDrawer.vue`
- `ClassificationReportDrawer.vue`

### Pages To Rewrite

- `DashboardPage.vue`
  - becomes global directory homepage
- `SearchPage.vue`
  - becomes concrete search page
- `DocumentsPage.vue`
  - stays as governed ledger + upload entry, but vocabulary must align with directory model

### Components To Rewrite

- search toolbar
  - remove topic-tree rebuild
  - remove summary/report actions
  - align terminology to concrete search
- document result list
  - file-first display
  - snippets as supporting evidence only
- file list / document ledger
  - align labels to public/department/business-category model

### App Shell

The shell copy and labels should stop describing the product as a general intelligent workspace.

It should describe:

- enterprise document directory
- governed document cabinet
- public/department directory access

## Backend Changes

### Remove

- topic-tree endpoints under classification/retrieval paths
- topic-tree service from active API composition
- product-facing topic-tree schemas

### Keep

- permission-aware retrieval service
- document reader and file preview
- organization, category, audit, auth, document governance

### Retrieval Contract After Cutover

Core retrieval must accept and honor:

- current user
- visibility scope
- department scope
- business category
- filename
- file type
- date range

But frontend should split this into two product modes:

1. global simple search
2. concrete scoped search

The backend does not need two separate engines if one service can support both via explicit scope parameters.

## Permissions

The directory tree must reflect permissions in a way users can understand:

- public documents folder is always visible to authenticated users
- department structure is visible at organization level
- actual directory entry depends on authorization
- unauthorized departments are locked
- directory content and search results never leak hidden documents

The system must remain server-authoritative.
The frontend tree is informational and navigational only.

## Migration / Cutover

This change should be treated as a hard product cutover, not a compatibility experiment.

Rules:

- remove old routes instead of hiding them behind nav flags
- remove old API helpers instead of leaving dead wrappers
- remove deleted-flow tests and replace them with directory-governance tests
- update page labels and copy in one pass so users do not see mixed language

## Testing Strategy

### Frontend

Add or update tests for:

- homepage global directory rendering
- locked departments shown but not enterable
- global search scoped to all visible content
- folder search scoped to current directory only
- concrete search page advanced filters
- absence of topic-tree, summary, and report actions

### Backend

Add or update tests for:

- deleted topic-tree routes are gone
- retrieval still respects permission scope after UI cutover
- folder-scope query parameters map to the correct retrieval boundaries
- no summary/report-only endpoints remain in active product path if deleted

## Risks

- deleting old architecture will touch many files at once, so route/test cleanup must be deliberate
- some backend semantic/chunking utilities may still be indirectly used by core extraction or retrieval and must not be deleted blindly in this phase
- frontend labels may remain inconsistent if the copy rewrite is not done together with route/component removal

## Implementation Order

Recommended order:

1. delete frontend topic-tree/summary/report surfaces
2. delete backend topic-tree/API surfaces and related tests
3. rebuild homepage into global directory page
4. rebuild concrete search page around scoped retrieval
5. update app shell, ledger, and upload language
6. run full governance verification

## Completion Criteria

This cutover is complete when:

1. no semantic-topic-tree route, panel, API, or action remains in the active product
2. no summary/report add-on action remains in the active product
3. homepage is the global directory page
4. directory navigation follows:
   - root
   - public or department layer
   - business-category folders
   - documents
5. global search works across all visible documents
6. folder search works only inside current directory scope
7. search results are file-first with optional snippets
8. public/department/business-category language is consistent across frontend and backend contracts
9. the product can be understood as a governed document cabinet without any semantic-topic-tree mental model

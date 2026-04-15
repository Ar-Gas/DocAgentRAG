# Enterprise Document Classification And Access Design

## Scope

Design a practical first-phase enterprise document governance system for daily office work.

Goals:

- Replace unstable semantic topic clustering as the primary classification mechanism.
- Introduce a stable document classification and access model based on:
  - fixed top-level document domains
  - business category dictionaries
  - department ownership
  - role-based access constraints
- Add a first-phase login and identity system with internal username/password accounts.
- Add user, department, role, and document visibility models that support real enterprise collaboration.
- Ensure document list, preview, download, and retrieval all enforce access control consistently.
- Add basic audit logging for key user and document actions.

Out of scope:

- Full approval workflow or BPM-style process orchestration.
- Fully custom RBAC editing UI or arbitrary permission graph editing.
- Real LDAP / AD / SSO integration in phase one.
- Replacing current retrieval algorithms beyond adding permission-aware filtering.
- Using LLM or semantic clustering as the authoritative classification source.

## Product Positioning

This design treats the system as a document governance and retrieval platform, not as a pure semantic discovery tool.

Phase-one priorities are:

- stable classification
- predictable access control
- explainable directory structure
- permission-safe retrieval
- operational manageability

The current dynamic semantic topic tree remains useful as an auxiliary browsing or exploratory feature, but it must not define the official document taxonomy or any access rule.

## Information Architecture

### Top-Level Classification

The primary directory is fixed and intentionally shallow.

Top-level domains:

- `公共文档`
- `部门文档`

These two domains are not free-form categories. They are governed by document visibility metadata.

- `公共文档` contains company-wide shared content such as制度, 公告, 模板, 培训资料, 通用知识库.
- `部门文档` contains department-owned or business-owned working documents.

### Secondary Classification

Secondary classification is business-oriented and dictionary-driven.

Each document has one primary business category in phase one.

Business category sources:

- system preset categories, maintained globally
- department extension categories, maintained per department

Recommended preset business categories:

- 制度流程
- 通知公告
- 模板表单
- 会议纪要
- 培训资料
- 知识库
- 财务报销
- 采购供应商
- 合同法务
- 人事招聘
- 项目管理
- 销售客户
- 运营支持
- 质量合规
- IT运维
- 档案资料

### Labels Instead Of Deep Trees

The classification tree should not absorb every dimension.

Additional dimensions should be modeled as labels or filters:

- document type
- department
- status
- confidentiality level
- created time
- owner

Recommended labels:

- document type: 制度, 合同, 报告, 纪要, 表单, 方案, 台账
- status: 草稿, 生效, 废止, 归档
- confidentiality level: 普通, 内部, 受限

## Identity And Organization Model

### Users

Each user has:

- internal username
- password hash
- display name
- status
- primary department
- optional collaborative departments
- one built-in role

Phase one login source is internal account/password only, but the data model should reserve a future external identity field so LDAP / AD / SSO can be added later.

### Departments

Departments form a managed tree with:

- department name
- parent department
- enabled status
- optional manager

### Roles

Phase one uses fixed built-in roles plus small configurable constraints, not full custom RBAC.

Built-in roles:

- `system_admin`
- `department_admin`
- `employee`
- `audit_readonly`

Role meaning:

- system admin manages all users, departments, categories, documents, and audit logs
- department admin manages documents and department categories within authorized departments
- employee uses the workspace and uploads to allowed scopes
- audit readonly can inspect authorized content and audit logs but cannot mutate business data

## Authorization Model

### Core Principle

Document access is determined by department membership and role together.

The permission order is:

1. authentication
2. document visibility scope
3. department match
4. role restriction

All backend read and write paths must evaluate permissions server-side. The frontend must never be the authority for access control.

### Document Ownership And Sharing

For department documents, each document has:

- one owner department
- zero or more shared departments

This gives a clear primary owner while still supporting cross-department collaboration.

### Public Document Rules

Public documents are visible to all authenticated users by default.

However, a public document may still carry optional restrictions:

- role restriction
- extra department restriction

This supports company-shared content that is not truly universal.

### Access Evaluation

For a given document:

1. if the current user is `system_admin`, allow
2. if the document scope is `public`
   - allow all authenticated users by default
   - if role restriction exists, user role must match
   - if extra department restriction exists, user must belong to one of those departments
3. if the document scope is `department`
   - user primary or collaborative departments may match owner department
   - or user departments may match shared departments
   - if role restriction exists, role must also match
4. otherwise deny

### Operation Permissions

Recommended phase-one operation rules:

- view / search / preview / download
  - allowed if the document is visible to the user
- upload
  - employee may upload to their primary department and explicitly authorized collaborative departments
  - department admin may upload within managed departments
- edit metadata / change category / change sharing
  - system admin: full
  - department admin: only for documents inside managed department scope
  - employee: no by default in phase one
- delete
  - system admin: full
  - department admin: allowed within managed department scope
  - employee: no by default in phase one

## Data Model

### Core Tables

Phase one should introduce or formalize the following core entities.

#### `users`

Fields:

- `id`
- `username`
- `password_hash`
- `display_name`
- `status`
- `primary_department_id`
- `role_code`
- `last_login_at`
- `external_identity_id` nullable
- `created_at`
- `updated_at`

#### `departments`

Fields:

- `id`
- `name`
- `parent_id`
- `manager_user_id` nullable
- `status`
- `created_at`
- `updated_at`

#### `roles`

Fields:

- `code`
- `name`
- `description`
- `builtin`

#### `user_department_memberships`

Fields:

- `id`
- `user_id`
- `department_id`
- `membership_type` with values `primary` or `collaborative`

#### `business_categories`

Fields:

- `id`
- `name`
- `scope_type` with values `system` or `department`
- `department_id` nullable for system scope
- `status`
- `sort_order`
- `created_by`
- `created_at`
- `updated_at`

#### `documents`

This is an extension of the current document metadata model.

Required added fields:

- `visibility_scope` with values `public` or `department`
- `owner_department_id` nullable for unrestricted public docs
- `business_category_id`
- `role_restriction` nullable
- `is_public_restricted`
- `created_by`
- `updated_by`
- `confidentiality_level`
- `document_status`

#### `document_shared_departments`

Fields:

- `id`
- `document_id`
- `department_id`

#### `audit_logs`

Fields:

- `id`
- `user_id`
- `username_snapshot`
- `department_id`
- `role_code`
- `action_type`
- `target_type`
- `target_id`
- `result`
- `ip_address`
- `metadata_json`
- `created_at`

## Backend Architecture

### New Service Boundaries

The current backend is document-centric and retrieval-centric, but it does not yet contain an identity or access layer.

Phase one should introduce these backend responsibilities:

- `auth service`
  - login
  - session or token validation
  - current user resolution
- `organization service`
  - users
  - departments
  - roles
- `authorization service`
  - document access evaluation
  - operation checks
- `category service`
  - preset and department category management
- `audit service`
  - action logging

### Access Control Integration

Access control must be enforced in service-layer read paths, not only in API routes.

That includes:

- document list
- document detail
- document file preview / download
- document reader
- retrieval workspace search
- retrieval stats
- topic tree or any future corpus browse features

## Retrieval Design

### Permission-Aware Search

The most important retrieval design rule is:

search only over documents the user is allowed to see.

This means filtering happens before retrieval execution, not after result assembly.

Reasons:

- avoids leaking sensitive snippets in hidden results
- avoids LLM summaries using unauthorized content
- keeps ranking, counts, and aggregates consistent with what the user is allowed to access

### Retrieval Pipeline Change

Current retrieval flow should be updated so the search service first computes the visible document set for the current user.

Then:

- vector retrieval searches only permitted document IDs
- keyword retrieval searches only permitted document IDs
- hybrid retrieval merges only permitted candidates
- retrieval stats count only permitted documents
- result summarization uses only permitted result documents

## Frontend Design

### Main Pages

Phase one should expose six primary pages.

#### Login Page

- username/password login
- login failure feedback
- password change entry

#### Document Workspace

Primary employee page.

Contains:

- global search
- top-level domain switch: 公共文档 / 部门文档
- department filter
- business category filter
- document type filter
- time filter
- result list
- document preview / reader panel

#### Upload Page

Upload form includes:

- target scope
- owner department
- shared departments
- business category
- optional role restriction
- optional labels

#### Category Management Page

- system categories for system admin
- department extension categories for department admin
- rename / enable / disable / sort

#### User And Organization Management Page

- user management
- department management
- role viewing
- collaborative department assignment

#### Audit Log Page

- filter by time, user, action, document
- view login, upload, preview, download, delete, permission change, category change events

### Navigation By Role

Employee:

- login
- workspace
- upload

Department admin:

- workspace
- upload
- category management
- scoped organization management
- audit log

System admin:

- workspace
- upload
- category management
- full organization management
- audit log

### Existing Page Integration

Recommended alignment with the current frontend structure:

- current dashboard becomes the employee workspace home
- current documents page becomes permission-aware document management
- current search page stays, but is framed as a workspace retrieval tool
- current taxonomy page is downgraded to auxiliary semantic browsing or hidden from primary navigation
- add:
  - `LoginPage`
  - `CategoryAdminPage`
  - `UserAdminPage`
  - `AuditLogPage`

## API Design

### Authentication

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`

### Organization

- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `GET /api/v1/departments`
- `POST /api/v1/departments`
- `PATCH /api/v1/departments/{department_id}`
- `GET /api/v1/roles`

### Categories

- `GET /api/v1/categories/system`
- `POST /api/v1/categories/system`
- `GET /api/v1/categories/department`
- `POST /api/v1/categories/department`
- `PATCH /api/v1/categories/{category_id}`

### Documents

- `GET /api/v1/documents`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents/{document_id}`
- `PATCH /api/v1/documents/{document_id}`
- `DELETE /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/file`
- `GET /api/v1/documents/{document_id}/reader`

### Retrieval

Existing retrieval APIs remain, but they must derive current user identity and enforce permission-aware document filtering before executing retrieval.

### Audit

- `GET /api/v1/audit-logs`

## Audit Design

Phase one logs the following events:

- login success
- login failure
- upload document
- preview / view document
- download original file
- delete document
- update document category
- update document sharing or visibility

Audit logs should be append-only in phase one.

## Migration Strategy

### Existing Documents

Current documents do not contain complete organization and access metadata.

During migration, assign safe defaults:

- default top-level scope:
  - prefer `department` unless the document is explicitly known to be shared company-wide
- default owner department:
  - infer from existing classification or file path only when reliable
  - otherwise assign to a temporary “待归属” department queue for admin cleanup
- default business category:
  - map from existing classification where possible
  - otherwise assign a temporary “待整理” category

### Semantic Topic Tree

The semantic topic tree should not be removed, but it must be demoted.

Rules:

- it is not the official taxonomy
- it cannot grant or imply access
- it is only computed from documents already visible to the current user if kept in user-facing flows

## Error Handling

### Authentication Errors

- invalid credentials return explicit login failure
- disabled accounts cannot log in
- expired or invalid session returns unauthenticated

### Authorization Errors

- unauthorized reads return not found or permission denied according to endpoint sensitivity
- unauthorized writes return permission denied

### Category Errors

- cannot assign department-only category to unrelated department document
- cannot use disabled categories for new uploads or edits

### Retrieval Errors

- retrieval should still work when topic tree is unavailable
- retrieval summaries must fail safely and never include unauthorized source documents

## Testing Strategy

Required backend tests:

- auth login success / failure
- current user resolution
- department + role permission matrix
- document list filtering by scope
- file preview and download authorization
- permission-aware retrieval filtering
- audit log emission for key actions
- category dictionary scope rules

Required frontend tests:

- login route guard
- role-based navigation visibility
- workspace filtering for public vs department documents
- upload form permission options
- admin page visibility by role

## Risks

- The repository currently has no existing authentication subsystem, so this phase introduces genuinely new platform capabilities rather than extending a small existing module.
- Retrieval changes are cross-cutting because access control must be enforced before vector and summary logic runs.
- Existing documents may not have enough metadata to safely auto-classify ownership without an admin cleanup pass.
- If semantic topic browsing remains exposed without permission-aware scoping, it may leak document existence or themes across departments.

## Phase-One Completion Criteria

The design is complete when:

1. authenticated users can log in and fetch current identity data
2. users only see documents they are allowed to see
3. uploads require explicit scope and category metadata
4. retrieval operates only over visible documents
5. department admins can manage scoped business categories
6. system admins can manage users and departments
7. audit logs record the defined phase-one actions
8. the semantic topic tree is no longer the primary classification path

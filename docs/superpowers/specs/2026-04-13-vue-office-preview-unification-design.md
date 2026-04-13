# Vue Office Preview Unification

## Context

The current document preview modal mixes two different preview models:

1. `@vue-office/pdf` is already used for PDF rendering.
2. Non-PDF formats still fall back to extracted text from the reader API.

That split causes inconsistent behavior. The user has explicitly requested that preview use `vue-office` rendering directly and that the old text-based preview path be removed.

## Goals

1. Use one frontend preview model for supported online document rendering.
2. Render `.pdf`, `.docx`, and `.xlsx` inside the existing preview modal.
3. Remove the old extracted-text preview path for Word and Excel documents.
4. Show a clear unsupported state for formats that are not part of this rendering scope.

## Non-Goals

1. Support legacy Office formats such as `.doc` and `.xls`.
2. Support PowerPoint rendering in this change.
3. Preserve the existing reader-text fallback for unsupported formats.
4. Change backend document storage or file delivery behavior beyond what is already fixed.

## Supported Formats

### Online Preview

- `.pdf` via `@vue-office/pdf`
- `.docx` via `@vue-office/docx`
- `.xlsx` via `@vue-office/excel`

### Not Supported For Online Preview

- `.doc`
- `.xls`
- `.ppt`
- `.pptx`
- `.txt`
- `.md`
- `.csv`
- any other file type outside the supported list

Unsupported formats should display a stable empty state that tells the user online preview is unavailable and they should download the file instead. This rule is intentional and global for the modal: every file type outside `.pdf/.docx/.xlsx` is treated as unsupported in this change.

## Data Contract

`DocumentViewerModal` consumes frontend props, while the page-level callers pass through backend fields.

### Backend To Frontend Mapping

- backend field `file_type` is passed into modal prop `fileType`
- backend field `file_available` is passed into modal prop `fileAvailable`

This mapping already happens at the page layer, for example:

- `:file-type="viewerDoc.file_type"`
- `:file-available="viewerDoc.file_available"`

Planning and tests should use the frontend prop names when targeting `DocumentViewerModal`, and backend field names when targeting API payloads or page integration.

### Normalized File Type

The modal should normalize the preview type using this rule:

1. prefer `fileType` if it is a non-empty extension-like value
2. lowercase the result
3. if `fileType` does not start with `.`, prefix it with `.`
4. if `fileType` is empty or unusable, fall back to the extension parsed from `filename`
5. if neither source yields a known extension, treat the document as unsupported

Examples:

- `fileType=".PDF"` -> normalized `.pdf`
- `fileType="docx"` -> normalized `.docx`
- `fileType=""` and `filename="report.xlsx"` -> normalized `.xlsx`
- `fileType=""` and `filename="README"` -> unsupported

## User Experience

The existing fullscreen preview modal remains the single preview entry point.

### Available File

If the original file exists and the extension is supported:

- show the corresponding `vue-office` component
- keep the file type tag in the header
- keep the “open in new tab” action

### Missing File

If the backend reports `file_available === false`:

- do not attempt rendering
- show the canonical missing-file empty state: `原文件不存在或路径已失效，当前无法预览原文。`
- keep the open-in-new-tab action disabled

### Unsupported Format

If the original file exists but the extension is outside `.pdf/.docx/.xlsx`:

- do not request reader content
- do not show extracted text or slide text
- show an empty state such as “暂不支持在线预览，请下载查看”
- keep the open-in-new-tab action enabled so the user can still open or download the source file

## Frontend Design

### Component Scope

The implementation is centered in `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`.

The modal should move from three branches:

1. PDF component rendering
2. PPT extracted slide text
3. generic text rendering

to three branches:

1. supported `vue-office` rendering
2. missing-file state
3. unsupported-format state

### Preview Selection

The modal should determine a normalized extension from `fileType` and derive booleans for:

- `isPdf`
- `isDocx`
- `isXlsx`
- `isSupportedOfficePreview`
- `isUnsupportedPreview`
- `fileUnavailable`

Only the supported branch should mount a preview renderer.
The missing-file branch should be shared across all file types instead of staying PDF-only.

### Rendering Components

The modal should statically import:

- `@vue-office/pdf`
- `@vue-office/docx`
- `@vue-office/excel`

Each renderer should receive the existing file URL returned by `api.getDocumentFileUrl(documentId)`.

### Renderer API Notes

The implementation plan should use the official `vue-office` README examples as the contract baseline for this repo version:

- `VueOfficePdf` uses `:src`, `@rendered`, and `@error`
- `VueOfficeExcel` uses `:src`, `@rendered`, and `@error`
- `VueOfficeDocx` uses `:src` and `@rendered` in the documented examples

Planning assumption for this change:

1. all three renderers receive the same file URL string through `:src`
2. loading state ends on `@rendered` for all three supported renderers
3. shared render-error UI is mandatory for PDF and Excel through `@error`
4. DOCX uses the same loading UX, and the implementation step must verify whether the installed package version also emits `@error`; if it does, DOCX is wired into the same shared error state, otherwise DOCX keeps the generic open-in-new-tab escape hatch without blocking this feature

This keeps planning concrete without inventing undocumented renderer behavior.

### Loading And Error States

The current PDF-specific loading and error state should be generalized so all supported renderers follow the same pattern:

- show a loading skeleton while the component is rendering
- surface a friendly render error if the component emits an error event

The message can remain generic, for example “预览失败，请在新标签页打开查看。”
This shared error state applies equally to `.pdf`, `.docx`, and `.xlsx`.

### Removed Behavior

The modal should delete the following preview behavior:

- `api.getDocumentReader(...)` calls for modal preview
- `textContent` state
- `slides` state
- `parseSlides(...)`
- PPT text-card rendering
- generic extracted-text rendering

This change intentionally makes the preview modal depend on the original file instead of extracted text.
That includes previously text-previewable non-Office formats such as `.txt`: they move to the unsupported-format state in this change.

## Dependencies

Add these frontend dependencies:

- `@vue-office/docx`
- `@vue-office/excel`

No backend dependency changes are required for this feature.

## Testing Strategy

Update frontend unit tests for `DocumentViewerModal` to cover:

1. `.pdf` renders with the PDF office component and does not call the reader API.
2. `.docx` renders with the DOCX office component and does not call the reader API.
3. `.xlsx` renders with the Excel office component and does not call the reader API.
4. `fileAvailable === false` shows the missing-file empty state and does not mount a renderer.
5. `.pptx` shows the unsupported-format state and does not show extracted text.
6. `.txt` also shows the unsupported-format state and does not show extracted text.

Run:

- `cd frontend/docagent-frontend && npm test`
- `cd frontend/docagent-frontend && npm run build`

## Risks

1. `vue-office` rendering quality depends on the source document and browser runtime. Some documents may still fail to render and must rely on the open-in-new-tab action.
2. Removing extracted-text fallback means unsupported formats lose inline visibility by design.
3. Very large Excel or Word files may render more slowly than the previous text-only fallback.

## Acceptance Criteria

1. Opening a `.pdf` document uses `@vue-office/pdf`.
2. Opening a `.docx` document uses `@vue-office/docx`.
3. Opening a `.xlsx` document uses `@vue-office/excel`.
4. Opening `.doc/.xls/.ppt/.pptx` no longer shows extracted text.
5. Unsupported formats show a clear “download to view” message.
6. Missing files still show the existing missing-file state.
7. The preview modal no longer calls the reader API for document preview.
8. Render errors from `.pdf` and `.xlsx` use one shared fallback message instead of per-format custom behavior.
9. `.txt` and any other non `.pdf/.docx/.xlsx` type show the unsupported-format state instead of inline text.

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
- any other file type outside the supported list

Unsupported formats should display a stable empty state that tells the user online preview is unavailable and they should download the file instead.

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
- show the existing missing-file empty state
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

### Rendering Components

The modal should statically import:

- `@vue-office/pdf`
- `@vue-office/docx`
- `@vue-office/excel`

Each renderer should receive the existing file URL returned by `api.getDocumentFileUrl(documentId)`.

### Loading And Error States

The current PDF-specific loading and error state should be generalized so all supported renderers follow the same pattern:

- show a loading skeleton while the component is rendering
- surface a friendly render error if the component emits an error event

The message can remain generic, for example “预览失败，请在新标签页打开查看。”

### Removed Behavior

The modal should delete the following preview behavior:

- `api.getDocumentReader(...)` calls for modal preview
- `textContent` state
- `slides` state
- `parseSlides(...)`
- PPT text-card rendering
- generic extracted-text rendering

This change intentionally makes the preview modal depend on the original file instead of extracted text.

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

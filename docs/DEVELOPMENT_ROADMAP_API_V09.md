# Development Roadmap API — v0.9

Base: `/api/v1` (same-origin HTTP session and CSRF protection for mutations)

## GET `/listings/{listing_id}/development-roadmap-preview`
Query `include_demo=true` when viewing a public demo listing. Requires existing listing
visibility rights for private/RESERVED listings. Returns read-only deterministic
`phases`, `tasks`, `analysis_basis`, `disclaimer`.

A task includes:
- `key`: stable task key inside generation snapshot
- `phase`: `TAKEOVER|SETUP|VERIFY|RELAUNCH`
- `difficulty`: `EASY|MEDIUM|HARD`
- `assistance`: `SELF|GUIDED|EXPERT`
- `priority`: `LOW|MEDIUM|HIGH`
- `prerequisites`: preceding task keys, no cycles
- `steps`, `success_criteria`: plain-language checklists
- `evidence`: `GENERAL_GUIDANCE|SELLER_DECLARATION|STATIC_FOUND|STATIC_NOT_FOUND|...`
- `source_kind`: `GENERATED`

## GET `/transactions/{transaction_id}/development-roadmap`
Buyer-only, requires `DEMO_COMPLETED`. If plan not yet created:
`{ "created": false, "preview": {"tasks": [...], "phase_definitions": [...] } }`.
Existing plan includes `tasks` with task IDs, `buyer_note`, `status`, `version`,
`waiting_on`, progress summary, `source_changed_since_creation`.

## POST `/transactions/{transaction_id}/development-roadmap`
Human buyer only; creates immutable task blueprint for this demo transaction.
If already created, returns the existing plan without resetting progress. Status 201.

## PATCH `/transactions/{transaction_id}/development-roadmap/tasks/{task_id}`
Human buyer only, JSON body:
```json
{ "status": "IN_PROGRESS", "buyer_note": "설치 확인 중", "expected_version": 1 }
```
`status`: `NOT_STARTED|IN_PROGRESS|BLOCKED|COMPLETED`.
Version conflict 409, unmet prerequisite 409, cross-user access 404.
To reverse a completed prerequisite, first reset dependent tasks.

## POST `/transactions/{transaction_id}/development-roadmap/tasks`
Human buyer only; add up to 30 tasks:
```json
{
  "title": "검색 최적화 점검",
  "detail": "검색 API 결과와 사용성을 확인합니다.",
  "phase": "VERIFY",
  "difficulty": "MEDIUM",
  "assistance": "GUIDED",
  "priority": "MEDIUM",
  "prerequisites": ["LOCAL_RUN"]
}
```
Prerequisite keys must refer to existing tasks. Custom tasks may depend only on
previously created tasks, preventing cycles.

## GET `/transactions/{transaction_id}/development-roadmap/export`
Buyer only, completed demo handover. Downloads UTF-8 BOM Markdown with private
`Cache-Control: private, no-store`.

## Permission and data handling
No external LLM, no seller-code execution, no private source code or GitHub repo name
in response. All work is simulated; do not treat `DEMO_COMPLETED` as paid acquisition.
Browser client must authenticate with session cookies and send CSRF token for writes.

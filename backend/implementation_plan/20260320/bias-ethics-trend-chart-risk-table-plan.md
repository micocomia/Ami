# Bias & Ethics Audit — Trend Line Chart + Color-Coded Risk Table

**Date:** 2026-03-20
**Branch:** sprint-7-bias-ethics-enhancement

## Context

The Analytics Dashboard (`AnalyticsPage.tsx`) displayed learning metrics (progress, skills, sessions, mastery) but had no Bias & Ethics section. The backend already provided a `GET /v1/bias-audit-history/{user_id}` endpoint returning audit entries with `timestamp`, `audit_type`, `overall_risk` (low/medium/high), `flagged_count`, and summary statistics.

This task added two visual components to the Analytics Dashboard:
1. A **trend line chart** showing risk levels over time as audit data accumulates
2. A **Recent Audits table** with color-coded risk levels (green/yellow/red)

## Files Created

| File | Purpose |
|------|---------|
| `frontend-react/src/components/analytics/BiasRiskTrendChart.tsx` | Recharts `LineChart` plotting risk levels over time with color-coded dots |
| `frontend-react/src/components/analytics/RecentAuditsTable.tsx` | Table with color-coded risk badges (green/amber/red pills) |

## Files Modified

| File | Change |
|------|--------|
| `frontend-react/src/components/analytics/index.ts` | Added exports for `BiasRiskTrendChart` and `RecentAuditsTable` |
| `frontend-react/src/api/endpoints/skillGap.ts` | Added `useBiasAuditHistory()` query hook, `getBiasAuditHistoryApi()`, and `BiasAuditEntry`/`BiasAuditHistoryResponse` types |
| `frontend-react/src/pages/AnalyticsPage.tsx` | Added "Bias & Ethics Review" section with KPI cards, trend chart, and recent audits table |

## Implementation Details

### BiasRiskTrendChart.tsx
- Follows the same recharts pattern as `MasteryChart.tsx` (`LineChart` with `ResponsiveContainer`)
- Maps risk levels to numeric values: low=1, medium=2, high=3
- X-axis: timestamps formatted as short dates (e.g., "Mar 20")
- Y-axis: risk level 1–3 with custom tick labels (Low/Medium/High)
- Line color: indigo (`#6366f1`)
- Dots color-coded per risk: green (`#10b981`) for low, amber (`#f59e0b`) for medium, red (`#ef4444`) for high

### RecentAuditsTable.tsx
- Simple HTML table styled with Tailwind, consistent with dashboard card style
- Columns: Date, Audit Type, Risk Level, Flags
- Risk Level column displays a colored badge/pill:
  - `low` — `bg-green-100 text-green-700`
  - `medium` — `bg-amber-100 text-amber-700`
  - `high` — `bg-red-100 text-red-700`
- Shows the 10 most recent entries sorted by timestamp descending
- Audit type displayed in human-readable form (e.g., "Skill Gap Bias" instead of "skill_gap_bias")

### API Hook (skillGap.ts)
- `getBiasAuditHistoryApi(userId, goalId?)` — calls `GET v1/bias-audit-history/{userId}` with optional `goal_id` query param
- `useBiasAuditHistory(userId, goalId?)` — React Query `useQuery` hook with 60s stale time, enabled only when userId is present
- Response types: `BiasAuditEntry` and `BiasAuditHistoryResponse` (entries + summary with risk_distribution and category_counts)

### AnalyticsPage.tsx — New Section
- Added after the Session Time + Mastery grid
- 3 summary KPI cards: Total Audits, Total Flags, Current Risk (color-coded text)
- Below KPIs: 2-column grid with trend chart (left) and recent audits table (right)
- Section gracefully hidden when no audit data exists (`biasHistory.entries.length > 0`)

## Additional Fix

### conftest.py — Python 3.14 / chromadb compatibility
- `backend/tests/conftest.py`: Wrapped `from main import app` in `try/except` inside the `autouse=True` `_bypass_auth` fixture
- Prevents chromadb/pydantic v1 import failures from cascading to all tests
- Pure unit tests now run even when chromadb cannot load

## Verification
- Run `npx tsc --noEmit` in `frontend-react/` — passes with zero errors
- Navigate to the Analytics page in the browser:
  - With no audit data: Bias & Ethics section does not appear
  - With audit data: trend chart renders with colored dots, table shows color-coded risk badges
  - Responsive layout collapses to single column on smaller screens

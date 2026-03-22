# High-Risk Bias Audit Warning Banner

**Date:** 2026-03-20
**Branch:** sprint-7-bias-ethics-enhancement

## Context
Users should be alerted when recent bias audits show repeated high-risk results. Currently the bias audit data is only visible on the Analytics page. A prominent warning banner should surface on both the Dashboard (HomePage) and the Analytics page so users don't miss critical bias issues.

## Definition of "Repeated High-Risk"
Triggered when **3 or more** of the most recent 5 audit entries have `overall_risk === "high"`. This avoids false alarms from a single audit while catching genuine patterns.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend-react/src/components/analytics/HighRiskBanner.tsx` | Reusable dismissible warning banner component |

## Files to Modify

| File | Change |
|------|--------|
| `frontend-react/src/components/analytics/index.ts` | Export `HighRiskBanner` |
| `frontend-react/src/pages/HomePage.tsx` | Add banner above the welcome section |
| `frontend-react/src/pages/AnalyticsPage.tsx` | Add banner above the header |

## Implementation Details

### HighRiskBanner.tsx
- A dismissible red warning banner
- Props: `entries: BiasAuditEntry[]` (the audit entries array from `useBiasAuditHistory`)
- Internal logic: checks if >= 3 of the last 5 entries are `overall_risk === "high"`
- If not triggered, renders `null`
- Styling: red background (`bg-red-50 border border-red-200`), red text, warning icon
- Includes a "View Details" link to `/analytics` and a dismiss button (local state, re-appears on next page load)
- Message: "Multiple recent bias audits flagged high risk. Review your Bias & Ethics analytics for details."

### HomePage.tsx
- Import `useAuthContext`, `useBiasAuditHistory`, and `HighRiskBanner`
- Call `useBiasAuditHistory(userId)` (no goal filter — check across all goals)
- Render `<HighRiskBanner entries={biasHistory?.entries ?? []} />` above the welcome banner

### AnalyticsPage.tsx
- Already has `biasHistory` from `useBiasAuditHistory` — reuse it
- Render `<HighRiskBanner entries={biasHistory?.entries ?? []} />` at the top of the component, above the header

## Verification
- `npx tsc --noEmit` passes
- With < 3 high-risk entries in last 5: banner does not appear
- With >= 3 high-risk entries in last 5: red warning banner appears on both Dashboard and Analytics pages
- Dismiss button hides the banner; navigating away and back shows it again

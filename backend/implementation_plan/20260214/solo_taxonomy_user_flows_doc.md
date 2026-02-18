# SOLO Taxonomy: User Flows Test Plan Doc Updates

## Context

`docs/user_flows_test_plan.md` documents manual Streamlit frontend test steps and references proficiency levels in several places. These must be updated to reflect the 5-level SOLO taxonomy.

---

## File to Modify

### `docs/user_flows_test_plan.md`

**a) Flow 2E step 4** (line 251) — update pill selector description:

Change:
```
Each card shows: skill name (numbered), **Required Level** pill selector (unlearned/beginner/intermediate/advanced), **Current Level** pill selector, colored header (red = gap, green = no gap)
```
To:
```
Each card shows: skill name (numbered), **Required Level** pill selector (beginner/intermediate/advanced/expert), **Current Level** pill selector (unlearned/beginner/intermediate/advanced/expert), colored header (red = gap, green = no gap)
```

Note: Required Level should not include `unlearned` (it's not in the `RequiredLevel` enum). Current Level includes all 5.

**b) Flow 2E — add new step after step 7** (after line 254) — test the `expert` level:

Add:
```
| 8 | Change a skill's **Required Level** to "expert" and **Current Level** to "advanced" | Card header turns red (gap). Skill is marked as a gap because advanced < expert |
| 9 | Change the **Current Level** to "expert" | Card header turns green. Skill is no longer a gap (expert >= expert) |
```

(Renumber subsequent steps accordingly: old step 8 → 10, old step 9 → 11, old step 10 → 12, old step 11 → 13.)

**c) Configuration endpoints note** (line 339):

Change:
```
skill levels (`["unlearned", "beginner", "intermediate", "advanced"]`)
```
To:
```
skill levels (`["unlearned", "beginner", "intermediate", "advanced", "expert"]`)
```

**d) Add Dashboard radar chart verification** — consider adding a new flow or step to Flow 2E:

```
| 14 | Navigate to **Dashboard** page after profile creation | Radar chart shows 5-level radial axis: Unlearned (0), Beginner (1), Intermediate (2), Advanced (3), Expert (4). Required and current level traces are plotted correctly |
```

---

## Verification

Review the updated doc and confirm:
1. All proficiency level lists include `expert`
2. Required Level lists exclude `unlearned` (since `RequiredLevel` enum doesn't have it)
3. New manual test steps cover `expert`-level interactions on the Skill Gap page
4. Configuration endpoint description matches the updated `APP_CONFIG`

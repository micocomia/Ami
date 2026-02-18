# Frontend: Agentic Skill Gap Pipeline UI

## Context
The backend skill gap agents are becoming truly agentic — they now autonomously retrieve course content, assess goal quality, and auto-refine vague goals. The frontend needs to:
- **Remove the manual AI Refinement button** from onboarding (system handles it seamlessly)
- **Handle new `goal_assessment` data** from the backend response
- **Show auto-refinement info** when the system refined a goal
- **Block scheduling when all skills are mastered** and guide the user to edit their goal or review levels
- **Dynamically re-check gaps** when users edit skill levels

---

## 1. Remove AI Refinement button from onboarding

**`frontend/pages/onboarding.py`**:
- Remove the "✨ AI Refinement" button (~line 185-187) and related callback logic
- Remove the `render_goal_refinement()` call and its imports
- Remove the `if_refining_learning_goal` state flag handling
- Goal input remains — user types their goal and clicks "Begin Learning"
- The backend now auto-refines if the goal is vague during skill gap identification

**`frontend/components/goal_refinement.py`**:
- Keep the file — it may still be used in `goal_management.py` as a manual fallback for users who want to re-refine after seeing results
- Alternatively, remove the AI refinement button from goal management too if we want full seamlessness

## 2. Handle `goal_assessment` in skill gap response

**`frontend/utils/request_api.py`** (`identify_skill_gap()` ~line 247):
- Currently returns only `response.get("skill_gaps")`
- Update to also extract and return `response.get("goal_assessment", {})`:
  ```python
  return {
      "skill_gaps": response.get("skill_gaps"),
      "goal_assessment": response.get("goal_assessment", {}),
  }
  ```
- Update callers to handle the new return format

**`frontend/utils/state.py`**:
- Add `goal_assessment` to the goal's state dictionary (alongside `skill_gaps`, `learner_profile`, `learning_path`)
- Store it when skill gaps are identified, clear it when goal changes

## 3. Show auto-refinement info on skill gap page

**`frontend/pages/skill_gap.py`** + **`frontend/components/gap_identification.py`**:

After skill gaps are identified, check `goal_assessment` and show appropriate UI:

### Auto-refined goal
If `goal_assessment.get("auto_refined")`:
- Show **info banner** (Streamlit `st.info`):
  - "Your goal was automatically refined for better results."
  - Show comparison: **Original:** "{original_goal}" → **Refined:** "{current_goal}"
  - User can proceed (accept refined goal) or click "Edit Goal" to modify manually

### Still vague after refinement
If `goal_assessment.get("is_vague")` and NOT `auto_refined` (i.e., refinement was attempted but goal is still vague, or no refinement context was available):
- Show **warning banner** (Streamlit `st.warning`):
  - Display the `suggestion` text from the backend
  - **"Edit Goal"** button — navigates back to goal editing (onboarding or goal management)

### Clear goal (no issues)
If neither `is_vague` nor `all_mastered`:
- No banner — proceed normally with skill gap display

## 4. All-mastered: block scheduling, offer goal edit or level review

**`frontend/pages/skill_gap.py`** + **`frontend/components/gap_identification.py`**:

If all skills have `is_gap == false` (compute dynamically, don't rely solely on backend `all_mastered`):
- Show **info banner** (Streamlit `st.info`):
  - Display the backend `suggestion` (e.g., "You already master all required skills. Consider a more advanced goal.")
- **"Schedule Learning Path" button is disabled** with clear text: "At least one skill gap is required to generate a learning path"
- Two paths forward for the user:
  1. **"Edit Goal"** button — if the user truly has mastered everything, they can navigate back to change to a more advanced or entirely different goal
  2. **Edit skill levels** — if the user thinks the AI misjudged their level on any skill, they can adjust via the existing required/current level pill selectors. Once at least 1 gap appears, the "Schedule" button re-enables

Apply the same logic in **`frontend/pages/goal_management.py`** skill gap dialog (~lines 174-221).

## 5. Dynamic gap-check on user edits

**`frontend/components/gap_identification.py`** (`render_identified_skill_gap()`):
- The existing level pill selectors (lines 53-86) already update `is_gap` on change
- Add logic to derive "Schedule Learning Path" button enabled state from: `any(g["is_gap"] for g in skill_gaps)`
- Recompute on every level edit (Streamlit re-renders on state change, so this happens naturally)
- The button should be rendered with `disabled=not has_any_gap` where `has_any_gap = any(g["is_gap"] for g in skill_gaps)`

---

## User Flows Documentation

### Update `docs/user_flows_test_plan.md`

**Add Flow 2F — Retrieval-Grounded Skill Gap Identification**:

User Story:
> As a learner setting a goal related to a verified course, I want the platform to identify skill requirements based on actual course syllabi and content, so that my skill gaps are accurate and grounded in real educational materials.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter a goal matching a verified course (e.g., "Introduction to Computer Science and Programming in Python") | Goal accepted |
| 2 | Click "Begin Learning", wait for skill gap identification | Skills identified are grounded in course syllabus (not just generic LLM knowledge) |
| 3 | Check skill names and levels | Should align with actual course content and expectations |
| 4 | Enter a specific goal ("Help me with lecture 3 of MIT 6.0001") | Skills should reflect lecture 3's specific topics |
| 5 | Enter a goal NOT matching any course ("Learn Kubernetes") | Skills still identified using LLM knowledge (graceful fallback) |

**Add Flow 2G — Automatic Goal Refinement**:

User Story:
> As a learner with a vague learning goal, I want the platform to automatically refine my goal using my profile and course content, so that I get accurate skill gaps without manual intervention.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter a vague goal (e.g., "learn stuff") and click "Begin Learning" | System auto-refines the goal. Skill gap page shows info banner: "Your goal was automatically refined" with original → refined comparison |
| 2 | Review the refined goal | Refined goal is more specific and actionable |
| 3 | Accept and proceed | Skill gaps are based on the refined goal |
| 4 | Click "Edit Goal" instead | Navigate back to goal editing with the refined goal pre-filled |
| 5 | Enter a very vague goal that can't be refined well (e.g., "help me") | Warning banner shown with suggestion to rewrite the goal manually |
| 6 | Enter a specific, clear goal (e.g., "Learn Python data analysis with Pandas") | No refinement needed, no banner. Skill gaps shown directly |

**Add Flow 2H — All Skills Mastered Handling**:

User Story:
> As a learner who already masters all required skills for my goal, I want the platform to prevent me from scheduling an unnecessary learning path and guide me to a more challenging goal.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding with a goal where resume shows mastery of all skills | Skill gap page shows info banner: "You already master all required skills" with suggestion |
| 2 | Observe "Schedule Learning Path" button | Button is disabled with message: "At least one skill gap is required" |
| 3 | Click "Edit Goal" | Navigate to goal editing to choose a more advanced goal |
| 4 | Instead, lower a skill's current level via pill selector | Card turns red (gap detected). "Schedule" button re-enables |
| 5 | Set the level back to match required | Card turns green again. "Schedule" button disables |
| 6 | Raise a skill's required level above current | Card turns red. "Schedule" button re-enables |

**Update Flow 2D** (Refining a Learning Goal):
- Note that AI refinement is now automatic during skill gap identification
- The "✨ AI Refinement" button has been removed from onboarding
- May still be available in goal management as a manual fallback
- Update frontend test steps accordingly

**Update test coverage summary table** with new backend test files and counts.

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `frontend/pages/onboarding.py` | MODIFY | Remove AI Refinement button and callback |
| `frontend/utils/request_api.py` | MODIFY | Extract and return `goal_assessment` |
| `frontend/utils/state.py` | MODIFY | Store `goal_assessment` in goal state |
| `frontend/pages/skill_gap.py` | MODIFY | Auto-refined banner, vague warning, all-mastered UI |
| `frontend/components/gap_identification.py` | MODIFY | Disable scheduling button, dynamic gap check, "Edit Goal" button |
| `frontend/pages/goal_management.py` | MODIFY | Same all-mastered/vague handling in dialog |
| `docs/user_flows_test_plan.md` | MODIFY | Add Flows 2F, 2G, 2H; update 2D |

## Key Existing Code to Reuse
- `render_goal_refinement()` — `frontend/components/goal_refinement.py` (keep for goal_management fallback)
- Level pill selectors with `is_gap` toggle — `frontend/components/gap_identification.py` (lines 53-86)
- State persistence — `frontend/utils/state.py` (debounced HTTP PUT pattern)
- Navigation patterns — existing `st.switch_page()` calls in onboarding/skill_gap pages

## Verification
1. Start frontend + backend with verified content indexed
2. Onboarding page — verify "✨ AI Refinement" button is gone
3. Enter vague goal → skill gap page shows auto-refinement info banner
4. Enter clear course goal → no banner, skills grounded in syllabus
5. Expert learner → "Schedule" button disabled, info banner with "Edit Goal" option
6. Edit skill levels → "Schedule" button re-enables/disables dynamically
7. Click "Edit Goal" on all-mastered → navigates to goal editing
8. Goal management page → same handling in skill gap dialog

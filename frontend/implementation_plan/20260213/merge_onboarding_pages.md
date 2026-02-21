# Merge Onboarding Pages into a Single Page

## Context
The current onboarding flow has two separate card-based steps (navigated via Next/Previous buttons):
1. **Card 0 — "Share Your Information"**: persona selection (dropdown), resume upload (PDF), text preferences
2. **Card 1 — "Set Learning Goal"**: learning goal text area, AI refinement button, Save & Continue

The user wants these merged into one single page matching the reference image layout: a welcome heading, a learning goal input, persona selection cards, resume upload, LinkedIn placeholder, and a "Begin Learning" button.

## Files to Modify
- **`/frontend/pages/onboarding.py`** — Rewrite to combine both steps into one page
- **`/frontend/utils/personas.py`** — No changes (keeping existing personas)

## Implementation Plan

### 1. Rewrite `pages/onboarding.py` — single-page layout

Remove the card index navigation system (`onboarding_card_index`, `render_cards_with_nav`, `render_information`, `render_goal` as separate cards). Replace with a single `render_onboard()` function that renders everything on one page in this order:

**a) Welcome Header Section**
- Large title: "Welcome to adaptive AI Tutor"
- Subtitle: "Your personal adaptive learning companion. No setup required - we'll adapt to you as we go."

**b) Learning Goal Section**
- Label: "What would you like to learn today?"
- `st.text_input` with placeholder "eg: learn english, python, data ....."
- Below the input: hint text ("Enter any topic you want to learn, and the system will automatically generate personalized content for you.") with "Adjust Preference" button (triggers AI refinement)

**c) Persona Selection Cards (5 across)**
- Use `st.columns(len(PERSONAS))` to lay out one card per persona
- Each card shows: icon, persona name (bold), description text
- Cards are clickable (use `st.button` inside each column). Selected card gets a highlighted border
- Keep existing 5 personas: Hands-on Explorer, Reflective Reader, Visual Learner, Conceptual Thinker, Balanced Learner

**d) Bottom Row — Upload Resume + LinkedIn**
- Two columns:
  - Left: `st.file_uploader` for resume (PDF, optional)
  - Right: "Connect to your LinkedIn" placeholder button (non-functional, shows toast)

**e) "Begin Learning" Button**
- Centered at bottom
- Validates: learning goal is not empty, persona is selected
- On click: saves state, navigates to skill_gap page

### 2. State management changes
- Remove `onboarding_card_index` from `_init_onboarding_state()` (no longer needed)
- Keep all existing session state keys (`learner_persona`, `learner_information`, `to_add_goal`, etc.)
- The `learner_information_text` text area is removed (the reference image doesn't have it); the persona + PDF data still get combined into `learner_information`

### 3. Keep existing dependencies unchanged
- `components/goal_refinement.py` — reuse `render_goal_refinement` (or call `refine_learning_goal` directly)
- `utils/pdf.py` — reuse `extract_text_from_pdf`
- `utils/state.py` — reuse `save_persistent_state`, `reset_to_add_goal`
- `utils/personas.py` — reuse `PERSONAS` dict as-is
- `main.py` — no changes needed (routing stays the same)

## Verification
1. Run the app with `streamlit run main.py`
2. Log in and confirm the onboarding page shows all sections on one page
3. Test persona selection (click cards, verify highlight)
4. Test learning goal input + AI refinement
5. Test resume upload
6. Test "Begin Learning" button validation (no goal → warning, no persona → warning)
7. Test successful navigation to skill_gap page after "Begin Learning"

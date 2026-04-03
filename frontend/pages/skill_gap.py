import streamlit as st

from components.gap_identification import (
    render_identifying_skill_gap,
    render_identified_skill_gap,
    render_goal_assessment_banners,
    render_retrieval_sources_banner,
    render_bias_audit_banners,
    render_skill_gap_summary,
    has_any_gap,
)
from utils.state import add_new_goal, save_persistent_state
from utils.request_api import create_learner_profile, validate_profile_fairness, get_personas


def render_skill_gap():
    # Guard: users can refresh or land directly on this page, so session keys may be missing
    goal = st.session_state.get("to_add_goal")
    if not goal:
        st.warning("No active goal found in session. Redirecting to onboarding...")
        st.switch_page("pages/onboarding.py")
        return

    has_info = st.session_state.get("learner_information") or st.session_state.get("learner_persona")
    if not goal.get("learning_goal") or not has_info:
        st.switch_page("pages/onboarding.py")
        return

    left, center, right = st.columns([1, 5, 1])
    with center:
        if st.button("< Back to Onboarding", type="secondary"):
            st.switch_page("pages/onboarding.py")
        st.title("Skill Gap")

        skill_gaps = goal.get("skill_gaps") or []
        if not skill_gaps:
            # TRY/CATCH around the component call
            try:
                render_identifying_skill_gap(goal)
            except Exception as e:
                st.error("Skill gap UI crashed while identifying skill gaps.")
                st.exception(e)
                st.stop()
        else:
            # Show goal assessment banners (auto-refined, vague, all-mastered)
            render_goal_assessment_banners(goal)

            num_skills = len(skill_gaps)
            num_gaps = sum(1 for skill in skill_gaps if skill["is_gap"])
            ai_disclaimer = ((goal.get("bias_audit") or {}).get("ethical_disclaimer") or "").strip()
            render_skill_gap_summary(
                num_skills,
                num_gaps,
                ai_disclaimer=ai_disclaimer,
                goal_assessment=goal.get("goal_assessment"),
                learning_goal=goal.get("learning_goal", ""),
            )
            render_bias_audit_banners(goal)
            render_identified_skill_gap(goal)

            # Dynamic gap-check: disable Schedule when no gaps exist
            gaps_exist = has_any_gap(skill_gaps)
            assessment = goal.get("goal_assessment") or {}
            all_mastered = assessment.get("all_mastered", False) or not gaps_exist

            space_col, edit_col, continue_button_col = st.columns([1, 0.15, 0.27])

            if all_mastered and not gaps_exist:
                with edit_col:
                    if st.button("Edit Goal", type="secondary"):
                        st.switch_page("pages/onboarding.py")

            with continue_button_col:
                schedule_disabled = not gaps_exist
                if st.button("Schedule Learning Path", type="primary", disabled=schedule_disabled):
                    if skill_gaps and not goal.get("learner_profile"):
                        with st.spinner('Creating your profile ...'):
                            try:
                                _PERSONAS = get_personas()
                                _persona_name = st.session_state.get("learner_persona", "")
                                _fslsm_baseline = _PERSONAS[_persona_name]["fslsm_dimensions"] if _persona_name in _PERSONAS else {}
                                learner_profile = create_learner_profile(
                                    goal["learning_goal"],
                                    st.session_state["learner_information"],
                                    skill_gaps,
                                    persona_name=_persona_name,
                                    fslsm_baseline=_fslsm_baseline,
                                )
                            except Exception as e:
                                st.error("Backend call failed while creating learner profile.")
                                st.exception(e)
                                st.stop()

                            if learner_profile is None:
                                st.rerun()
                            goal["learner_profile"] = learner_profile
                            st.toast("Your profile has been created!")
                            # Run fairness validation on the new profile
                            try:
                                fairness_result = validate_profile_fairness(
                                    learner_profile,
                                    st.session_state["learner_information"],
                                    persona_name=st.session_state.get("learner_persona", ""),
                                    user_id=st.session_state.get("userId"),
                                    goal_id=goal.get("id"),
                                )
                                goal["profile_fairness"] = fairness_result
                            except Exception:
                                goal["profile_fairness"] = None

                    new_goal_id = add_new_goal(**goal)
                    st.session_state["selected_goal_id"] = new_goal_id
                    st.session_state["if_complete_onboarding"] = True
                    st.session_state["selected_page"] = "Learning Path"
                    save_persistent_state()
                    st.switch_page("pages/learning_path.py")

            render_retrieval_sources_banner(goal)


render_skill_gap()

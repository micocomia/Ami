import streamlit as st

from components.gap_identification import (
    render_identifying_skill_gap,
    render_identified_skill_gap,
    render_goal_assessment_banners,
    render_retrieval_sources_banner,
    has_any_gap,
)
from utils.state import add_new_goal, get_new_goal_uid, save_persistent_state
from utils.request_api import create_learner_profile


def render_skill_gap():
    # Guard: users can refresh or land directly on this page, so session keys may be missing
    goal = st.session_state.get("to_add_goal")
    if not goal:
        st.warning("No active goal found in session. Redirecting to onboarding...")
        st.switch_page("pages/onboarding.py")
        return

    if not goal.get("learning_goal") or not st.session_state.get("learner_information"):
        st.switch_page("pages/onboarding.py")
        return

    left, center, right = st.columns([1, 5, 1])
    with center:
        if st.button("< Back to Onboarding", type="secondary"):
            st.switch_page("pages/onboarding.py")
        st.title("Skill Gap")
        st.write("Review and confirm your skill gaps.")

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
            render_retrieval_sources_banner(goal)

            num_skills = len(skill_gaps)
            num_gaps = sum(1 for skill in skill_gaps if skill["is_gap"])
            st.info(f"There are {num_skills} skills in total, with {num_gaps} skill gaps identified.")
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
                                learner_profile = create_learner_profile(
                                    goal["learning_goal"],
                                    st.session_state["learner_information"],
                                    skill_gaps,
                                    user_id=st.session_state.get("userId"),
                                    goal_id=get_new_goal_uid()
                                )
                            except Exception as e:
                                st.error("Backend call failed while creating learner profile.")
                                st.exception(e)
                                st.stop()

                            if learner_profile is None:
                                st.rerun()
                            goal["learner_profile"] = learner_profile
                            st.toast("Your profile has been created!")

                    new_goal_id = add_new_goal(**goal)
                    st.session_state["selected_goal_id"] = new_goal_id
                    st.session_state["if_complete_onboarding"] = True
                    st.session_state["selected_page"] = "Learning Path"
                    save_persistent_state()
                    st.switch_page("pages/learning_path.py")


render_skill_gap()

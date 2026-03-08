import streamlit as st

from components.goal_refinement import render_goal_refinement
from utils.request_api import create_learner_profile, delete_goal, update_goal, list_goals
from components.gap_identification import (
    render_identified_skill_gap,
    render_identifying_skill_gap,
    render_goal_assessment_banners,
    render_skill_gap_summary,
    has_any_gap,
)
from utils.state import add_new_goal, change_selected_goal_id, index_goal_by_id, reset_to_add_goal, save_persistent_state
from components.skill_info import render_skill_info


def render_goal_management():
    user_id = st.session_state.get("userId")
    if user_id:
        fresh_goals = list_goals(user_id)
        if fresh_goals:
            st.session_state["goals"] = fresh_goals

    st.title("Goal Management")
    st.write("Manage your learning goals: add new ones, edit or delete existing ones.")

    render_add_new_goal()
    st.divider()
    render_existing_goals()

def render_add_new_goal():
    if "if_refining_learning_goal" not in st.session_state:
        st.session_state["if_refining_learning_goal"] = False
        try:
            save_persistent_state()
        except Exception:
            pass
    if "if_show_skill_gap_results_in_dialog" not in st.session_state:
        st.session_state["if_show_skill_gap_results_in_dialog"] = False
        try:
            save_persistent_state()
        except Exception:
            pass

    # Ensure required session_state keys exist (avoid KeyError on fresh sessions)
    if "to_add_goal" not in st.session_state or not isinstance(st.session_state.get("to_add_goal"), dict):
        reset_to_add_goal()
        try:
            save_persistent_state()
        except Exception:
            pass
    if "goals" not in st.session_state or st.session_state.get("goals") is None:
        st.session_state["goals"] = []
        try:
            save_persistent_state()
        except Exception:
            pass

    to_add_goal = st.session_state["to_add_goal"]
    st.subheader("🎯 Add New Goal")
    new_learning_goal = st.text_area("Enter your new goal:", to_add_goal["learning_goal"], key="new_learning_goal")
    to_add_goal["learning_goal"] = new_learning_goal

    refine_col, clear_col, hint_col, add_col = st.columns([1, 1, 3, 1])

    render_goal_refinement(to_add_goal, refine_col, hint_col)
    if clear_col.button("Clear", key="clear_goal"):
        reset_to_add_goal()
        try:
            save_persistent_state()
        except Exception:
            pass
        st.rerun()

    if add_col.button("Add Goal", type="primary", icon=":material/add:", use_container_width=True):
        if new_learning_goal:
            render_skill_gap_dialog()
        else:
            hint_col.warning("Please enter a goal before adding.")

    if st.session_state["if_show_skill_gap_results_in_dialog"]:
        render_skill_gap_dialog()



def render_existing_goals():
    st.subheader("📋 Existing Goals")
    goals_raw = st.session_state.get("goals", [])
    # Normalize goals to a list of goal dicts
    if isinstance(goals_raw, dict):
        goals = [g for g in goals_raw.values() if isinstance(g, dict)]
    elif isinstance(goals_raw, list):
        goals = [g for g in goals_raw if isinstance(g, dict)]
    else:
        goals = []

    non_deleted_goals = [goal for goal in goals if not goal.get("is_deleted")]
    for goal_id, goal in enumerate(non_deleted_goals):
        with st.container():
            col_left, col_right = st.columns([3, 1])
            display_name = goal.get("learner_profile", {}).get("goal_display_name", "") or f"Goal {goal_id + 1}"
            col_left.write(f"#### {display_name}")
            
            # Check if the current goal is the active goal
            is_active = st.session_state.get("selected_goal_id") == goal["id"]
            
            if is_active:
                col_right.button("Current Active Goal", type="primary", key=f"active_{goal['id']}", use_container_width=True)
            else:
                if col_right.button("Set as Active Goal", key=f"set_{goal['id']}", help="Mark this goal as your active learning goal."):
                    change_selected_goal_id(goal["id"])
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.rerun()
            
            st.info(f"{goal['learning_goal']}")
            st.write(f"**Overall Progress:**")
            learner_profile = goal["learner_profile"]
            learning_path = goal.get("learning_path", [])
            if learning_path:
                learned_sessions = sum(1 for s in learning_path if isinstance(s, dict) and s.get("if_learned"))
                overall_progress = int((learned_sessions / len(learning_path)) * 100)
            else:
                overall_progress = learner_profile["cognitive_status"]["overall_progress"]
            progress = st.slider("Progress", min_value=0, max_value=100, value=overall_progress, key=f"progress_{goal['id']}", disabled=True)
            if learning_path:
                mastered_skills = set()
                all_skills = set()
                for s in learning_path:
                    if not isinstance(s, dict):
                        continue
                    for outcome in s.get("desired_outcome_when_completed", []):
                        skill_name = outcome.get("name", "") if isinstance(outcome, dict) else ""
                        if skill_name:
                            all_skills.add(skill_name)
                            if s.get("if_learned"):
                                mastered_skills.add(skill_name)
                all_skill = len(all_skills)
                learned_skill = len(mastered_skills)
                unlearned_skill = all_skill - learned_skill
            else:
                unlearned_skill = len(goal['learner_profile']['cognitive_status']['in_progress_skills'])
                learned_skill = len(goal['learner_profile']['cognitive_status']['mastered_skills'])
                all_skill = learned_skill + unlearned_skill
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                st.metric(label="Total Skill Count", value=all_skill, delta_color="off")
            with col2:
                st.metric(label="Mastered Skill Count", value=learned_skill, delta_color="off")
            with col3:
                st.metric(label="In-progress Skill Count", value=unlearned_skill, delta_color="off")
            with st.expander("Skill Info"):
                render_skill_info(goal["learner_profile"])
            
            col1, col2 = st.columns([7, 1])
            with col1:
                if st.button("Edit", key=f"edit_{goal['id']}"):
                    edited_goal = st.text_area("Edit Goal", value=goal["learning_goal"])
                    if st.button("Save", key=f"save_{goal['id']}"):
                        result = update_goal(st.session_state.get("userId"), goal["id"], {"learning_goal": edited_goal})
                        if result is not None:
                            goal["learning_goal"] = edited_goal
                            st.success("Goal updated successfully!")
                        else:
                            st.error("Failed to update goal. Please try again.")
            with col2:
                if st.button("Delete", key=f"delete_{goal['id']}", type="primary"):
                    goal_index = index_goal_by_id(goal["id"])
                    delete_goal(st.session_state.get("userId"), goal["id"])
                    st.session_state.goals[goal_index]["is_deleted"] = True
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.success("Goal deleted successfully!")
                    st.rerun()
        
        if goal_id < len(non_deleted_goals) - 1:
            st.divider()

            
            


@st.dialog("Skill Gap", width="large")
def render_skill_gap_dialog():
    to_add_goal = st.session_state["to_add_goal"]
    st.write("Review and confirm your skill gaps.")
    skill_gaps = to_add_goal.get("skill_gaps", [])
    num_skills = len(skill_gaps)
    num_gaps = sum(1 for skill in skill_gaps if skill["is_gap"])
    render_skill_gap_summary(num_skills, num_gaps)
    if not skill_gaps:
        st.session_state["if_show_skill_gap_results_in_dialog"] = True
        try:
            save_persistent_state()
        except Exception:
            pass
        render_identifying_skill_gap(to_add_goal)
    else:
        st.session_state["if_show_skill_gap_results_in_dialog"] = False
        try:
            save_persistent_state()
        except Exception:
            pass

        # Show goal assessment banners
        render_goal_assessment_banners(to_add_goal)

        render_identified_skill_gap(to_add_goal)

        # Dynamic gap-check: disable Schedule when no gaps exist
        gaps_exist = has_any_gap(skill_gaps)
        schedule_disabled = not gaps_exist

        if st.button("Schedule Learning Path", type="primary", disabled=schedule_disabled):
            if skill_gaps and not to_add_goal.get("learner_profile"):
                with st.spinner('Creating your profile ...'):
                    learner_profile = create_learner_profile(
                        to_add_goal["learning_goal"],
                        st.session_state["learner_information"],
                        skill_gaps,
                    )
                    if learner_profile is None:
                        st.rerun()
                    to_add_goal["learner_profile"] = learner_profile
                    st.toast("Your profile has been created!")
            new_goal_id = add_new_goal(**to_add_goal)
            st.session_state["selected_goal_id"] = new_goal_id
            try:
                save_persistent_state()
            except Exception:
                pass
            st.session_state["if_complete_onboarding"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.session_state["selected_page"] = "Learning Path"
            try:
                save_persistent_state()
            except Exception:
                pass
            st.switch_page("pages/learning_path.py")



render_goal_management()

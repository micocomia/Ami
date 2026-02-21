import streamlit as st

from utils.request_api import create_learner_profile, identify_skill_gap, audit_skill_gap_bias, get_app_config
from utils.format import format_citation
from utils.state import save_persistent_state

_LEVEL_DESCRIPTIONS = {
    "unlearned":     "No prior exposure — you haven't encountered this skill yet.",
    "beginner":      "Basic awareness — you can follow guided examples but still need support.",
    "intermediate":  "Working knowledge — you can apply this skill independently in common scenarios.",
    "advanced":      "Deep proficiency — you can tackle complex problems and guide others.",
    "expert":        "Mastery — you can innovate and define best practices in this area.",
}


def render_skill_gap_summary(num_skills: int, num_gaps: int) -> None:
    """Render the skill-count summary, a review instruction, and a level-description reference."""
    st.info(
        f"**{num_skills} skills identified · {num_gaps} skill gap{'s' if num_gaps != 1 else ''}**  \n"
        "Review each skill below. Adjust the **Current Level** if it doesn't match your "
        "actual knowledge, and toggle **Mark as Gap** to correct any mis-classifications. "
        "Only skills marked as gaps will be included in your learning path."
    )
    with st.expander("What do the proficiency levels mean?"):
        for level, description in _LEVEL_DESCRIPTIONS.items():
            st.markdown(f"- **{level.capitalize()}** — {description}")


def render_identifying_skill_gap(goal):
    with st.spinner('Identifying Skill Gap ...'):
        learning_goal = goal["learning_goal"]
        learner_information = st.session_state["learner_information"]
        llm_type = st.session_state["llm_type"]

        # Gather mastered skills from existing goals so the LLM doesn't flag them as gaps
        goals = st.session_state.get("goals", [])
        all_mastered = {}
        for g in goals:
            for skill in (g.get("learner_profile") or {}).get("cognitive_status", {}).get("mastered_skills", []):
                name = skill.get("name")
                if name and name not in all_mastered:
                    all_mastered[name] = skill

        if all_mastered:
            skill_lines = "\n".join(
                f"  - {s['name']} (proficiency: {s.get('proficiency_level', 'unknown')})"
                for s in all_mastered.values()
            )
            learner_information += (
                "\n\n[Skills already mastered from previous learning goals"
                " — do NOT list these as skill gaps]:\n" + skill_lines
            )

        skill_gaps, goal_assessment, retrieved_sources = identify_skill_gap(learning_goal, learner_information, llm_type)
    goal["skill_gaps"] = skill_gaps
    goal["goal_assessment"] = goal_assessment
    goal["retrieved_sources"] = retrieved_sources or []
    goal["_last_identified_goal"] = goal["learning_goal"]
    # If the goal was auto-refined, update the learning_goal to the refined version
    if goal_assessment and goal_assessment.get("auto_refined") and goal_assessment.get("refined_goal"):
        goal["learning_goal"] = goal_assessment["refined_goal"]
    # Run bias audit on the skill gap results
    if skill_gaps:
        try:
            skill_gaps_dict = {"skill_gaps": skill_gaps}
            if goal_assessment:
                skill_gaps_dict["goal_assessment"] = goal_assessment
            bias_audit = audit_skill_gap_bias(
                skill_gaps_dict,
                learner_information,
                llm_type,
            )
            goal["bias_audit"] = bias_audit
        except Exception:
            goal["bias_audit"] = None
    save_persistent_state()
    st.rerun()
    st.toast("Successfully identified skill gaps!")
    return skill_gaps


def render_goal_assessment_banners(goal):
    """Show info/warning banners based on goal_assessment."""
    assessment = goal.get("goal_assessment")
    if not assessment:
        return

    if assessment.get("auto_refined"):
        original = assessment.get("original_goal", "")
        st.info(
            f"Your goal was automatically refined for better results.\n\n"
            f"**Original goal:** {original}\n\n"
            f"**Refined goal:** {goal.get('learning_goal', '')}"
        )
    elif assessment.get("is_vague"):
        suggestion = assessment.get("suggestion", "Consider making your goal more specific.")
        st.warning(
            f"Your goal may be too vague to produce optimal results. {suggestion}"
        )

    if assessment.get("all_mastered"):
        suggestion = assessment.get("suggestion", "Consider setting a more advanced goal.")
        st.info(
            f"You already master all required skills for this goal. {suggestion}"
        )


def render_retrieval_sources_banner(goal):
    """Show a banner indicating whether the skill analysis used verified course content."""
    sources = goal.get("retrieved_sources") or []
    if sources:
        st.info("Skill analysis was grounded in verified course content.")
        with st.expander("View sources"):
            for idx, source in enumerate(sources, start=1):
                # Normalise to the format expected by format_citation
                source_ref = dict(source)
                if "source_type" not in source_ref:
                    source_ref["source_type"] = "verified_content"
                st.markdown(format_citation(source_ref, idx))


def has_any_gap(skill_gaps):
    """Return True if at least one skill gap exists."""
    return any(g.get("is_gap", False) for g in (skill_gaps or []))


def render_identified_skill_gap(goal, method_name="genmentor"):
    """
    Render skill gaps in a card-style with prev/next switching.
    """
    levels = get_app_config()["skill_levels"]
    required_levels = [l for l in levels if l != "unlearned"]
    # Render all skill cards on a single page (no pagination)
    skill_gaps = goal.get("skill_gaps", [])
    total = len(skill_gaps)
    if total == 0:
        st.info("No skills identified yet.")
        return

    for skill_id, skill_info in enumerate(skill_gaps):
        skill_name = skill_info.get("name", f"skill_{skill_id}")
        required_level = skill_info.get("required_level", required_levels[0])
        current_level = skill_info.get("current_level", levels[0])

        background_color = "#ffe6e6" if skill_info.get("is_gap") else "#e6ffe6"
        text_color = "#ff4d4d" if skill_info.get("is_gap") else "#33cc33"

        with st.container(border=True):
            # Card header
            st.markdown(
                f"""
                <div style="background-color: {background_color}; color: {text_color}; padding: 10px 16px; border-radius: 8px; margin-bottom: 12px; display: flex; align-items: center; min-height: 44px;">
                    <p style="font-weight: 700; margin: 0; flex: 1;">{skill_id+1:2d}. {skill_name}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Required level selector
            new_required_level = st.pills(
                "**Required Level**",
                options=required_levels,
                selection_mode="single",
                default=required_level,
                disabled=False,
                key=f"required_{skill_name}_{method_name}",
            )
            if new_required_level != required_level:
                goal["skill_gaps"][skill_id]["required_level"] = new_required_level
                if levels.index(new_required_level) > levels.index(goal["skill_gaps"][skill_id].get("current_level", levels[0])):
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                save_persistent_state()
                st.rerun()

            # Current level selector
            new_current_level = st.pills(
                "**Current Level**",
                options=levels,
                selection_mode="single",
                default=current_level,
                disabled=False,
                key=f"current_{skill_name}__{method_name}",
            )
            if new_current_level != current_level:
                goal["skill_gaps"][skill_id]["current_level"] = new_current_level
                if levels.index(new_current_level) < levels.index(goal["skill_gaps"][skill_id].get("required_level", required_levels[0])):
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                save_persistent_state()
                st.rerun()

            # Details
            with st.expander("More Analysis Details"):
                if levels.index(goal["skill_gaps"][skill_id].get("current_level", levels[0])) < levels.index(goal["skill_gaps"][skill_id].get("required_level", required_levels[0])):
                    st.warning("Current level is lower than the required level!")
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    st.success("Current level is equal to or higher than the required")
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                st.write(f"**Reason**: {skill_info.get('reason', '')}")
                st.write(f"**Confidence Level**: {skill_info.get('level_confidence', '')}")
            save_persistent_state()
            # Gap toggle
            old_gap_status = skill_info.get("is_gap", False)
            gap_status = st.toggle(
                "Mark as Gap",
                value=skill_info.get("is_gap", False),
                key=f"gap_{skill_name}_{method_name}",
                disabled=not skill_info.get("is_gap", False),
            )
            if gap_status != old_gap_status:
                goal["skill_gaps"][skill_id]["is_gap"] = gap_status
                if not goal["skill_gaps"][skill_id]["is_gap"]:
                    goal["skill_gaps"][skill_id]["current_level"] = goal["skill_gaps"][skill_id].get("required_level", goal["skill_gaps"][skill_id].get("current_level"))
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()


_FALLBACK_DISCLAIMER = (
    "These skill assessments are AI-generated inferences based on the information you provided. "
    "They may not fully reflect your actual abilities. Use them as a starting point, not a definitive evaluation."
)


def render_bias_audit_banners(goal):
    """Show ethical disclaimer and any bias/calibration warnings from the audit."""
    audit = goal.get("bias_audit")

    # Always show ethical disclaimer (even if audit failed)
    disclaimer = (audit or {}).get("ethical_disclaimer", _FALLBACK_DISCLAIMER)
    st.info(disclaimer)

    if not audit:
        return

    # Overall risk warning
    risk = audit.get("overall_bias_risk", "low")
    if risk in ("medium", "high"):
        flagged = audit.get("flagged_skill_count", 0)
        audited = audit.get("audited_skill_count", 0)
        severity_label = "Moderate" if risk == "medium" else "High"
        st.warning(
            f"{severity_label} bias risk detected: {flagged} of {audited} skills flagged. "
            f"Review the details below and consider adjusting the assessments."
        )

    # Bias flags details
    bias_flags = audit.get("bias_flags", [])
    calibration_flags = audit.get("confidence_calibration_flags", [])

    if bias_flags or calibration_flags:
        with st.expander("View bias audit details"):
            if bias_flags:
                st.markdown("**Bias Flags**")
                for flag in bias_flags:
                    severity = flag.get("severity", "low")
                    icon = {"low": "🟡", "medium": "🟠", "high": "🔴"}.get(severity, "🟡")
                    st.markdown(
                        f"{icon} **{flag.get('skill_name', 'Unknown')}** — "
                        f"*{flag.get('bias_category', '')}* ({severity})\n\n"
                        f"  {flag.get('explanation', '')}\n\n"
                        f"  **Suggestion:** {flag.get('suggestion', '')}"
                    )

            if calibration_flags:
                st.markdown("**Confidence Calibration Warnings**")
                for flag in calibration_flags:
                    st.markdown(
                        f"⚠️ **{flag.get('skill_name', 'Unknown')}**: {flag.get('issue', '')}"
                    )

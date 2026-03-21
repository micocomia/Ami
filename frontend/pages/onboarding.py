import streamlit as st

from utils.pdf import extract_text_from_pdf
from utils.state import save_persistent_state, reset_to_add_goal
from components.topbar import render_topbar
from utils.request_api import get_personas


def _init_onboarding_state():
    """Ensure required session_state keys exist to avoid KeyErrors."""
    st.session_state.setdefault("learner_persona", "")
    st.session_state.setdefault("learner_information_text", "")
    st.session_state.setdefault("learner_information", "")
    if "to_add_goal" not in st.session_state:
        reset_to_add_goal()
    try:
        save_persistent_state()
    except Exception:
        pass


def _inject_page_css():
    """Inject CSS for the merged onboarding page."""
    st.markdown(
        """
        <style>
        /* Welcome header */
        .welcome-title {
            font-size: 2.8rem;
            font-weight: 700;
            color: #111827 !important;
            text-align: center;
            margin-bottom: 0;
        }
        .welcome-subtitle {
            font-size: 1.1rem;
            color: #9ca3af;
            text-align: center;
            margin-top: 4px;
            margin-bottom: 32px;
            line-height: 1.6;
        }
        /* Section label */
        .section-label {
            text-align: center;
            font-size: 1rem;
            color: #374151;
            margin-bottom: 8px;
        }
        /* Hint text */
        .hint-text {
            font-size: 0.88rem;
            color: #6b7280;
            margin-top: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _select_persona(name):
    """Callback for persona card selection."""
    st.session_state["learner_persona"] = name
    try:
        save_persistent_state()
    except Exception:
        pass


def render_onboard():
    _init_onboarding_state()
    _inject_page_css()

    goal = st.session_state["to_add_goal"]

    PERSONAS = get_personas()

    left, center, right = st.columns([1, 5, 1])
    with center:
        render_topbar()

        # --- Welcome Header ---
        st.markdown('<h1 class="welcome-title">Welcome to Ami</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="welcome-subtitle">'
            "Your personal adaptive learning companion.<br>"
            "No setup required - we'll adapt to you as we go."
            "</p>",
            unsafe_allow_html=True,
        )

        # --- Learning Goal Input ---
        st.markdown('<p class="section-label">What would you like to learn today?</p>', unsafe_allow_html=True)
        learning_goal = st.text_input(
            "Learning goal",
            value=goal["learning_goal"],
            placeholder="eg : learn english, python, data .....",
            label_visibility="collapsed",
        )
        goal["learning_goal"] = learning_goal

        st.markdown(
            '<p class="hint-text">'
            "Enter any topic you want to learn. The system will automatically "
            "refine your goal if needed and generate personalized content for you."
            "</p>",
            unsafe_allow_html=True,
        )
        try:
            save_persistent_state()
        except Exception:
            pass

        # --- Learning Style Baseline ---
        st.write("")  # spacing
        st.markdown(
            '<p class="section-label">'
            "Help us personalize your experience — pick a persona, upload your resume, or both."
            "</p>",
            unsafe_allow_html=True,
        )

        # --- Persona Selection Cards ---
        st.markdown(
            '<p class="hint-text">Option 1 — Select a learning persona as your style baseline:</p>',
            unsafe_allow_html=True,
        )
        persona_names = list(PERSONAS.keys())
        current_persona = st.session_state.get("learner_persona", "")
        cols = st.columns(len(persona_names))
        for i, name in enumerate(persona_names):
            with cols[i]:
                is_selected = name == current_persona
                desc = PERSONAS[name]["description"]
                persona_label = f"**{name}**\n\n{desc}"
                if st.button(
                    persona_label,
                    key=f"persona_{i}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                ):
                    _select_persona(name)
        if current_persona:
            st.markdown(
                f'<p class="hint-text">✓ Selected: <strong>{current_persona}</strong></p>',
                unsafe_allow_html=True,
            )

        # --- OR Divider ---
        st.write("")
        left_div, mid_div, right_div = st.columns([2, 1, 2])
        with left_div:
            st.divider()
        with mid_div:
            st.markdown(
                '<p style="text-align:center;color:#9ca3af;margin-top:8px;">OR</p>',
                unsafe_allow_html=True,
            )
        with right_div:
            st.divider()

        # --- Upload Resume ---
        st.markdown(
            '<p class="hint-text">Option 2 — Upload your resume to infer your learning style:</p>',
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader(
            "Upload resume (PDF)",
            type="pdf",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            with st.spinner("Extracting text from PDF..."):
                learner_information_pdf = extract_text_from_pdf(uploaded_file)
                st.session_state["learner_information_pdf"] = learner_information_pdf
                st.toast("✅ PDF uploaded successfully.")
        else:
            learner_information_pdf = st.session_state.get("learner_information_pdf", "")

        # learner_information is biographical text only (resume); FSLSM baseline
        # is carried separately via learner_persona + PERSONAS lookup in skill_gap.py
        st.session_state["learner_information"] = learner_information_pdf
        try:
            save_persistent_state()
        except Exception:
            pass

        # --- Begin Learning Button ---
        st.write("")  # spacing
        _, btn_col, _ = st.columns([2, 1, 2])
        with btn_col:
            if st.button("Begin Learning", type="primary", use_container_width=True):
                has_persona = bool(st.session_state.get("learner_persona"))
                has_resume = bool(st.session_state.get("learner_information_pdf", ""))
                if not goal["learning_goal"] or not (has_persona or has_resume):
                    st.warning(
                        "Please provide a learning goal and either select a learning persona "
                        "or upload a resume (or both)."
                    )
                else:
                    # Clear stale skill gaps if the learning goal changed
                    previous_goal = goal.get("_last_identified_goal", "")
                    if goal["learning_goal"] != previous_goal:
                        goal["skill_gaps"] = []
                        goal["learner_profile"] = {}
                    st.session_state["selected_page"] = "Skill Gap"
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.switch_page("pages/skill_gap.py")

        # --- Data Transparency Notice ---
        st.write("")  # spacing
        with st.expander("How your data is used"):
            st.markdown(
                "**What we collect:** Your learning goal, and optionally a selected persona and/or "
                "resume text. During learning, we also record quiz scores and session timing.\n\n"
                "**AI-generated assessments:** Skill levels, learner profiles, and learning content "
                "are generated by AI based on the information you provide. They are estimates and "
                "may not fully reflect your actual abilities.\n\n"
                "**External services:** Your learning goal and background information are sent to "
                "an LLM provider (e.g., OpenAI) to generate personalised assessments and content.\n\n"
                "**Your control:** You can delete your account and all associated data at any time "
                "from the My Profile page. No data is shared with third parties or used for advertising."
            )


render_onboard()

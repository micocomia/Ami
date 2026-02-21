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
        /* Persona cards */
        .persona-card {
            background: #ffffff;
            border: 1.5px solid #e5e7eb;
            border-radius: 12px;
            padding: 18px 14px;
            min-height: 150px;
            cursor: pointer;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .persona-card:hover {
            border-color: #007bff;
            box-shadow: 0 2px 12px rgba(0,123,255,0.10);
        }
        .persona-card.selected {
            border-color: #007bff;
            box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
            background: #f0f7ff;
        }
        .persona-card .persona-icon {
            font-size: 1.5rem;
            margin-bottom: 6px;
            color: #6b7280;
        }
        .persona-card .persona-name {
            font-weight: 700;
            font-size: 0.95rem;
            color: #111827;
            margin-bottom: 6px;
        }
        .persona-card .persona-desc {
            font-size: 0.82rem;
            color: #6b7280;
            line-height: 1.4;
        }
        /* Bottom action cards */
        .action-card {
            background: #ffffff;
            border: 1.5px solid #e5e7eb;
            border-radius: 12px;
            padding: 18px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            min-height: 60px;
        }
        .action-card .action-icon {
            font-size: 1.3rem;
            color: #6b7280;
        }
        .action-card .action-text {
            font-size: 0.95rem;
            color: #6b7280;
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
        st.markdown('<h1 class="welcome-title">Welcome to adaptive AI Tutor</h1>', unsafe_allow_html=True)
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

        # --- Persona Selection Cards ---
        st.write("")  # spacing
        persona_names = list(PERSONAS.keys())
        current_persona = st.session_state.get("learner_persona", "")
        cols = st.columns(len(persona_names))
        for i, name in enumerate(persona_names):
            with cols[i]:
                is_selected = name == current_persona
                selected_class = " selected" if is_selected else ""
                desc = PERSONAS[name]["description"]
                st.markdown(
                    f'<div class="persona-card{selected_class}">'
                    f'<div class="persona-icon">ℹ️</div>'
                    f'<div class="persona-name">{name}</div>'
                    f'<div class="persona-desc">{desc}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.button(
                    "Select" if not is_selected else "✓ Selected",
                    key=f"persona_{i}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                    on_click=_select_persona,
                    args=(name,),
                )

        # Build learner_information from persona
        persona_name = st.session_state.get("learner_persona", "")
        if persona_name and persona_name in PERSONAS:
            dims = PERSONAS[persona_name]["fslsm_dimensions"]
            persona_prefix = (
                f"Learning Persona: {persona_name} "
                f"(initial FSLSM: processing={dims['fslsm_processing']}, "
                f"perception={dims['fslsm_perception']}, "
                f"input={dims['fslsm_input']}, "
                f"understanding={dims['fslsm_understanding']}). "
            )
        else:
            persona_prefix = ""

        # --- Upload Resume + LinkedIn ---
        st.write("")  # spacing
        upload_col, linkedin_col = st.columns(2)
        with upload_col:
            uploaded_file = st.file_uploader(
                "Upload Your Resume (Optional)",
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
                st.markdown(
                    '<div class="action-card">'
                    '<span class="action-icon">ℹ️</span>'
                    '<span class="action-text">Upload Your Resume (Optional)</span>'
                    "</div>",
                    unsafe_allow_html=True,
                )
        with linkedin_col:
            st.markdown(
                '<div class="action-card">'
                '<span class="action-icon">ℹ️</span>'
                '<span class="action-text">Connect to your LinkedIn</span>'
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("Connect LinkedIn", use_container_width=True, type="secondary"):
                st.toast("LinkedIn integration coming soon!")

        # Combine learner information
        st.session_state["learner_information"] = persona_prefix + learner_information_pdf
        try:
            save_persistent_state()
        except Exception:
            pass

        # --- Begin Learning Button ---
        st.write("")  # spacing
        _, btn_col, _ = st.columns([2, 1, 2])
        with btn_col:
            if st.button("Begin Learning", type="primary", use_container_width=True):
                if not goal["learning_goal"] or not st.session_state.get("learner_persona"):
                    st.warning("Please provide both a learning goal and select a learning persona before continuing.")
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
                "**What we collect:** Your learning goal, selected persona, and optionally your "
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

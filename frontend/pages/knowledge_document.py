import json
import re
import streamlit as st
import streamlit.components.v1 as components
import urllib.parse as urlparse
from utils.request_api import (
    complete_session,
    delete_learning_content,
    evaluate_mastery,
    generate_learning_content,
    get_learning_content,
    post_session_activity,
    submit_content_feedback,
)
from utils.format import inject_citation_tooltips
from utils.state import get_current_session_uid, get_selected_goal, save_persistent_state
from config import use_mock_data, use_search, backend_endpoint, backend_public_endpoint
from assets.js.doc_reading import doc_reading_auto_scroll_js
from utils.document_parser import parse_document_for_section_view


st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)


def _current_backend_public_base() -> str:
    """Resolve browser-facing backend endpoint from live session settings, fallback to config."""
    endpoint = st.session_state.get("backend_public_endpoint", backend_public_endpoint)
    if not isinstance(endpoint, str) or not endpoint.strip():
        endpoint = backend_public_endpoint or backend_endpoint
    return endpoint.rstrip("/")


def _absolutize_backend_url(path_or_url: str) -> str:
    """Build absolute browser-facing URL for backend-served static assets."""
    if not isinstance(path_or_url, str):
        return ""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return f"{_current_backend_public_base()}/{path_or_url.lstrip('/')}"


def _replace_current_goal(updated_goal):
    if not isinstance(updated_goal, dict):
        return
    selected_goal_id = st.session_state.get("selected_goal_id")
    goals = st.session_state.get("goals", [])
    if not isinstance(goals, list):
        return
    for idx, goal in enumerate(goals):
        if isinstance(goal, dict) and str(goal.get("id")) == str(selected_goal_id):
            goals[idx] = updated_goal
            break


def _cache_learning_content(session_uid, learning_content):
    st.session_state.setdefault("document_caches", {})[session_uid] = learning_content
    return learning_content


def _end_current_session_activity():
    user_id = st.session_state.get("userId")
    goal_id = st.session_state.get("selected_goal_id")
    session_index = st.session_state.get("selected_session_id")
    if user_id is None or goal_id is None or session_index is None:
        return
    post_session_activity(user_id, goal_id, session_index, "end")


def render_learning_content():
    if 'if_render_qizzes' not in st.session_state:
        st.session_state['if_render_qizzes'] = False
        try:
            save_persistent_state()
        except Exception:
            pass

    goal = get_selected_goal()
    if not isinstance(goal, dict):
        st.error("No active goal found. Please select an active goal first.")
        return
    if not goal["learning_path"]:
        st.error("Learning path is still scheduling. Please visit this page later.")
        return

    render_session_details(goal)
    session_uid = get_current_session_uid()
    is_document_available = st.session_state["document_caches"].get(session_uid, False)
    if not is_document_available and not st.session_state["if_updating_learner_profile"]:
        learning_content = render_content_preparation(goal)
        if learning_content is None:
            st.error("Failed to prepare knowledge content.")
            return
    else:
        learning_content = st.session_state["document_caches"].get(session_uid, "")

        # Show content format badge and audio player (Sprint 3: audio-visual adaptive content)
        content_format = learning_content.get("content_format", "standard")
        audio_url = learning_content.get("audio_url")
        audio_mode = learning_content.get("audio_mode")
        if not audio_url:
            st.session_state.pop("last_media_url", None)
        if content_format == "audio_enhanced":
            if audio_mode == "narration_optional":
                st.info("🎧 This lesson keeps written content and offers an optional narrated audio version.")
            else:
                st.info("🎙️ This lesson keeps written content and offers an optional host-expert audio version.")
            if audio_url:
                media_url = _absolutize_backend_url(audio_url)
                st.session_state["last_media_url"] = media_url
                st.audio(media_url, format="audio/mpeg")
        elif content_format == "visual_enhanced":
            st.info("📊 This content includes visual resources (diagrams, videos, images) for visual learners.")

        render_type = "by_section"
        document = learning_content["document"]
        sources_used = learning_content.get("sources_used", [])
        if render_type == "by_section":
            render_document_content_by_section(
                document,
                sources_used,
                learning_content.get("view_model"),
            )
        else:
            render_document_content_by_document(document)

        if st.session_state['if_render_qizzes']:
            quiz_data = learning_content["quizzes"]
            render_questions(quiz_data)
            st.divider()
            selected_sid = st.session_state["selected_session_id"]
            session_info_bottom = goal["learning_path"][selected_sid]
            complete_button_status = True if session_info_bottom["if_learned"] else False

            # Mastery gating for bottom Complete Session button
            nav_mode_bottom = session_info_bottom.get("navigation_mode", "linear")
            mastery_info_bottom = st.session_state.get("mastery_status", {}).get(session_uid, {})
            is_mastered_bottom = mastery_info_bottom.get("is_mastered", False)
            if nav_mode_bottom == "linear":
                complete_disabled_bottom = (
                    complete_button_status
                    or st.session_state["if_updating_learner_profile"]
                    or not is_mastered_bottom
                )
            else:
                complete_disabled_bottom = complete_button_status or st.session_state["if_updating_learner_profile"]

            if st.button("Regenerate", icon=":material/refresh:"):
                _end_current_session_activity()
                st.session_state["document_caches"].pop(session_uid, None)
                delete_learning_content(
                    st.session_state.get("userId"),
                    st.session_state.get("selected_goal_id"),
                    st.session_state.get("selected_session_id"),
                )
                try:
                    save_persistent_state()
                except Exception:
                    pass
                goal['learner_profile']['behavioral_patterns']['additional_notes'] += f"I have regenerated Session {selected_sid} content.\n"
                st.rerun()
            if st.button("Complete Session",
                        key="complete-session", type="primary", icon=":material/task_alt:",
                        use_container_width=True, disabled=complete_disabled_bottom):
                _handle_session_completion(goal, selected_sid, session_info_bottom)

            st.divider()
            render_content_feedback_form(goal)
            render_motivational_triggers()


def render_motivational_triggers():
    result = post_session_activity(
        st.session_state.get("userId"),
        st.session_state.get("selected_goal_id"),
        st.session_state.get("selected_session_id"),
        "heartbeat",
    )
    trigger = (result or {}).get("trigger", {})
    if trigger.get("show") and trigger.get("message"):
        st.toast(trigger["message"])

def _handle_session_completion(goal, selected_sid, session_info):
    """Handle session completion: update profile, mark learned, navigate away."""
    with st.spinner("Updating learner profile..."):
        result = complete_session(
            st.session_state.get("userId"),
            st.session_state.get("selected_goal_id"),
            selected_sid,
        )
    if not result:
        st.session_state["if_updating_learner_profile"] = False
        return
    updated_goal = result.get("goal")
    if isinstance(updated_goal, dict):
        _replace_current_goal(updated_goal)
    st.session_state["if_updating_learner_profile"] = False
    try:
        save_persistent_state()
    except Exception:
        pass
    st.switch_page("pages/learning_path.py")


def render_session_details(goal):
    selected_sid = st.session_state["selected_session_id"]
    session_uid = get_current_session_uid()
    session_info = goal["learning_path"][selected_sid]

    col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
    with col1:
        if st.button("Back", icon=":material/arrow_back:", key="back-learning-center"):
            _end_current_session_activity()
            st.session_state["selected_page"] = "Learning Path"
            st.session_state["current_page"][session_uid] = 0

            st.switch_page("pages/learning_path.py")
            try:
                save_persistent_state()
            except Exception:
                pass

    with col3:
        if st.button("Regenerate", icon=":material/refresh:", key="regenerate-content-top"):
            _end_current_session_activity()
            st.session_state["document_caches"].pop(session_uid, None)
            delete_learning_content(
                st.session_state.get("userId"),
                st.session_state.get("selected_goal_id"),
                st.session_state.get("selected_session_id"),
            )
            try:
                save_persistent_state()
            except Exception:
                pass
            goal['learner_profile']['behavioral_patterns']['additional_notes'] += f"I have regenerated Session {selected_sid} content.\n"
            st.session_state["current_page"][session_uid] = 0
            st.rerun()

    with col4:
        complete_button_status = True if session_info["if_learned"] else False

        # Mastery gating for sequential (linear) learners
        navigation_mode = session_info.get("navigation_mode", "linear")
        mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})
        is_mastered = mastery_info.get("is_mastered", False)

        if navigation_mode == "linear":
            complete_disabled = (
                complete_button_status
                or st.session_state["if_updating_learner_profile"]
                or not is_mastered
            )
            if not is_mastered and not complete_button_status:
                st.info("Pass the quiz to unlock session completion.")
        else:
            complete_disabled = complete_button_status or st.session_state["if_updating_learner_profile"]

        if st.button("Complete Session",
                     key="complete-session-bottom", type="primary", icon=":material/task_alt:",
                     use_container_width=True, disabled=complete_disabled):
            _handle_session_completion(goal, selected_sid, session_info)

    st.write(f"# {session_info['id']}")
    st.write(f"# {session_info['title']}")

    with st.container(border=True):
        st.info(session_info["abstract"])
        associated_skills = session_info["associated_skills"]
        st.write("**Associated Skills:**")
        for i, skill_name in enumerate(associated_skills):
            st.write(f"- {skill_name}")

def render_content_preparation(goal):
    selected_sid = st.session_state["selected_session_id"]
    selected_gid = st.session_state["selected_goal_id"]
    user_id = st.session_state.get("userId")
    learning_session = goal["learning_path"][selected_sid]
    session_uid = get_current_session_uid()
    if use_mock_data:
        st.warning("Using mock data for knowledge document.")
        file_path = "./assets/data_example/knowledge_document.json"
        learning_content = load_knowledge_point_content(file_path)
        _cache_learning_content(session_uid, learning_content)
        try:
            save_persistent_state()
        except Exception:
            pass
        return learning_content

    if user_id is not None:
        cached_learning_content = get_learning_content(user_id, selected_gid, selected_sid)
        if cached_learning_content:
            _cache_learning_content(session_uid, cached_learning_content)
            # Ensure the page re-enters the "document available" branch and renders immediately.
            st.rerun()
            return cached_learning_content

    with st.spinner("Generating personalized learning content..."):
        learning_content = generate_learning_content(
            goal["learner_profile"],
            goal["learning_path"],
            learning_session,
            use_search=use_search,
            allow_parallel=True,
            with_quiz=True,
            goal_context=goal.get("goal_context"),
            user_id=user_id,
            goal_id=selected_gid,
            session_index=selected_sid,
            llm_type="gpt4o",
        )

    if not learning_content:
        st.error("Failed to generate learning content.")
        return

    learning_content.setdefault("sources_used", [])
    _cache_learning_content(session_uid, learning_content)
    try:
        save_persistent_state()
    except Exception:
        pass
    st.rerun()
    return learning_content

def render_document_content_by_section(document, sources_used=None, view_model=None):
    selected_gid = st.session_state["selected_goal_id"]
    session_id = st.session_state["selected_session_id"]
    if "current_page" not in st.session_state or not isinstance(st.session_state["current_page"], dict):
        st.session_state["current_page"] = {}

    section_documents = []
    sidebar_items = []
    references_section = None
    if isinstance(view_model, dict) and view_model.get("sections"):
        for idx, section in enumerate(view_model.get("sections", [])):
            if not isinstance(section, dict):
                continue
            section_documents.append(section.get("markdown", ""))
            sidebar_items.append({
                "title": section.get("title", f"Section {idx + 1}"),
                "anchor": section.get("anchor", ""),
                "level": int(section.get("level", 2) or 2),
                "page_index": idx,
            })
        references = view_model.get("references", [])
        if references:
            references_section = "\n".join(
                f"{item.get('index', idx + 1)}. {item.get('label', '')}"
                for idx, item in enumerate(references)
                if isinstance(item, dict)
            )
    else:
        parsed = parse_document_for_section_view(document)
        section_documents = list(parsed.get("section_documents", []))
        sidebar_items = list(parsed.get("sidebar_items", []))
        references_section = parsed.get("references_section")

    if not section_documents:
        st.warning("No document sections are available.")
        return

    page_key = f"{selected_gid}-{session_id}"
    params = {}
    try:
        params = dict(st.query_params)
    except Exception:
        pass

    if 'gm_page' in params:
        try:
            p = int(params['gm_page'])
            p = max(0, min(p, len(section_documents) - 1))
            st.session_state['current_page'][page_key] = p
            try:
                save_persistent_state()
            except Exception:
                pass
        except Exception:
            pass
    if 'gm_anchor' in params and params['gm_anchor']:
        try:
            st.session_state[f"{page_key}__pending_anchor_text"] = urlparse.unquote(params['gm_anchor'])
        except Exception:
            st.session_state[f"{page_key}__pending_anchor_text"] = params['gm_anchor']

    current_page = st.session_state['current_page'].get(page_key, 0)

    prev_page_key = f"{page_key}__prev"
    prev_page = st.session_state.get(prev_page_key, None)
    if prev_page is None or prev_page != current_page or st.session_state.get(f"{page_key}__pending_anchor_text"):
        pending_anchor_text = st.session_state.get(f"{page_key}__pending_anchor_text")
        pending_anchor_js = json.dumps(pending_anchor_text) if pending_anchor_text else 'null'
        components.html(doc_reading_auto_scroll_js.replace("PENDING_ANCHOR_PLACEHOLDER", pending_anchor_js),
            height=1,
        )
        st.session_state[prev_page_key] = current_page
        st.session_state[f"{page_key}__pending_anchor_text"] = None
        try:
            save_persistent_state()
        except Exception:
            pass
    section_md = section_documents[current_page]
    if sources_used:
        section_md = inject_citation_tooltips(section_md, sources_used)
    # Absolutize backend static URLs (diagrams, audio) for the Streamlit renderer
    _backend_base = _current_backend_public_base()
    section_md = section_md.replace('/static/', f'{_backend_base}/static/')
    st.markdown(section_md, unsafe_allow_html=True)

    if references_section:
        with st.expander("References", expanded=False, icon=":material/menu_book:"):
            ref_body = "\n".join(references_section.split("\n")[1:]).strip() if references_section.startswith("## ") else references_section
            st.markdown(ref_body)

    st.sidebar.header("Document Structure")
    for idx, item in enumerate(sidebar_items):
        if item["level"] == 2:
            if st.sidebar.button(item["title"], key=f"toc_l2_{idx}", type="primary" if item["page_index"] == current_page else "secondary"):
                st.session_state.setdefault("current_page", {})[page_key] = item["page_index"]
                st.rerun()
            st.sidebar.markdown("")
        elif item["level"] == 3:
            st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;[{item['title']}](#{item['anchor']})", unsafe_allow_html=True)

    col_prev, col_center, col_next= st.columns([1, 4, 1])
    if current_page > 0:
        if col_prev.button("Previous Page", icon=":material/arrow_back:", use_container_width=True, key="prev-section-page"):
            new_page = current_page - 1
            st.session_state["current_page"][page_key] = new_page
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
    if current_page < len(section_documents) - 1:
        if col_next.button("Next Page", icon=":material/arrow_forward:", use_container_width=True, key="next-section-page"):
            new_page = current_page + 1
            st.session_state["current_page"][page_key] = new_page
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

    st.divider()

    if current_page == len(section_documents) - 1:
        st.session_state["if_render_qizzes"] = True
    else:
        st.session_state["if_render_qizzes"] = False

    

def render_document_content_by_document(document):
    st.session_state["if_render_qizzes"] = True

    titles = re.findall(r'^(#+)\s*(.*)', document, re.MULTILINE)

    sections = []
    for level, title in titles:
        section = {'level': len(level), 'title': title}
        sections.append(section)

    sidebar_content = ""
    curr_level_1_idx = 0
    curr_level_2_idx = 0
    curr_level_3_idx = 0
    for i, section in enumerate(sections):
        anchor = re.sub(r'[^\w\s]', '-', section["title"].lower()).replace(" ", "-")
        if section["level"] == 1:
            continue
        if section["level"] == 2:
            curr_level_2_idx += 1
            curr_level_3_idx = 0
            sidebar_content += f"[**{curr_level_2_idx}. {section['title']}**](#{anchor})\n"
        elif section["level"] == 3:
            curr_level_3_idx += 1
            sidebar_content += f"> [{curr_level_2_idx}.{curr_level_3_idx}. {section['title']}](#{anchor})\n\n"

    st.sidebar.header("Document Structure")
    st.sidebar.markdown(sidebar_content)

    st.markdown(document)

    for section in sections:
        anchor = section["title"].replace(" ", "").replace("，", "").replace("。", "")
        st.markdown(f"<a name='{anchor}'></a>", unsafe_allow_html=True)


def render_questions(quiz_data):
    """Render quiz questions in Submit All mode (no per-question feedback).

    All answers are collected and submitted together for mastery evaluation.
    """
    st.subheader("Test Your Knowledge")

    session_uid = get_current_session_uid()

    # Initialize answer storage for this session
    if session_uid not in st.session_state.get("quiz_answers", {}):
        st.session_state.setdefault("quiz_answers", {})[session_uid] = {
            "single_choice_questions": [None] * len(quiz_data.get("single_choice_questions", [])),
            "multiple_choice_questions": [[] for _ in quiz_data.get("multiple_choice_questions", [])],
            "true_false_questions": [None] * len(quiz_data.get("true_false_questions", [])),
            "short_answer_questions": [None] * len(quiz_data.get("short_answer_questions", [])),
            "open_ended_questions": [None] * len(quiz_data.get("open_ended_questions", [])),
        }

    answers = st.session_state["quiz_answers"][session_uid]
    q_num = 0

    # Check if quiz has been submitted and mastered already
    mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})
    quiz_submitted = mastery_info.get("score") is not None

    # Single choice questions
    for i, q in enumerate(quiz_data.get("single_choice_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        selected = st.radio(
            "Options", q["options"], key=f"sc_{session_uid}_{i}",
            index=None, label_visibility="hidden", disabled=quiz_submitted,
        )
        answers["single_choice_questions"][i] = selected

    # Multiple choice questions
    for i, q in enumerate(quiz_data.get("multiple_choice_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}** (Select all that apply)")
        selected = []
        for j, option in enumerate(q["options"]):
            if st.checkbox(option, key=f"mc_{session_uid}_{i}_{j}", disabled=quiz_submitted):
                selected.append(option)
        answers["multiple_choice_questions"][i] = selected

    # True/False questions
    for i, q in enumerate(quiz_data.get("true_false_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        selected = st.radio(
            "True or False?", ["True", "False"], key=f"tf_{session_uid}_{i}",
            index=None, label_visibility="hidden", disabled=quiz_submitted,
        )
        answers["true_false_questions"][i] = selected

    # Short answer questions
    for i, q in enumerate(quiz_data.get("short_answer_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        user_answer = st.text_input(
            "Your Answer", key=f"sa_{session_uid}_{i}",
            label_visibility="hidden", disabled=quiz_submitted,
        )
        answers["short_answer_questions"][i] = user_answer if user_answer else None

    # Open-ended questions (Sprint 3: SOLO taxonomy — Relational / Extended Abstract)
    if quiz_data.get("open_ended_questions"):
        st.divider()
        st.caption("The following questions require a detailed written response and will be evaluated using the SOLO Taxonomy.")
    for i, q in enumerate(quiz_data.get("open_ended_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        st.caption("Write a detailed response demonstrating your understanding.")
        user_answer = st.text_area(
            "Your Response", key=f"oe_{session_uid}_{i}",
            height=150, label_visibility="hidden", disabled=quiz_submitted,
        )
        answers["open_ended_questions"][i] = user_answer if user_answer else None

    try:
        save_persistent_state()
    except Exception:
        pass

    # Show mastery result or submit button
    if mastery_info.get("is_mastered"):
        st.success(
            f"Mastery achieved! Score: {mastery_info['score']:.0f}% "
            f"(threshold: {mastery_info.get('threshold', 70):.0f}%)"
        )
        # Show explanations after mastery
        _render_quiz_explanations(quiz_data, mastery_info)
    elif quiz_submitted and not mastery_info.get("is_mastered"):
        st.warning(
            f"Score: {mastery_info['score']:.0f}%. "
            f"Need {mastery_info.get('threshold', 70):.0f}% to master this session. "
            f"Review the material and try again."
        )
        # Show explanations after attempt
        _render_quiz_explanations(quiz_data, mastery_info)
        if st.button("Retake Quiz", icon=":material/refresh:", type="primary"):
            st.session_state["quiz_answers"].pop(session_uid, None)
            st.session_state["mastery_status"].pop(session_uid, None)
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
    else:
        if st.button("Submit Quiz", type="primary", icon=":material/check_circle:"):
            with st.spinner("Evaluating your responses..."):
                result = evaluate_mastery(
                    user_id=st.session_state.get("userId", ""),
                    goal_id=st.session_state["selected_goal_id"],
                    session_index=st.session_state["selected_session_id"],
                    quiz_answers=answers,
                )
            if result:
                st.session_state.setdefault("mastery_status", {})[session_uid] = {
                    "score": result["score_percentage"],
                    "is_mastered": result["is_mastered"],
                    "threshold": result["threshold"],
                    "short_answer_feedback": result.get("short_answer_feedback", []),
                    "open_ended_feedback": result.get("open_ended_feedback", []),
                }
                # Mirror mastery data onto the learning path session so it
                # survives save_persistent_state() and is available for the
                # adapt-learning-path endpoint.
                current_goal = get_selected_goal()
                if not isinstance(current_goal, dict):
                    st.error("No active goal found. Please reselect your goal and retry.")
                    return
                session_obj = current_goal["learning_path"][st.session_state["selected_session_id"]]
                session_obj["mastery_score"] = result["score_percentage"]
                session_obj["is_mastered"] = result["is_mastered"]
                session_obj["mastery_threshold"] = result["threshold"]
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
            else:
                st.error("Failed to evaluate quiz. Please try again.")


_SOLO_LEVEL_COLORS = {
    "prestructural": "#FF4444",
    "unistructural": "#FF8800",
    "multistructural": "#DDAA00",
    "relational": "#2288FF",
    "extended_abstract": "#22CC66",
}

_SOLO_LEVEL_LABELS = {
    "prestructural": "Prestructural",
    "unistructural": "Unistructural",
    "multistructural": "Multistructural",
    "relational": "Relational",
    "extended_abstract": "Extended Abstract",
}


def _render_quiz_explanations(quiz_data, mastery_info=None):
    """Show quiz explanations and SOLO-level feedback after submission."""
    with st.expander("View Explanations", expanded=False, icon=":material/info:"):
        q_num = 0
        for q in quiz_data.get("single_choice_questions", []):
            q_num += 1
            correct = q["options"][q["correct_option"]]
            st.write(f"**Q{q_num}.** Correct: {correct}")
            st.write(f"  {q['explanation']}")
        for q in quiz_data.get("multiple_choice_questions", []):
            q_num += 1
            correct = [q["options"][idx] for idx in q["correct_options"]]
            st.write(f"**Q{q_num}.** Correct: {', '.join(correct)}")
            st.write(f"  {q['explanation']}")
        for q in quiz_data.get("true_false_questions", []):
            q_num += 1
            correct = "True" if q["correct_answer"] else "False"
            st.write(f"**Q{q_num}.** Correct: {correct}")
            st.write(f"  {q['explanation']}")

        # Short answer: show expected answer plus LLM semantic evaluation feedback
        sa_feedback = (mastery_info or {}).get("short_answer_feedback", [])
        for i, q in enumerate(quiz_data.get("short_answer_questions", [])):
            q_num += 1
            st.write(f"**Q{q_num}.** Expected: {q['expected_answer']}")
            st.write(f"  {q['explanation']}")
            if i < len(sa_feedback):
                fb = sa_feedback[i]
                icon = "✓" if fb.get("is_correct") else "✗"
                color = "#22CC66" if fb.get("is_correct") else "#FF4444"
                st.markdown(
                    f"<span style='color:{color}'>{icon} {fb.get('feedback', '')}</span>",
                    unsafe_allow_html=True,
                )

        # Open-ended: show rubric and SOLO-level evaluation feedback
        oe_feedback = (mastery_info or {}).get("open_ended_feedback", [])
        for i, q in enumerate(quiz_data.get("open_ended_questions", [])):
            q_num += 1
            st.write(f"**Q{q_num}.** (Open-ended)")
            with st.container(border=True):
                st.caption("Rubric")
                st.write(q.get("rubric", ""))
                if q.get("example_answer"):
                    st.caption("Example answer")
                    st.write(q["example_answer"])
            if i < len(oe_feedback):
                fb = oe_feedback[i]
                solo_level = fb.get("solo_level", "")
                score = fb.get("score", 0.0)
                label = _SOLO_LEVEL_LABELS.get(solo_level, solo_level.title())
                color = _SOLO_LEVEL_COLORS.get(solo_level, "#999999")
                st.markdown(
                    f"**SOLO Level:** <span style='color:{color};font-weight:bold'>{label}</span> "
                    f"— Score: {score:.0%}",
                    unsafe_allow_html=True,
                )
                st.write(f"Feedback: {fb.get('feedback', '')}")

def render_content_feedback_form(goal):
    st.header("🌟 Session Feedback") 
    with st.form("feedback_form"):
        st.info("Your feedback helps us improve the learning experience.\nPlease take a moment to share your thoughts.")

        col1, col2 = st.columns([1, 3])
        col1.write("Clarity of Content")
        clarity = col2.feedback("stars", key="clarity")

        col1, col2 = st.columns([1, 3])
        col1.write("Relevance to Goals")
        relevance = col2.feedback("stars", key="relevance")

        col1, col2 = st.columns([1, 3])
        col1.write("Depth of Content")
        depth = col2.feedback("stars", key="depth")

        col1, col2 = st.columns([1, 3])
        col1.write("Engagement Level")
        engagement = col2.feedback("faces", key="engagement")

        additional_comments = st.text_area("Additional Comments", max_chars=500)
        feedback_data = {
            "clarity": clarity,
            "relevance": relevance,
            "depth": depth,
            "engagement": engagement,
            "additional_comments": additional_comments
        }
        submitted = st.form_submit_button("Submit Feedback")
        if submitted:
            result = update_learner_profile_with_feedback(goal, feedback_data)
            if result:
                st.success("Thank you for your feedback!")

def update_learner_profile_with_feedback(goal, feedback_data, session_information=""):
    user_id = st.session_state.get("userId")
    goal_id = st.session_state.get("selected_goal_id")
    is_cognitive_update = session_information != ""
    if is_cognitive_update:
        response = complete_session(
            user_id=user_id,
            goal_id=goal_id,
            session_index=st.session_state.get("selected_session_id"),
        )
    else:
        response = submit_content_feedback(
            user_id=user_id,
            goal_id=goal_id,
            feedback=feedback_data,
        )
    if response is None:
        st.error("Failed to update learner profile. Please try again.")
        return False
    updated_goal = response.get("goal")
    if isinstance(updated_goal, dict):
        _replace_current_goal(updated_goal)
        goal.update(updated_goal)
    st.toast("🎉 Your profile has been updated!")
    return True

def load_knowledge_point_content(file_path):
    try:
        knowledge_document = json.load(open(file_path))
        return knowledge_document
    except FileNotFoundError:
        st.error("Knowledge document not found. Please make sure `knowledge_document.md` is in the correct directory.")
        return None

render_learning_content()

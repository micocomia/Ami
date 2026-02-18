import json
import math
import time
import copy
import re
import streamlit as st
import streamlit.components.v1 as components
import urllib.parse as urlparse
from components.time_tracking import track_session_learning_start_time
from utils.request_api import draft_knowledge_points, explore_knowledge_points, generate_document_quizzes, integrate_learning_document, update_cognitive_status, update_learning_preferences, get_app_config, evaluate_mastery
from utils.format import prepare_markdown_document, extract_sources_used, inject_citation_tooltips
from utils.state import get_current_session_uid, save_persistent_state
from config import use_mock_data, use_search
from assets.js.doc_reading import doc_reading_auto_scroll_js


st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)


def render_learning_content():
    if 'if_render_qizzes' not in st.session_state:
        st.session_state['if_render_qizzes'] = False
        try:
            save_persistent_state()
        except Exception:
            pass

    goal = st.session_state["goals"][st.session_state["selected_goal_id"]]
    if not goal["learning_path"]:
        st.error("Learning path is still scheduling. Please visit this page later.")
        return

    render_session_details(goal)
    session_uid = get_current_session_uid()
    session_id = st.session_state["selected_session_id"]
    selected_gid = st.session_state["selected_goal_id"]
    is_document_available = st.session_state["document_caches"].get(session_uid, False)
    if not is_document_available and not st.session_state["if_updating_learner_profile"]:
        learning_content = render_content_preparation(goal)
        if learning_content is None:
            st.error("Failed to prepare knowledge content.")
            return
    else:
        track_session_learning_start_time()
        learning_content = st.session_state["document_caches"].get(session_uid, "")

        render_type = "by_section"
        document = learning_content["document"]
        sources_used = learning_content.get("sources_used", [])
        if render_type == "by_section":
            render_document_content_by_section(document, sources_used)
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
                st.session_state["document_caches"].pop(session_uid)
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
    curr_time = time.time()
    session_uid = get_current_session_uid()
    session_learning_times = st.session_state["session_learning_times"][session_uid]
    last_session_trigger_time = session_learning_times["trigger_time_list"][-1]
    last_session_trigger_time_index = len(session_learning_times["trigger_time_list"])
    trigger_interval = get_app_config()["motivational_trigger_interval_secs"]
    if curr_time - last_session_trigger_time > trigger_interval:
        if last_session_trigger_time_index % 2 == 0:
            st.toast("🌟 Stay hydrated and keep a healthy posture.")
        else:
            st.toast("🚀 Keep up the good work!")
        session_learning_times["trigger_time_list"].append(curr_time)

def _handle_session_completion(goal, selected_sid, session_info):
    """Handle session completion: update profile, mark learned, navigate away."""
    session_uid = get_current_session_uid()
    with st.spinner("Updating learner profile..."):
        result = update_learner_profile_with_feedback(goal, "", session_information=session_info)
    if not result:
        st.session_state["if_updating_learner_profile"] = False
        return
    session_info["if_learned"] = True
    if session_uid in st.session_state.get("session_learning_times", {}):
        st.session_state["session_learning_times"][session_uid]["end_time"] = time.time()
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
            st.session_state["selected_page"] = "Learning Path"
            st.session_state["current_page"][session_uid] = 0

            st.switch_page("pages/learning_path.py")
            try:
                save_persistent_state()
            except Exception:
                pass

    with col3:
        if st.button("Regenerate", icon=":material/refresh:", key="regenerate-content-top"):
            st.session_state["document_caches"].pop(session_uid)
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
    learning_session = goal["learning_path"][selected_sid]
    session_uid = get_current_session_uid()
    if use_mock_data:
        st.warning("Using mock data for knowledge document.")
        file_path = "./assets/data_example/knowledge_document.json"
        learning_content = load_knowledge_point_content(file_path)
        st.session_state["document_caches"][session_uid] = learning_content
        try:
            save_persistent_state()
        except Exception:
            pass
        return learning_content

    with st.spinner("Stage 1/4 - Exploring knowledge Points..."):
        knowledge_points = explore_knowledge_points(
            goal["learner_profile"],
            goal["learning_path"],
            learning_session,
            llm_type="gpt4o"
        )
    if knowledge_points is None:
        st.error("Failed to explore knowledge points.")
        return
    else:
        st.success("Stage 1/4 🔍 Knowledge points explored successfully.")
        with st.expander("View Explored Knowledge Points", expanded=False):
            for kp in knowledge_points:
                st.write(f"- {kp['name']} (`{kp['type']}`)")
    with st.spinner("Stage 2/4 - Drafting knowledge points..."):
        knowledge_drafts = draft_knowledge_points(
            goal["learner_profile"],
            goal["learning_path"],
            learning_session,
            knowledge_points,
            use_search=use_search,
            allow_parallel=True,
            llm_type="gpt4o"
        )
    if knowledge_drafts is None:
        st.error("Failed to draft knowledge points.")
        return
    sources_used = extract_sources_used(knowledge_drafts)
    st.success("Stage 2/4 📝 Knowledge points drafted successfully.")
    with st.spinner("Stage 3/4 - Integrating knowledge document..."):
        document_structure = integrate_learning_document(
            goal["learner_profile"],
            goal["learning_path"],
            learning_session,
            knowledge_points,
            knowledge_drafts,
            llm_type="gpt4o",
            output_markdown=False
        )
        learning_document = prepare_markdown_document(document_structure, knowledge_points, knowledge_drafts)
    if learning_document is None:
        st.error("Failed to integrate knowledge document.")
        return
    st.success("Stage 3/4 📚 Knowledge document integrated successfully.")
    learning_content = {"document": learning_document, "sources_used": sources_used}
    with st.spinner("Stage 4/4 - Generating document quizzes..."):
        quizzes = generate_document_quizzes(
            goal["learner_profile"],
            learning_document,
            single_choice_count=3,
            multiple_choice_count=1,
            true_false_count=1,
            short_answer_count=1,
            llm_type="gpt4o"
        )
    learning_content["quizzes"] = quizzes
    st.success("Stage 4/4 🎯 Document quizzes generated successfully.")
    st.session_state["document_caches"][session_uid] = learning_content
    try:
        save_persistent_state()
    except Exception:
        pass
    st.rerun()
    return learning_content

def render_document_content_by_section(document, sources_used=None):
    selected_gid = st.session_state["selected_goal_id"]
    session_id = st.session_state["selected_session_id"]
    if "current_page" not in st.session_state or not isinstance(st.session_state["current_page"], dict):
        st.session_state["current_page"] = {}

    titles = re.findall(r'^(#+)\s*(.*)', document, re.MULTILINE)

    section_starts = []
    start_idx = 0
    for title in titles:
        if title[0] == "#":
            continue
        elif title[0] == "##":
            start_idx = document.find(title[1], start_idx)
            section_starts.append(start_idx-3)
    section_documents = []
    references_section = None
    for i in range(len(section_starts)):
        start_idx = section_starts[i]
        end_idx = section_starts[i + 1] if i + 1 < len(section_starts) else len(document)
        section_text = document[start_idx:end_idx-1].strip()
        # Extract References section so it can be shown persistently
        if section_text.startswith("## References"):
            references_section = section_text
        else:
            section_documents.append(section_text)

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
    st.markdown(section_md, unsafe_allow_html=True)

    if references_section:
        with st.expander("References", expanded=False, icon=":material/menu_book:"):
            # Skip the "## References" header line and render the body
            ref_body = "\n".join(references_section.split("\n")[1:]).strip()
            st.markdown(ref_body)

    st.sidebar.header("Document Structure")
    curr_l2 = 0
    curr_l3 = 0
    page_idx_counter = -1
    for m in re.finditer(r'^(#+)\s*(.+)$', document, re.MULTILINE):
        level_marks, title_txt = m.group(1), m.group(2).strip()
        level_len = len(level_marks)
        if level_len == 1:
            continue
        if level_len == 2 and title_txt == "References":
            continue
        if level_len == 2:
            page_idx_counter += 1
            curr_l2 += 1
            curr_l3 = 0
            if st.sidebar.button(f"{curr_l2}. {title_txt}", key=f"toc_l2_{page_idx_counter}", type="primary" if page_idx_counter == current_page else "secondary"):
                st.session_state.setdefault("current_page", {})[page_key] = page_idx_counter
                st.rerun()
            st.sidebar.markdown("")

        elif level_len == 3 and page_idx_counter >= 0:
            curr_l3 += 1
            st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;[{curr_l2}.{curr_l3}. {title_txt}](#{title_txt.lower().replace(' ', '-').replace('，','').replace('。','')})", unsafe_allow_html=True)

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
        _render_quiz_explanations(quiz_data)
    elif quiz_submitted and not mastery_info.get("is_mastered"):
        st.warning(
            f"Score: {mastery_info['score']:.0f}%. "
            f"Need {mastery_info.get('threshold', 70):.0f}% to master this session. "
            f"Review the material and try again."
        )
        # Show explanations after attempt
        _render_quiz_explanations(quiz_data)
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
                }
                # Mirror mastery data onto the learning path session so it
                # survives save_persistent_state() and is available for the
                # adapt-learning-path endpoint.
                current_goal = st.session_state["goals"][st.session_state["selected_goal_id"]]
                session_obj = current_goal["learning_path"][st.session_state["selected_session_id"]]
                session_obj["mastery_score"] = result["score_percentage"]
                session_obj["is_mastered"] = result["is_mastered"]
                session_obj["mastery_threshold"] = result["threshold"]
                # Flag adaptation suggestion if backend suggests it
                if result.get("plan_adaptation_suggested"):
                    goal_id = st.session_state.get("selected_goal_id")
                    st.session_state[f"adaptation_suggested_{goal_id}"] = True
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
            else:
                st.error("Failed to evaluate quiz. Please try again.")


def _render_quiz_explanations(quiz_data):
    """Show quiz explanations after submission."""
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
        for q in quiz_data.get("short_answer_questions", []):
            q_num += 1
            st.write(f"**Q{q_num}.** Expected: {q['expected_answer']}")
            st.write(f"  {q['explanation']}")

def render_content_feedback_form(goal):
    st.header("🌟 Value Your Feedback!") 
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
        submitted = st.form_submit_button("Submit Feedback", on_click=update_learner_profile_with_feedback, kwargs={"feedback_data": feedback_data, "goal": goal})
        if submitted:
            st.success("Thank you for your feedback!")

def update_learner_profile_with_feedback(goal, feedback_data, session_information=""):
    user_id = st.session_state.get("userId")
    goal_id = st.session_state.get("selected_goal_id")
    if session_information != "":
        # Session completion → update only cognitive status
        session_information = copy.deepcopy(session_information)
        session_information["if_learned"] = True
        new_learner_profile = update_cognitive_status(
            goal["learner_profile"], session_information,
            user_id=user_id, goal_id=goal_id,
        )
    else:
        # Content feedback → update only learning preferences
        new_learner_profile = update_learning_preferences(
            goal["learner_profile"], feedback_data,
            user_id=user_id, goal_id=goal_id,
        )
    if new_learner_profile is None:
        st.error("Failed to update learner profile. Please try again.")
        return False
    else:
        goal["learner_profile"] = new_learner_profile
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
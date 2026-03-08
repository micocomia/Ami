import streamlit as st
from streamlit_float import *
from utils.request_api import chat_with_tutor, audit_chatbot_bias, save_learner_profile
from utils.state import get_selected_goal
from components.chatbot_bias import render_chatbot_bias_banners


@st.dialog("Ask Ami")
def ask_autor_chatbot():
    instruction = "Hi, I'm Ami. I'm here to help you step-by-step and keep you encouraged while you learn. What would you like to work on?"
    # messages.chat_message("user").write(prompt)
    st.info(instruction)
    
    goal = get_selected_goal()
    if not isinstance(goal, dict):
        goal = st.session_state["to_add_goal"]
    learner_profile = goal["learner_profile"]

    messages = st.container(height=300)
    if prompt := st.chat_input("Ask me anything"):
        messages.chat_message("user").write(prompt)
        st.session_state["tutor_messages"].append({"role": "user", "content": prompt})

        selected_session = st.session_state.get("selected_session_id")
        session_index = None
        learning_path = goal.get("learning_path", []) if isinstance(goal, dict) else []
        if (
            isinstance(selected_session, int)
            and isinstance(learning_path, list)
            and 0 <= selected_session < len(learning_path)
        ):
            session_index = selected_session

        response_payload = chat_with_tutor(
            st.session_state["tutor_messages"][-20:],
            learner_profile,
            user_id=st.session_state.get("userId"),
            goal_id=goal.get("id") if isinstance(goal, dict) else None,
            session_index=session_index,
            learner_information=st.session_state.get("learner_information", ""),
            return_metadata=True,
        )
        if isinstance(response_payload, dict):
            response = response_payload.get("response") or "I could not generate a response right now."
            updated_profile = response_payload.get("updated_learner_profile")
            if isinstance(updated_profile, dict):
                user_id = st.session_state.get("userId")
                goal_id = goal.get("id") if isinstance(goal, dict) else None
                if user_id and goal_id is not None:
                    save_learner_profile(user_id, goal_id, updated_profile)
                goal["learner_profile"] = updated_profile
                st.session_state["learner_profile"] = updated_profile
                for idx, existing_goal in enumerate(st.session_state.get("goals", [])):
                    if isinstance(existing_goal, dict) and existing_goal.get("id") == goal.get("id"):
                        st.session_state["goals"][idx]["learner_profile"] = updated_profile
                        break
        else:
            response = response_payload or "I could not generate a response right now."

        messages.chat_message("assistant").write(response)
        st.session_state["tutor_messages"].append({"role": "assistant", "content": response})

        # Run chatbot bias audit (non-blocking)
        try:
            learner_information = st.session_state.get("learner_information", "")
            chatbot_audit_result = audit_chatbot_bias(response, learner_information)
            st.session_state["chatbot_bias_audit"] = chatbot_audit_result
        except Exception:
            st.session_state["chatbot_bias_audit"] = None

        # Render bias warnings if any
        audit = st.session_state.get("chatbot_bias_audit")
        if audit:
            render_chatbot_bias_banners(audit)

def click_chatbot_func():
    ask_autor_chatbot()


def render_chatbot():
    float_init()

    button_container = st.container()
    with button_container:
        if_open_chatbot = st.button("Ask Ami ", type="primary", key="chatbot", icon="🤖", on_click=click_chatbot_func)
        if if_open_chatbot:
            st.session_state.show_chatbot = True

    button_css = float_css_helper(width="8rem", right="2rem", bottom="4rem", transition=0)
    button_container.float(button_css)

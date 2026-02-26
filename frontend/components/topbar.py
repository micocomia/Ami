import streamlit as st
import config
from utils.state import save_persistent_state, load_persistent_state, clear_user_state
import requests
import re
from urllib.parse import urlparse
from pathlib import Path
from utils.request_api import get_available_models, auth_register, auth_login


@st.dialog("Login / Register")
def login():
    login_tab, register_tab = st.tabs(["Login", "Register"])
    with login_tab:
        login_user = st.text_input("Username", key="login_username")
        login_pass = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_submit"):
            if not login_user or not login_pass:
                st.error("Please enter both username and password.")
            else:
                status, data = auth_login(login_user, login_pass)
                if status == 200:
                    clear_user_state()
                    st.session_state["userId"] = data["username"]
                    st.session_state["auth_token"] = data.get("token", "")
                    load_persistent_state()
                    st.session_state["logged_in"] = True
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.rerun()
                elif status == 401:
                    st.error("Invalid username or password.")
                elif status is None:
                    st.error("Could not reach backend. Please check your settings.")
                else:
                    st.error(data.get("detail", "Login failed."))

    with register_tab:
        reg_user = st.text_input("Username", key="reg_username")
        reg_pass = st.text_input("Password", type="password", key="reg_password")
        reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
        if st.button("Register", key="reg_submit"):
            if not reg_user or not reg_pass:
                st.error("Please fill in all fields.")
            elif len(reg_user) < 3:
                st.error("Username must be at least 3 characters.")
            elif len(reg_pass) < 6:
                st.error("Password must be at least 6 characters.")
            elif reg_pass != reg_confirm:
                st.error("Passwords do not match.")
            else:
                status, data = auth_register(reg_user, reg_pass)
                if status == 200:
                    clear_user_state()
                    st.session_state["logged_in"] = True
                    st.session_state["userId"] = data["username"]
                    st.session_state["auth_token"] = data.get("token", "")
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.rerun()
                elif status == 409:
                    st.error("Username already exists. Please choose another.")
                elif status is None:
                    st.error("Could not reach backend. Please check your settings.")
                else:
                    st.error(data.get("detail", "Registration failed."))


def logout():
    clear_user_state()
    # Pop UI-only keys not covered by PERSIST_KEYS
    for k in ["selected_model", "agent_reasoning",
              "agent_reasoning_context", "agent_reasoning_raw_response"]:
        st.session_state.pop(k, None)


def render_topbar():

    # Ensure expected session keys exist (prevents KeyError on first load / direct page nav)
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("userId", "default")
    st.session_state.setdefault("backend_endpoint", getattr(config, "backend_endpoint", "http://127.0.0.1:8000/"))
    st.session_state.setdefault(
        "backend_public_endpoint",
        getattr(config, "backend_public_endpoint", st.session_state["backend_endpoint"]),
    )
    st.session_state.setdefault("if_complete_onboarding", False)
    st.session_state.setdefault("goals", [])
    st.session_state.setdefault("_navigated_lp_once", False)
    col1, col3, col4 = st.columns([1, 8, 1])
    # first-time backend availability check
    if "checked_backend" not in st.session_state:
        st.session_state["checked_backend"] = False
    if not st.session_state["checked_backend"]:
        try:
            # try a fast GET to backend root
            internal_backend_endpoint = st.session_state.get("backend_endpoint")
            models = get_available_models(internal_backend_endpoint)
            model_id_list = [f"{m['model_provider']}/{m['model_name']}" for m in models]
            st.session_state["available_models"] = model_id_list
            backend_ok = True
            if len(model_id_list) == 0:
                backend_ok = False
        except Exception:
            backend_ok = False
        if not backend_ok:
            st.warning("Backend not reachable. Please check your settings.")
            # open settings dialog so user can update `frontend/config.py`
            settings()
        st.session_state["checked_backend"] = True
    with col1:
        if st.button("", icon=":material/settings:", use_container_width=False):
            settings()

    with col4:
        if st.session_state.get("logged_in", False):
            with st.popover("", icon=":material/account_circle:", use_container_width=True):
                st.caption(f"Signed in as **{st.session_state.get('userId', '')}**")
                logout_button = st.button("Log-out", icon=":material/exit_to_app:")
                if logout_button:
                    logout()
                    st.rerun()
        else:
            if st.button("", icon=":material/account_circle:", use_container_width=True):
                login()


@st.dialog("Settings")
def settings():
    """Settings dialog to edit runtime backend endpoints."""
    def _normalize_endpoint(value: str) -> str:
        value = (value or "").strip()
        if value and not value.endswith("/"):
            value += "/"
        return value

    def _looks_like_url(value: str) -> bool:
        parsed = urlparse(value)
        return bool(parsed.scheme in {"http", "https"} and parsed.netloc)

    # current backend endpoint values
    is_valid_backend = False
    if_check_api = False
    did_check_api = False
    cur_backend = st.session_state.get("backend_endpoint", getattr(config, "backend_endpoint", "http://127.0.0.1:8000/"))
    cur_public_backend = st.session_state.get(
        "backend_public_endpoint",
        getattr(config, "backend_public_endpoint", cur_backend),
    )
    new_backend = st.text_input("Backend endpoint (internal, include protocol and port)", value=cur_backend)
    new_public_backend = st.text_input(
        "Public backend URL (for browser media/static files)",
        value=cur_public_backend,
    )

    st.markdown("---")

    col1, col3  = st.columns([2, 1])
    with col3:
        if st.button("Check & Save", type="primary", use_container_width=True):
            if_check_api = True
            new_backend = _normalize_endpoint(new_backend)
            new_public_backend = _normalize_endpoint(new_public_backend)

    if if_check_api:
        did_check_api = True
        try:
            models = get_available_models(new_backend)
            model_id_list = [f"{m['model_provider']}/{m['model_name']}" for m in models]
            if len(model_id_list) > 0:
                is_valid_backend = True
            else:
                is_valid_backend = False
        except Exception as e:
            is_valid_backend = False
        if_check_api = False

    if is_valid_backend:
        st.session_state["backend_endpoint"] = new_backend
        st.session_state["backend_public_endpoint"] = new_public_backend or new_backend
        st.session_state["available_models"] = model_id_list
        if new_public_backend and not _looks_like_url(new_public_backend):
            st.warning("Public backend URL format looks invalid; saved anyway. Audio/static links may fail in browser.")
        try:
            save_persistent_state()
            st.success("Settings saved. Restarting app...")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save settings: {e}")

    if did_check_api and not is_valid_backend:
        st.warning("Backend endpoint not reachable or invalid.")
        st.info("Ensure the Ami backend API is running and the endpoint is correct, including protocol and port (e.g., http://127.0.0.1:8000/).")
        st.info("Set Public backend URL to a browser-reachable host (e.g., http://localhost:8000/) when internal endpoint uses host.docker.internal.")
        st.info("Please refer to the [Ami Backend Setup Instructions] for more details on how to set up and run the backend service.")

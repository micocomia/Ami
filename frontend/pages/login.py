import os
import streamlit as st
from utils.request_api import auth_login, auth_register
from utils.state import clear_user_state, load_persistent_state, save_persistent_state

st.markdown("""<style>
.stApp { background-color: #d5eaee !important; }
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stMainBlockContainer"] {
    background-color: transparent !important;
    max-width: 500px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-top: 48px !important;
    padding-left: 16px !important;
    padding-right: 16px !important;
}

[data-testid="stTabs"] {
    background: white !important;
    border-radius: 16px !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.12) !important;
    padding: 16px 20px !important;
}
</style>""", unsafe_allow_html=True)

_, logo_col, _ = st.columns([1, 2, 1])
with logo_col:
    logo_path = os.path.join(os.path.dirname(__file__), "../assets/Logo_black.png")
    st.image(logo_path, use_container_width=True)

login_tab, register_tab = st.tabs(["Sign in", "Register"])

with login_tab:
    st.caption("Welcome back — enter your credentials to continue.")
    login_user = st.text_input("Username", key="login_username_page")
    login_pass = st.text_input("Password", type="password", key="login_password_page")
    if st.button("Sign in", type="primary", use_container_width=True, key="login_submit_page"):
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
    st.caption("Create an account to get started.")
    reg_user = st.text_input("Username", key="reg_username_page")
    reg_pass = st.text_input("Password", type="password", key="reg_password_page")
    reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm_page")
    if st.button("Register", type="primary", use_container_width=True, key="reg_submit_page"):
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

import os
import streamlit as st

from streamlit_cognito_auth import CognitoAuthenticator

pool_id = os.environ.get("COGNITIO_POOL_ID")
app_client_id = os.environ.get("COGNITIO_APP_CLIENT_ID")
if pool_id and app_client_id:
    print("!!!!", pool_id, app_client_id)
    app_client_secret = os.environ.get("COGNITIO_APP_CLIENT_SECRET", None)

    authenticator = CognitoAuthenticator(
        pool_id=pool_id,
        app_client_id=app_client_id,
        app_client_secret=app_client_secret,
    )

    is_logged_in = authenticator.login()
    st.session_state['is_logged_in'] = is_logged_in
    if not is_logged_in:
        st.stop()

    def logout():
        authenticator.logout()

    with st.sidebar:
        st.text(f"Welcome,{authenticator.get_username()}")
        st.button("Logout", "logout_btn", on_click=logout)

st.header("Welcome to AWS GenAI and moderation demo site")
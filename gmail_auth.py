import json
import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_flow():

    config = {
        "web": {
            "client_id": st.secrets["gmail_oauth"]["client_id"],
            "client_secret": st.secrets["gmail_oauth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES
    )

    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    return flow


def connect_gmail():

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        login_hint=st.user.email
    )

    st.session_state["gmail_oauth_state"] = state

    return authorization_url


def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # Normal page — no OAuth callback
    if not code and not error:
        return False

    if error:
        st.error(f"Gmail authorization failed: {error}")
        st.query_params.clear()
        return False

    saved_state = st.session_state.get("gmail_oauth_state")

    if not saved_state or state != saved_state:
        st.error("Invalid Gmail OAuth state.")
        st.query_params.clear()
        return False

    try:

        flow = get_gmail_flow()

        flow.fetch_token(code=code)

        credentials = flow.credentials

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]

        # Make sure Gmail belongs to logged-in user
        if gmail_email.lower() != st.user.email.lower():

            st.error(
                f"Logged-in account: {st.user.email}\n\n"
                f"Gmail account selected: {gmail_email}\n\n"
                "Please connect the same Google account."
            )

            st.query_params.clear()
            return False

        user_id = st.user.get("sub")

        if not user_id:
            st.error("Could not identify Google user.")
            return False

        if "gmail_tokens" not in st.session_state:
            st.session_state["gmail_tokens"] = {}

        st.session_state["gmail_tokens"][user_id] = (
            json.loads(credentials.to_json())
        )

        st.session_state["gmail_connected"] = True

        st.query_params.clear()

        st.success(
            f"✅ Gmail connected: {gmail_email}"
        )

        return True

    except Exception as e:

        st.error(f"Gmail connection failed: {e}")

        st.query_params.clear()

        return False
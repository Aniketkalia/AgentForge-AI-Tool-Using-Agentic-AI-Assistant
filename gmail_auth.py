import json
import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
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

    # IMPORTANT:
    # Gmail OAuth uses homepage, NOT /oauth2callback
    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    return flow


def connect_gmail():

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email
    )

    # Save state for callback validation
    st.session_state["gmail_oauth_state"] = state

    return authorization_url


def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # No Gmail OAuth response
    if not code and not error:
        return False

    # Google returned an error
    if error:

        st.error(
            f"Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False

    # Missing authorization code
    if not code:

        st.error(
            "Gmail authorization code was not received."
        )

        st.query_params.clear()

        return False

    # Check OAuth state
    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "Gmail OAuth session expired. "
            "Please click Connect Gmail again."
        )

        st.query_params.clear()

        return False

    if state != saved_state:

        st.error(
            "Invalid Gmail OAuth state."
        )

        st.query_params.clear()

        return False

    try:

        # Create a fresh OAuth flow
        flow = get_gmail_flow()

        # Exchange code for Gmail credentials
        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials

        # Create Gmail API service
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        # Get the Gmail account associated with
        # THIS OAuth authorization
        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]

        logged_in_email = st.user.email

        # SECURITY CHECK
        # Gmail account must be the same account
        # that logged into AgentForge.
        if gmail_email.lower() != logged_in_email.lower():

            st.error(
                "Account mismatch.\n\n"
                f"AgentForge login: {logged_in_email}\n"
                f"Gmail account: {gmail_email}\n\n"
                "Please connect the same Google account."
            )

            st.query_params.clear()

            return False

        # Streamlit Google user ID
        user_id = st.user.get("sub")

        if not user_id:

            st.error(
                "Unable to identify logged-in user."
            )

            st.query_params.clear()

            return False

        # Store token for CURRENT USER
        if "gmail_tokens" not in st.session_state:

            st.session_state["gmail_tokens"] = {}

        st.session_state["gmail_tokens"][user_id] = (
            json.loads(
                credentials.to_json()
            )
        )

        # Store connection information
        st.session_state["gmail_connected"] = True
        st.session_state["gmail_email"] = gmail_email

        # Remove OAuth query parameters
        st.query_params.clear()

        st.success(
            f"✅ Gmail connected: {gmail_email}"
        )

        return True

    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        st.query_params.clear()

        return False


def get_gmail_service():

    user_id = st.user.get("sub")

    if not user_id:
        return None

    tokens = st.session_state.get(
        "gmail_tokens",
        {}
    )

    token_data = tokens.get(user_id)

    if not token_data:
        return None

    try:

        credentials = Credentials.from_authorized_user_info(
            token_data,
            GMAIL_SCOPES
        )

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        return service

    except Exception as e:

        st.error(
            f"Unable to create Gmail service: {e}"
        )

        return None

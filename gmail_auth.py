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

    flow.redirect_uri = st.secrets[
        "gmail_oauth"
    ]["redirect_uri"]

    return flow


def connect_gmail():

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
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

    # No Gmail callback
    if not code and not error:
        return False

    # Google returned an error
    if error:

        st.error(
            f"Gmail authorization failed: {error}"
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
            "Please click Connect My Gmail again."
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

        flow = get_gmail_flow()

        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials

        # Build Gmail service using the OAuth
        # credentials of THIS logged-in user.
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        # ------------------------------------------------------
        # Find the Gmail account represented by these credentials
        # ------------------------------------------------------

        profile = (
            service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        gmail_email = profile["emailAddress"]

        logged_in_email = st.user.email

        # ------------------------------------------------------
        # SECURITY CHECK
        # Gmail account MUST equal AgentForge login account
        # ------------------------------------------------------

        if (
            gmail_email.lower()
            !=
            logged_in_email.lower()
        ):

            st.error(
                f"""
❌ Gmail account mismatch.

AgentForge login:
{logged_in_email}

Gmail account:
{gmail_email}

Please select the same Google account.
"""
            )

            st.query_params.clear()

            return False

        # ------------------------------------------------------
        # Get current Google user's unique ID
        # ------------------------------------------------------

        user_id = st.user.get("sub")

        if not user_id:

            st.error(
                "Unable to identify Google user."
            )

            st.query_params.clear()

            return False

        # ------------------------------------------------------
        # Store Gmail credentials PER USER
        # ------------------------------------------------------

        if "gmail_tokens" not in st.session_state:

            st.session_state[
                "gmail_tokens"
            ] = {}

        st.session_state[
            "gmail_tokens"
        ][user_id] = json.loads(
            credentials.to_json()
        )

        # Save connected email
        st.session_state[
            "gmail_email"
        ] = gmail_email

        st.session_state[
            "gmail_connected"
        ] = True

        # Remove OAuth parameters
        st.query_params.clear()

        return True

    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        st.query_params.clear()

        return False

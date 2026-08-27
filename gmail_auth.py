import json
import streamlit as st

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_flow():
    """
    Creates a Gmail OAuth flow using the SEPARATE Gmail OAuth client.
    """

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
        scopes=GMAIL_SCOPES,
    )

    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    return flow


def connect_gmail():
    """
    Start Gmail OAuth for the currently logged-in Streamlit user.
    """

    if not st.user.is_logged_in:
        st.error("Please login first.")
        return None

    current_user = st.user.email

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=current_user,
    )

    # Save OAuth state for this browser session.
    st.session_state["gmail_oauth_state"] = state
    st.session_state["gmail_oauth_in_progress"] = True

    return authorization_url


def handle_gmail_callback():
    """
    Handles the Gmail OAuth callback.

    IMPORTANT:
    This is only called when Gmail OAuth was explicitly started.
    """

    if not st.user.is_logged_in:
        return False

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # No OAuth response.
    if not code and not error:
        return False

    # Only handle callbacks created by our Gmail connection button.
    if not st.session_state.get("gmail_oauth_in_progress"):
        return False

    # Google returned an OAuth error.
    if error:
        st.error(f"Gmail authorization failed: {error}")

        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        st.query_params.clear()

        return False

    # Missing authorization code.
    if not code:
        st.error("Gmail OAuth authorization code is missing.")

        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        st.query_params.clear()

        return False

    # Missing state.
    if not state:
        st.error("Gmail OAuth state is missing.")

        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        st.query_params.clear()

        return False

    saved_state = st.session_state.get("gmail_oauth_state")

    # Protect against OAuth state mismatch.
    if not saved_state or state != saved_state:
        st.error(
            "Invalid Gmail OAuth state. "
            "Please click 'Connect My Gmail' again."
        )

        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        st.query_params.clear()

        return False

    try:

        # Create a fresh OAuth flow.
        flow = get_gmail_flow()

        # Complete OAuth.
        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Build Gmail API service.
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        # Ask Gmail which account authorized the application.
        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]

        current_user = st.user.email

        # VERY IMPORTANT:
        # Gmail account must be the same account that logged
        # into AgentForge.
        if gmail_email.lower() != current_user.lower():

            st.error(
                "Gmail account mismatch.\n\n"
                f"AgentForge user: {current_user}\n\n"
                f"Gmail account: {gmail_email}\n\n"
                "Please connect the same Google/Gmail account."
            )

            st.session_state.pop("gmail_oauth_state", None)
            st.session_state.pop("gmail_oauth_in_progress", None)

            st.query_params.clear()

            return False

        # Google unique user ID.
        user_id = st.user.get("sub")

        if not user_id:
            st.error(
                "Unable to identify the logged-in Google user."
            )

            return False

        # --------------------------------------------------------
        # USER-SPECIFIC GMAIL TOKENS
        # --------------------------------------------------------

        if "gmail_tokens" not in st.session_state:
            st.session_state["gmail_tokens"] = {}

        # Store this Gmail token ONLY under this logged-in user's ID.
        st.session_state["gmail_tokens"][user_id] = (
            json.loads(credentials.to_json())
        )

        # Store Gmail email for display.
        st.session_state["gmail_email"] = gmail_email

        # Mark Gmail connected.
        st.session_state["gmail_connected"] = True

        # Cleanup OAuth state.
        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        # Remove ?code=...&state=... from browser.
        st.query_params.clear()

        st.success(
            f"✅ Gmail connected successfully: {gmail_email}"
        )

        return True

    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        st.session_state.pop("gmail_oauth_state", None)
        st.session_state.pop("gmail_oauth_in_progress", None)

        st.query_params.clear()

        return False


def get_current_gmail_credentials():
    """
    Return Gmail credentials belonging to the CURRENT
    logged-in AgentForge user.
    """

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {}
    )

    token_data = gmail_tokens.get(user_id)

    if not token_data:
        return None

    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_info(
        token_data,
        GMAIL_SCOPES,
    )

    return credentials


def get_current_gmail_service():
    """
    Return Gmail API service for the CURRENT user.
    """

    credentials = get_current_gmail_credentials()

    if credentials is None:
        return None

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

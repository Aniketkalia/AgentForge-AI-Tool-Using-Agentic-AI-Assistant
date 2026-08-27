import json
import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# GMAIL SCOPES
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# GET OAUTH FLOW
# ============================================================

def get_gmail_flow():

    client_id = st.secrets["gmail_oauth"]["client_id"]
    client_secret = st.secrets["gmail_oauth"]["client_secret"]
    redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
    )

    flow.redirect_uri = redirect_uri

    return flow


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:
        st.error("Please login to AgentForge first.")
        return None

    flow = get_gmail_flow()

    # IMPORTANT:
    # Explicitly pass scope.
    # This fixes:
    # "Missing required parameter: scope"

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email,
        scope=" ".join(GMAIL_SCOPES),
    )

    # Save OAuth state
    st.session_state["gmail_oauth_state"] = state

    st.session_state["gmail_oauth_in_progress"] = True

    return authorization_url


# ============================================================
# HANDLE GOOGLE CALLBACK
# ============================================================

def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # --------------------------------------------------------
    # Nothing returned from Google
    # --------------------------------------------------------

    if not code and not error:
        return False

    # --------------------------------------------------------
    # Google OAuth error
    # --------------------------------------------------------

    if error:

        st.error(
            f"❌ Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # AgentForge login check
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "❌ AgentForge login session is not active."
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # Authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "❌ Gmail authorization code was not received."
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # OAuth state
    # --------------------------------------------------------

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "❌ Gmail OAuth session expired. "
            "Please click Connect My Gmail again."
        )

        st.query_params.clear()

        return False

    if state != saved_state:

        st.error(
            "❌ Invalid Gmail OAuth state."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # EXCHANGE CODE FOR TOKEN
    # ========================================================

    try:

        flow = get_gmail_flow()

        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials

        # ====================================================
        # CREATE GMAIL SERVICE
        # ====================================================

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        # ====================================================
        # CHECK GMAIL ACCOUNT
        # ====================================================

        profile = (
            service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        gmail_email = profile.get(
            "emailAddress"
        )

        if not gmail_email:

            raise Exception(
                "Google did not return Gmail email address."
            )

        # ====================================================
        # AGENTFORGE USER
        # ====================================================

        logged_in_email = st.user.email
        user_id = st.user.get("sub")

        if not user_id:

            raise Exception(
                "Unable to identify AgentForge user."
            )

        # ====================================================
        # ACCOUNT MATCH
        # ====================================================

        if (
            logged_in_email
            and gmail_email.lower()
            != logged_in_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge account: {logged_in_email}"
            )

            st.warning(
                f"Gmail account: {gmail_email}"
            )

            st.info(
                "Please connect Gmail using the same "
                "Google account used for AgentForge."
            )

            st.query_params.clear()

            return False

        # ====================================================
        # SAVE TOKEN IN SESSION
        # ====================================================

        if "gmail_tokens" not in st.session_state:

            st.session_state["gmail_tokens"] = {}

        st.session_state["gmail_tokens"][user_id] = (
            json.loads(
                credentials.to_json()
            )
        )

        # ====================================================
        # SAVE CONNECTION
        # ====================================================

        st.session_state["gmail_connected"] = True

        st.session_state["gmail_email"] = gmail_email

        st.session_state["gmail_oauth_in_progress"] = False

        st.session_state.pop(
            "gmail_oauth_state",
            None,
        )

        # Remove ?code=...&state=...
        st.query_params.clear()

        st.success(
            f"✅ Gmail connected successfully: {gmail_email}"
        )

        return True

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        st.query_params.clear()

        return False


# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {},
    )

    token_data = gmail_tokens.get(
        user_id
    )

    if not token_data:
        return None

    try:

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                GMAIL_SCOPES,
            )
        )

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return service

    except Exception as e:

        st.error(
            f"❌ Unable to create Gmail service: {e}"
        )

        return None


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    if not st.user.is_logged_in:
        return False

    user_id = st.user.get("sub")

    if not user_id:
        return False

    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {},
    )

    return user_id in gmail_tokens


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {},
    )

    token_data = gmail_tokens.get(
        user_id
    )

    if not token_data:
        return None

    return st.session_state.get(
        "gmail_email"
    )

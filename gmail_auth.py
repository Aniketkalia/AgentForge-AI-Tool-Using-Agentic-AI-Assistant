import json
import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# GMAIL PERMISSIONS
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# CREATE GMAIL OAUTH FLOW
# ============================================================

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
    # Gmail OAuth returns to the APP HOMEPAGE.
    #
    # Do NOT use:
    # /oauth2callback
    #
    # /oauth2callback is used by Streamlit's own st.login().

    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    return flow


# ============================================================
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    # Make sure AgentForge user is logged in
    if not st.user.is_logged_in:
        return None

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email
    )

    # Save OAuth state
    st.session_state["gmail_oauth_state"] = state

    # Mark OAuth as running
    st.session_state["gmail_oauth_in_progress"] = True

    return authorization_url


# ============================================================
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # --------------------------------------------------------
    # No OAuth response
    # --------------------------------------------------------

    if not code and not error:
        return False


    # --------------------------------------------------------
    # Google returned an error
    # --------------------------------------------------------

    if error:

        st.error(
            f"Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # User must be logged into AgentForge
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "Please login to AgentForge before connecting Gmail."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Check authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Gmail authorization code was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Check OAuth state
    # --------------------------------------------------------

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "Gmail OAuth session expired. "
            "Please click 'Connect Gmail' again."
        )

        st.query_params.clear()

        return False


    if state != saved_state:

        st.error(
            "Invalid Gmail OAuth state."
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
            cache_discovery=False
        )


        # ====================================================
        # GET ACTUAL GMAIL ACCOUNT
        # ====================================================

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]


        # ====================================================
        # CURRENT AGENTFORGE USER
        # ====================================================

        logged_in_email = st.user.email

        user_id = st.user.get("sub")


        if not user_id:

            st.error(
                "Unable to identify the logged-in Google user."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SECURITY CHECK
        # ====================================================
        #
        # Gmail account MUST match the account that logged
        # into AgentForge.
        #

        if (
            not logged_in_email
            or gmail_email.lower()
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
                "Please authorize Gmail using the same "
                "Google account that you used to login."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN FOR CURRENT USER
        # ====================================================

        if "gmail_tokens" not in st.session_state:

            st.session_state["gmail_tokens"] = {}


        st.session_state["gmail_tokens"][user_id] = (
            json.loads(
                credentials.to_json()
            )
        )


        # ====================================================
        # SAVE CONNECTION INFO
        # ====================================================

        st.session_state["gmail_connected"] = True

        st.session_state["gmail_email"] = gmail_email


        # OAuth completed
        st.session_state["gmail_oauth_in_progress"] = False

        # Remove OAuth state
        st.session_state.pop(
            "gmail_oauth_state",
            None
        )


        # Remove OAuth query parameters
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
# GET CURRENT USER'S GMAIL SERVICE
# ============================================================

def get_gmail_service():

    # User must be logged in
    if not st.user.is_logged_in:
        return None


    # Get CURRENT AgentForge user's Google ID
    user_id = st.user.get("sub")

    if not user_id:
        return None


    # Get tokens
    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {}
    )


    # IMPORTANT:
    # Only get token belonging to THIS user.
    token_data = gmail_tokens.get(user_id)


    if not token_data:
        return None


    try:

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                GMAIL_SCOPES
            )
        )


        # Build Gmail service
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

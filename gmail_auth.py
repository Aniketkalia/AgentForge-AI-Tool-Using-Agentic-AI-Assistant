import json
import secrets
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
# HELPERS
# ============================================================

def get_user_id():
    """Return the current AgentForge Google user ID."""

    if not st.user.is_logged_in:
        return None

    return st.user.get("sub")


def get_user_email():
    """Return the current AgentForge email."""

    if not st.user.is_logged_in:
        return None

    return st.user.email


# ============================================================
# CREATE OAUTH FLOW
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

    flow.redirect_uri = st.secrets[
        "gmail_oauth"
    ]["redirect_uri"]

    return flow


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    user_id = get_user_id()

    user_email = get_user_email()

    if not user_id or not user_email:
        st.error(
            "Please login to AgentForge first."
        )
        return None

    flow = get_gmail_flow()

    authorization_url, state = (
        flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            login_hint=user_email
        )
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Put state in query parameters.
    #
    # This survives a Streamlit page refresh.
    # --------------------------------------------------------

    st.query_params["gmail_oauth_state"] = state

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
    # No OAuth callback
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
    # AgentForge login required
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "Please login to AgentForge first."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Current AgentForge user
    # --------------------------------------------------------

    user_id = get_user_id()
    logged_in_email = get_user_email()

    if not user_id:

        st.error(
            "Unable to identify AgentForge user."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Google did not return an authorization code."
        )

        st.query_params.clear()

        return False


    # ========================================================
    # GET SAVED STATE
    # ========================================================

    saved_state = params.get(
        "gmail_oauth_state"
    )


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Google callback contains:
    #
    # ?code=...
    # &state=...
    #
    # We stored our state as:
    #
    # gmail_oauth_state
    #
    # So the callback state must match it.
    # --------------------------------------------------------

    if not saved_state:

        st.error(
            "Gmail OAuth state was lost. "
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
            .getProfile(
                userId="me"
            )
            .execute()
        )

        gmail_email = profile[
            "emailAddress"
        ]


        # ====================================================
        # SECURITY CHECK
        # ====================================================

        if (
            not logged_in_email
            or gmail_email.lower()
            != logged_in_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge login: "
                f"{logged_in_email}"
            )

            st.warning(
                f"Gmail account: "
                f"{gmail_email}"
            )

            st.info(
                "Authorize Gmail using the same "
                "Google account used to login "
                "to AgentForge."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # TOKEN DATA
        # ====================================================

        token_data = json.loads(
            credentials.to_json()
        )


        # ====================================================
        # SAVE CURRENT USER TOKEN
        #
        # IMPORTANT:
        #
        # user_id is used as the key.
        #
        # Therefore:
        #
        # User A → User A token
        # User B → User B token
        #
        # ====================================================

        if "gmail_tokens" not in st.session_state:

            st.session_state[
                "gmail_tokens"
            ] = {}


        st.session_state[
            "gmail_tokens"
        ][user_id] = token_data


        # ====================================================
        # SAVE CONNECTION INFORMATION
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email


        # ====================================================
        # CLEAR CALLBACK PARAMETERS
        # ====================================================

        st.query_params.clear()


        st.success(
            f"✅ Gmail connected: "
            f"{gmail_email}"
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

    user_id = get_user_id()

    if not user_id:
        return None


    # --------------------------------------------------------
    # Get token belonging ONLY to current user
    # --------------------------------------------------------

    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {}
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
                GMAIL_SCOPES
            )
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

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
# GET GMAIL OAUTH CONFIG
# ============================================================

def get_gmail_config():

    if "gmail_oauth" not in st.secrets:

        raise RuntimeError(
            "Missing [gmail_oauth] section in Streamlit secrets."
        )

    gmail_config = st.secrets["gmail_oauth"]

    required = [
        "client_id",
        "client_secret",
        "redirect_uri",
    ]

    for key in required:

        if key not in gmail_config:

            raise RuntimeError(
                f"Missing '{key}' inside [gmail_oauth] "
                "in Streamlit secrets."
            )

    return {
        "client_id": gmail_config["client_id"],
        "client_secret": gmail_config["client_secret"],
        "redirect_uri": gmail_config["redirect_uri"],
    }


# ============================================================
# CREATE OAUTH FLOW
# ============================================================

def get_gmail_flow():

    config_data = get_gmail_config()

    config = {
        "web": {
            "client_id": config_data["client_id"],
            "client_secret": config_data["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
    )

    flow.redirect_uri = config_data["redirect_uri"]

    return flow


# ============================================================
# START GMAIL AUTHORIZATION
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:

        raise RuntimeError(
            "You must login to AgentForge first."
        )

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email,
    )

    # Save state in Streamlit session
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
    # Nothing to process
    # --------------------------------------------------------

    if not code and not error:

        return False


    # --------------------------------------------------------
    # Google returned error
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
            "❌ AgentForge login session is missing."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "❌ Google authorization code was not received."
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
            "❌ Gmail OAuth state is missing or expired. "
            "Please click Connect Gmail again."
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
        # BUILD GMAIL SERVICE
        # ====================================================

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )


        # ====================================================
        # GET GMAIL PROFILE
        # ====================================================

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile.get(
            "emailAddress"
        )


        if not gmail_email:

            raise RuntimeError(
                "Unable to determine Gmail email address."
            )


        # ====================================================
        # AGENTFORGE USER
        # ====================================================

        logged_in_email = st.user.email

        user_id = st.user.get("sub")


        if not user_id:

            raise RuntimeError(
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
                "Use the same Google account for "
                "AgentForge and Gmail."
            )

            st.query_params.clear()

            st.session_state.pop(
                "gmail_oauth_state",
                None,
            )

            return False


        # ====================================================
        # STORE TOKEN IN SESSION
        # ====================================================

        if "gmail_tokens" not in st.session_state:

            st.session_state["gmail_tokens"] = {}


        token_json = json.loads(
            credentials.to_json()
        )


        st.session_state["gmail_tokens"][user_id] = (
            token_json
        )


        # ====================================================
        # STORE CONNECTION STATUS
        # ====================================================

        st.session_state["gmail_connected"] = True

        st.session_state["gmail_email"] = gmail_email

        st.session_state["gmail_oauth_in_progress"] = False


        # Remove OAuth state

        st.session_state.pop(
            "gmail_oauth_state",
            None,
        )


        # Remove URL parameters

        st.query_params.clear()


        return True


    except Exception as e:

        st.session_state["gmail_oauth_in_progress"] = False

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
# CONNECTION CHECK
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

    token_data = gmail_tokens.get(
        user_id
    )

    if not token_data:

        return False

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

        service.users().getProfile(
            userId="me"
        ).execute()

        return True

    except Exception:

        return False


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


        profile = (
            service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )


        return profile.get(
            "emailAddress"
        )


    except Exception:

        return None

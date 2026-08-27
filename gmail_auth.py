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
# GET GMAIL OAUTH FLOW
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
    # This MUST be the SAME redirect URI configured
    # in Google Cloud Console for this Gmail OAuth client.
    #
    # Example:
    # https://agentforge-ai-tool-using-agentic-ai-assistant-bxq2braoxb5b6yfa.streamlit.app/
    #
    flow.redirect_uri = st.secrets[
        "gmail_oauth"
    ]["redirect_uri"]

    return flow


# ============================================================
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    # User must already be logged into AgentForge
    if not st.user.is_logged_in:

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
            login_hint=st.user.email
        )
    )

    # Save OAuth state
    st.session_state[
        "gmail_oauth_state"
    ] = state

    return authorization_url


# ============================================================
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    # --------------------------------------------------------
    # Make sure user is logged in
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "AgentForge login session is missing. "
            "Please login again."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Get current user
    # --------------------------------------------------------

    logged_in_email = st.user.email

    user_id = st.user.get("sub")


    if not user_id:

        st.error(
            "Unable to identify logged-in Google user."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Read OAuth parameters
    # --------------------------------------------------------

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")


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
    # No authorization code
    # --------------------------------------------------------

    if not code:

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
            "Please click 'Connect My Gmail' again."
        )

        st.query_params.clear()

        return False


    if state != saved_state:

        st.error(
            "Invalid Gmail OAuth state. "
            "Please connect Gmail again."
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
        #
        # The Gmail account selected on Google MUST
        # match the Google account currently logged
        # into AgentForge.
        #
        # This prevents:
        #
        # User A login
        # +
        # User B Gmail
        #
        # from being connected.
        #

        if (
            gmail_email.lower()
            !=
            logged_in_email.lower()
        ):

            st.error(
                "❌ Google account mismatch.\n\n"
                f"AgentForge account: {logged_in_email}\n\n"
                f"Gmail account: {gmail_email}\n\n"
                "Please select the same Google account "
                "that you used to login to AgentForge."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # INITIALIZE USER-SPECIFIC STORAGE
        # ====================================================

        if (
            "gmail_tokens"
            not in st.session_state
        ):

            st.session_state[
                "gmail_tokens"
            ] = {}


        if (
            "gmail_emails"
            not in st.session_state
        ):

            st.session_state[
                "gmail_emails"
            ] = {}


        # ====================================================
        # SAVE TOKEN FOR CURRENT USER
        # ====================================================

        token_data = json.loads(
            credentials.to_json()
        )


        st.session_state[
            "gmail_tokens"
        ][user_id] = token_data


        # ====================================================
        # SAVE EMAIL FOR CURRENT USER
        # ====================================================

        st.session_state[
            "gmail_emails"
        ][user_id] = gmail_email


        # ====================================================
        # COMPATIBILITY VALUES
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True


        st.session_state[
            "gmail_email"
        ] = gmail_email


        # ====================================================
        # REMOVE USED OAUTH STATE
        # ====================================================

        st.session_state.pop(
            "gmail_oauth_state",
            None
        )


        # ====================================================
        # CLEAR GOOGLE CALLBACK PARAMETERS
        # ====================================================

        st.query_params.clear()


        # ====================================================
        # SUCCESS
        # ====================================================

        st.success(
            f"✅ Gmail connected successfully!\n\n"
            f"Connected account: {gmail_email}"
        )


        return True


    # ========================================================
    # ERROR
    # ========================================================

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed:\n\n{e}"
        )

        st.query_params.clear()

        return False


# ============================================================
# GET CURRENT USER'S GMAIL SERVICE
# ============================================================

def get_current_gmail_service():

    # --------------------------------------------------------
    # Make sure AgentForge user is logged in
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        return None


    # --------------------------------------------------------
    # Get CURRENT AgentForge user
    # --------------------------------------------------------

    user_id = st.user.get("sub")


    if not user_id:

        return None


    # --------------------------------------------------------
    # Get user-specific tokens
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


    # ========================================================
    # CREATE CREDENTIALS
    # ========================================================

    try:

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                scopes=GMAIL_SCOPES
            )
        )


        # ====================================================
        # CREATE GMAIL API SERVICE
        # ====================================================

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


# ============================================================
# GET CURRENT USER'S GMAIL EMAIL
# ============================================================

def get_current_gmail_email():

    if not st.user.is_logged_in:

        return None


    user_id = st.user.get("sub")


    if not user_id:

        return None


    gmail_emails = st.session_state.get(
        "gmail_emails",
        {}
    )


    return gmail_emails.get(
        user_id
    )


# ============================================================
# CHECK WHETHER CURRENT USER IS CONNECTED
# ============================================================

def is_gmail_connected():

    if not st.user.is_logged_in:

        return False


    user_id = st.user.get("sub")


    if not user_id:

        return False


    gmail_tokens = st.session_state.get(
        "gmail_tokens",
        {}
    )


    return user_id in gmail_tokens

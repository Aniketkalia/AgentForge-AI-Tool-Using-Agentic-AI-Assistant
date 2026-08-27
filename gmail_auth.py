import json
import secrets

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
# PERSISTENT APP STORAGE
# ============================================================

@st.cache_resource
def get_gmail_store():
    return {
        "oauth_states": {},
        "tokens": {},
        "emails": {},
    }


# ============================================================
# REDIRECT URI
# ============================================================

def get_redirect_uri():

    return st.secrets[
        "gmail_oauth"
    ][
        "redirect_uri"
    ].rstrip("/")


# ============================================================
# CREATE GMAIL OAUTH FLOW
# ============================================================

def get_gmail_flow(state=None):

    config = {
        "web": {
            "client_id": st.secrets[
                "gmail_oauth"
            ]["client_id"],

            "client_secret": st.secrets[
                "gmail_oauth"
            ]["client_secret"],

            "auth_uri":
                "https://accounts.google.com/o/oauth2/v2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
        state=state,
    )

    # IMPORTANT:
    # Gmail OAuth uses homepage.
    # Do NOT use /oauth2callback here.

    flow.redirect_uri = get_redirect_uri()

    return flow


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    store = get_gmail_store()

    # Generate OAuth state
    state = secrets.token_urlsafe(32)

    flow = get_gmail_flow(
        state=state
    )

    authorization_url, generated_state = (
        flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            login_hint=st.user.email,
        )
    )

    # Store state outside session_state
    store["oauth_states"][user_id] = (
        generated_state
    )

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
            f"❌ Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # AgentForge login required
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "❌ Please login to AgentForge first."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Validate code
    # --------------------------------------------------------

    if not code:

        st.error(
            "❌ Gmail authorization code missing."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Validate state
    # --------------------------------------------------------

    if not state:

        st.error(
            "❌ Gmail OAuth state missing."
        )

        st.query_params.clear()

        return False


    user_id = st.user.get("sub")

    if not user_id:

        st.error(
            "❌ Unable to identify AgentForge user."
        )

        st.query_params.clear()

        return False


    store = get_gmail_store()

    saved_state = store[
        "oauth_states"
    ].get(user_id)


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
    # EXCHANGE AUTHORIZATION CODE
    # ========================================================

    try:

        flow = get_gmail_flow(
            state=state
        )

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
                "Google did not return Gmail email."
            )


        # ====================================================
        # CHECK SAME ACCOUNT
        # ====================================================

        logged_in_email = st.user.email


        if (
            not logged_in_email
            or
            gmail_email.lower()
            !=
            logged_in_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge: {logged_in_email}"
            )

            st.warning(
                f"Gmail: {gmail_email}"
            )

            st.info(
                "Use the same Google account for "
                "AgentForge and Gmail."
            )

            store[
                "oauth_states"
            ].pop(
                user_id,
                None
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN
        # ====================================================

        token_data = json.loads(
            credentials.to_json()
        )

        store[
            "tokens"
        ][user_id] = token_data


        # ====================================================
        # SAVE EMAIL
        # ====================================================

        store[
            "emails"
        ][user_id] = gmail_email


        # ====================================================
        # REMOVE USED STATE
        # ====================================================

        store[
            "oauth_states"
        ].pop(
            user_id,
            None
        )


        # ====================================================
        # SESSION CACHE
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email


        # ====================================================
        # CLEAR CALLBACK
        # ====================================================

        st.query_params.clear()


        st.success(
            f"✅ Gmail connected: {gmail_email}"
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

    store = get_gmail_store()

    token_data = store[
        "tokens"
    ].get(user_id)


    if not token_data:
        return None


    try:

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                GMAIL_SCOPES,
            )
        )


        # ====================================================
        # REFRESH EXPIRED TOKEN
        # ====================================================

        if (
            credentials.expired
            and
            credentials.refresh_token
        ):

            from google.auth.transport.requests import (
                Request
            )

            credentials.refresh(
                Request()
            )

            # Save refreshed token
            store[
                "tokens"
            ][user_id] = json.loads(
                credentials.to_json()
            )


        # ====================================================
        # BUILD SERVICE
        # ====================================================

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

    store = get_gmail_store()

    return (
        user_id
        in store["tokens"]
    )


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    store = get_gmail_store()

    return store[
        "emails"
    ].get(user_id)


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail():

    if not st.user.is_logged_in:
        return

    user_id = st.user.get("sub")

    if not user_id:
        return

    store = get_gmail_store()

    store[
        "tokens"
    ].pop(
        user_id,
        None
    )

    store[
        "emails"
    ].pop(
        user_id,
        None
    )

    store[
        "oauth_states"
    ].pop(
        user_id,
        None
    )

    st.session_state.pop(
        "gmail_connected",
        None
    )

    st.session_state.pop(
        "gmail_email",
        None
    )

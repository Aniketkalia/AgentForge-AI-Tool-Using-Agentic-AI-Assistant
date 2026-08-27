import json
import os
import sqlite3
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
# DATABASE
# ============================================================

DB_FILE = "gmail_tokens.db"


def init_database():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            token_json TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


init_database()


# ============================================================
# SAVE TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    email,
    credentials
):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    token_json = credentials.to_json()

    cursor.execute(
        """
        INSERT OR REPLACE INTO gmail_tokens
        (user_id, email, token_json)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            email,
            token_json
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# LOAD TOKEN
# ============================================================

def load_gmail_token(user_id):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT email, token_json
        FROM gmail_tokens
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    conn.close()

    if not row:
        return None, None

    email, token_json = row

    return email, token_json


# ============================================================
# DELETE TOKEN
# ============================================================

def delete_gmail_token(user_id):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM gmail_tokens
        WHERE user_id = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# CREATE OAUTH FLOW
# ============================================================

def get_gmail_flow():

    client_id = st.secrets["gmail_oauth"]["client_id"]

    client_secret = st.secrets["gmail_oauth"]["client_secret"]

    redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,

            "auth_uri":
                "https://accounts.google.com/o/oauth2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",

            "redirect_uris": [
                redirect_uri
            ]
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES
    )

    flow.redirect_uri = redirect_uri

    return flow


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:

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

    # Save state
    st.session_state["gmail_oauth_state"] = state

    return authorization_url


# ============================================================
# HANDLE CALLBACK
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
    # Google error
    # --------------------------------------------------------

    if error:

        st.error(
            f"Google Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # AgentForge login
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "AgentForge login session is not available."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Google authorization code was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "OAuth session expired. "
            "Please click Connect Gmail again."
        )

        st.query_params.clear()

        return False


    if state != saved_state:

        st.error(
            "Invalid OAuth state."
        )

        st.query_params.clear()

        return False


    # ========================================================
    # EXCHANGE CODE
    # ========================================================

    try:

        flow = get_gmail_flow()

        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials


        # ====================================================
        # CREATE SERVICE
        # ====================================================

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
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

        gmail_email = profile["emailAddress"]


        # ====================================================
        # CURRENT AGENTFORGE USER
        # ====================================================

        user_id = st.user.get("sub")

        logged_in_email = st.user.email


        if not user_id:

            st.error(
                "Unable to identify AgentForge user."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # ACCOUNT MATCH
        # ====================================================

        if (
            gmail_email.lower()
            != logged_in_email.lower()
        ):

            st.error(
                "Google account mismatch."
            )

            st.write(
                f"AgentForge account: {logged_in_email}"
            )

            st.write(
                f"Gmail account: {gmail_email}"
            )

            st.info(
                "Use the same Google account "
                "for AgentForge and Gmail."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN TO DATABASE
        # ====================================================

        save_gmail_token(
            user_id=user_id,
            email=gmail_email,
            credentials=credentials
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


        # Remove OAuth state
        st.session_state.pop(
            "gmail_oauth_state",
            None
        )


        # Remove URL parameters
        st.query_params.clear()


        return True


    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        st.query_params.clear()

        return False


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    if not st.user.is_logged_in:

        return False

    user_id = st.user.get("sub")

    if not user_id:

        return False

    email, token_json = load_gmail_token(
        user_id
    )

    return token_json is not None


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:

        return None

    user_id = st.user.get("sub")

    if not user_id:

        return None

    email, token_json = load_gmail_token(
        user_id
    )

    return email


# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service():

    if not st.user.is_logged_in:

        return None

    user_id = st.user.get("sub")

    if not user_id:

        return None


    email, token_json = load_gmail_token(
        user_id
    )

    if not token_json:

        return None


    try:

        token_data = json.loads(
            token_json
        )

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


# ============================================================
# CURRENT USER GMAIL SERVICE
# ============================================================

def get_current_gmail_service():

    return get_gmail_service()


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail():

    if not st.user.is_logged_in:

        return

    user_id = st.user.get("sub")

    if not user_id:

        return


    delete_gmail_token(
        user_id
    )


    st.session_state.pop(
        "gmail_connected",
        None
    )

    st.session_state.pop(
        "gmail_email",
        None
    )

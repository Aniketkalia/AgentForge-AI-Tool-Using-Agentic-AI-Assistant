# gmail_auth.py

import json
import sqlite3
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

DB_PATH = Path("gmail_tokens.db")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            token_json TEXT NOT NULL
        )
        """
    )

    conn.commit()

    return conn


# ============================================================
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    email,
    token_json
):

    conn = get_db_connection()

    conn.execute(
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
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    conn = get_db_connection()

    cursor = conn.execute(
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

    conn = get_db_connection()

    conn.execute(
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
        }
    }

    # IMPORTANT:
    #
    # Disable automatic PKCE.
    #
    # Your previous code generated a code_challenge
    # during authorization but then created a new Flow
    # during callback without the original code_verifier.
    #
    # That caused:
    #
    # invalid_grant: Missing code verifier
    #
    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
        autogenerate_code_verifier=False
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

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email
    )

    # Store OAuth state
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
    # Google OAuth error
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
    # Authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Google authorization code was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Validate OAuth state
    # --------------------------------------------------------

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "OAuth session expired. "
            "Please click Connect My Gmail again."
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

        # IMPORTANT:
        #
        # Since PKCE is disabled, there is no
        # missing code_verifier problem.
        #
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
            cache_discovery=False
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

            raise Exception(
                "Could not determine Gmail account."
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
        # ACCOUNT SECURITY CHECK
        # ====================================================

        if (
            not logged_in_email
            or
            gmail_email.lower()
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

            return False


        # ====================================================
        # SAVE TOKEN PERMANENTLY
        # ====================================================

        token_json = credentials.to_json()

        save_gmail_token(
            user_id=user_id,
            email=gmail_email,
            token_json=token_json
        )


        # ====================================================
        # UPDATE SESSION
        # ====================================================

        st.session_state["gmail_connected"] = True

        st.session_state["gmail_email"] = gmail_email

        st.session_state["gmail_oauth_in_progress"] = False


        st.session_state.pop(
            "gmail_oauth_state",
            None
        )


        # ====================================================
        # REMOVE CALLBACK PARAMETERS
        # ====================================================

        st.query_params.clear()

        return True


    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
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

    return (
        email is not None
        and token_json is not None
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


        # ----------------------------------------------------
        # Refresh expired access token automatically
        # ----------------------------------------------------

        if credentials.expired and credentials.refresh_token:

            from google.auth.transport.requests import Request

            credentials.refresh(
                Request()
            )

            # Save refreshed token
            save_gmail_token(
                user_id=user_id,
                email=email,
                token_json=credentials.to_json()
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
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail():

    if not st.user.is_logged_in:
        return

    user_id = st.user.get("sub")

    if user_id:

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

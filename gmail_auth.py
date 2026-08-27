# ============================================================
# gmail_auth.py
# ============================================================

import json
import secrets
import sqlite3
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

DB_PATH = Path("gmail_tokens_v3.db")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False
    )

    # Gmail token table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            token_json TEXT NOT NULL
        )
        """
    )

    # OAuth state table
    #
    # IMPORTANT:
    # OAuth state is stored in SQLite instead of
    # st.session_state.
    #
    # This allows the callback to work even if Google
    # opens the OAuth flow in another browser tab/session.
    #
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL
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
        (
            user_id,
            email,
            token_json
        )
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
        SELECT
            email,
            token_json
        FROM gmail_tokens
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None, None

    return row[0], row[1]


# ============================================================
# DELETE GMAIL TOKEN
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
# SAVE OAUTH STATE
# ============================================================

def save_oauth_state(
    state,
    user_id,
    email
):

    conn = get_db_connection()

    conn.execute(
        """
        INSERT OR REPLACE INTO gmail_oauth_states
        (
            state,
            user_id,
            email
        )
        VALUES (?, ?, ?)
        """,
        (
            state,
            user_id,
            email
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def load_oauth_state(state):

    conn = get_db_connection()

    cursor = conn.execute(
        """
        SELECT
            user_id,
            email
        FROM gmail_oauth_states
        WHERE state = ?
        """,
        (state,)
    )

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return None, None

    return row[0], row[1]


# ============================================================
# DELETE OAUTH STATE
# ============================================================

def delete_oauth_state(state):

    conn = get_db_connection()

    conn.execute(
        """
        DELETE FROM gmail_oauth_states
        WHERE state = ?
        """,
        (state,)
    )

    conn.commit()
    conn.close()


# ============================================================
# CREATE GMAIL OAUTH FLOW
# ============================================================

def get_gmail_flow():

    client_id = st.secrets[
        "gmail_oauth"
    ][
        "client_id"
    ]

    client_secret = st.secrets[
        "gmail_oauth"
    ][
        "client_secret"
    ]

    redirect_uri = st.secrets[
        "gmail_oauth"
    ][
        "redirect_uri"
    ]

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": (
                "https://accounts.google.com/"
                "o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
        }
    }

    # ========================================================
    # IMPORTANT
    # ========================================================
    #
    # PKCE is disabled.
    #
    # Previously Google returned:
    #
    # invalid_grant: Missing code verifier
    #
    # because the authorization Flow and callback Flow
    # were different objects.
    #
    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
        autogenerate_code_verifier=False
    )

    flow.redirect_uri = redirect_uri

    return flow


# ============================================================
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")
    user_email = st.user.email

    if not user_id:
        return None

    flow = get_gmail_flow()

    # ========================================================
    # CREATE OUR OWN STATE
    # ========================================================

    state = secrets.token_urlsafe(32)

    # ========================================================
    # SAVE STATE IN SQLITE
    #
    # NOT st.session_state
    #
    # This survives Streamlit reruns and allows callback
    # from another browser tab/session.
    # ========================================================

    save_oauth_state(
        state=state,
        user_id=user_id,
        email=user_email
    )

    # ========================================================
    # CREATE GOOGLE AUTHORIZATION URL
    # ========================================================

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=user_email,
        state=state
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

    # ========================================================
    # NO OAUTH RESPONSE
    # ========================================================

    if not code and not error:
        return False

    # ========================================================
    # GOOGLE ERROR
    # ========================================================

    if error:

        st.error(
            f"❌ Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False

    # ========================================================
    # CHECK CODE
    # ========================================================

    if not code:

        st.error(
            "❌ Google authorization code was not received."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # CHECK STATE
    # ========================================================

    if not state:

        st.error(
            "❌ OAuth state was not received."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # LOAD STATE FROM DATABASE
    # ========================================================

    oauth_user_id, oauth_email = load_oauth_state(
        state
    )

    if not oauth_user_id:

        st.error(
            "❌ OAuth session expired or invalid."
        )

        st.info(
            "Please click Connect My Gmail again."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # REMOVE USED STATE
    # ========================================================

    delete_oauth_state(state)

    # ========================================================
    # CURRENT AGENTFORGE USER
    # ========================================================

    if not st.user.is_logged_in:

        st.error(
            "❌ Please login to AgentForge first."
        )

        st.query_params.clear()

        return False

    current_user_id = st.user.get("sub")
    current_email = st.user.email

    # ========================================================
    # SECURITY CHECK
    # ========================================================

    if (
        not current_user_id
        or current_user_id != oauth_user_id
    ):

        st.error(
            "❌ AgentForge user changed during Gmail "
            "authorization."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # EMAIL CHECK
    # ========================================================

    if (
        oauth_email
        and current_email
        and oauth_email.lower()
        != current_email.lower()
    ):

        st.error(
            "❌ AgentForge account changed during "
            "Gmail authorization."
        )

        st.query_params.clear()

        return False

    # ========================================================
    # TOKEN EXCHANGE
    # ========================================================

    try:

        flow = get_gmail_flow()

        # ====================================================
        # IMPORTANT
        # ====================================================
        #
        # PKCE is disabled, so this does NOT require
        # a code_verifier.
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
        # GET GMAIL ACCOUNT
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
                "Unable to determine Gmail email address."
            )

        # ====================================================
        # ACCOUNT MATCH
        # ====================================================

        if (
            not current_email
            or gmail_email.lower()
            != current_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge account: {current_email}"
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
        # SAVE TOKEN
        # ====================================================

        token_json = credentials.to_json()

        save_gmail_token(
            user_id=current_user_id,
            email=gmail_email,
            token_json=token_json
        )

        # ====================================================
        # UPDATE SESSION
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email

        # ====================================================
        # CLEAN OAUTH SESSION
        # ====================================================

        st.session_state.pop(
            "gmail_oauth_state",
            None
        )

        st.session_state.pop(
            "gmail_oauth_in_progress",
            None
        )

        # ====================================================
        # REMOVE CODE + STATE FROM URL
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

    try:

        email, token_json = load_gmail_token(
            user_id
        )

        return (
            email is not None
            and token_json is not None
        )

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

    try:

        email, token_json = load_gmail_token(
            user_id
        )

        return email

    except Exception:

        return None


# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    try:

        email, token_json = load_gmail_token(
            user_id
        )

        if not token_json:
            return None

        token_data = json.loads(
            token_json
        )

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                GMAIL_SCOPES
            )
        )

        # ====================================================
        # REFRESH EXPIRED ACCESS TOKEN
        # ====================================================

        if (
            credentials.expired
            and credentials.refresh_token
        ):

            from google.auth.transport.requests import (
                Request
            )

            credentials.refresh(
                Request()
            )

            # Save refreshed credentials
            save_gmail_token(
                user_id=user_id,
                email=email,
                token_json=credentials.to_json()
            )

        # ====================================================
        # BUILD SERVICE
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
            f"❌ Unable to create Gmail service: {e}"
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

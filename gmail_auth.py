import json
import sqlite3
import secrets
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "gmail_tokens.db"


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_tokens (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()

    finally:

        conn.close()


# Initialize database when module loads
init_db()


# ============================================================
# OAUTH CONFIG
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
        scopes=GMAIL_SCOPES,
    )

    # IMPORTANT
    #
    # This must be the SAME URL configured in
    # Google Cloud Console.
    #
    # Example:
    #
    # https://your-app.streamlit.app/
    #
    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

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

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=st.user.email,
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Save state in SQLite, NOT session_state.
    #
    # OAuth callback can create a NEW Streamlit session.
    # --------------------------------------------------------

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT OR REPLACE INTO gmail_oauth_states
            (state, user_id)
            VALUES (?, ?)
            """,
            (
                state,
                user_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()

    return authorization_url


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def get_oauth_user(state):

    conn = get_db()

    try:

        row = conn.execute(
            """
            SELECT user_id
            FROM gmail_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()

        if row:
            return row["user_id"]

        return None

    finally:

        conn.close()


# ============================================================
# DELETE OAUTH STATE
# ============================================================

def delete_oauth_state(state):

    conn = get_db()

    try:

        conn.execute(
            """
            DELETE FROM gmail_oauth_states
            WHERE state = ?
            """,
            (state,),
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # --------------------------------------------------------
    # No Gmail callback
    # --------------------------------------------------------

    if not code and not error:
        return False


    # --------------------------------------------------------
    # Google returned error
    # --------------------------------------------------------

    if error:

        st.error(
            f"Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Missing code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Gmail authorization code was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Missing state
    # --------------------------------------------------------

    if not state:

        st.error(
            "Gmail OAuth state was not received."
        )

        st.query_params.clear()

        return False


    # ========================================================
    # FIND USER FROM DATABASE
    # ========================================================

    user_id = get_oauth_user(state)

    if not user_id:

        st.error(
            "Gmail OAuth session expired or is invalid. "
            "Please click Connect Gmail again."
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
        # GET GMAIL ACCOUNT
        # ====================================================

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]


        # ====================================================
        # CHECK LOGGED-IN AGENTFORGE USER
        # ====================================================

        logged_in_email = None

        if st.user.is_logged_in:

            logged_in_email = st.user.email


        # ====================================================
        # SECURITY CHECK
        # ====================================================

        if (
            logged_in_email
            and gmail_email.lower()
            != logged_in_email.lower()
        ):

            delete_oauth_state(state)

            st.error(
                "❌ Google account mismatch."
            )

            st.write(
                f"AgentForge account: {logged_in_email}"
            )

            st.write(
                f"Gmail account: {gmail_email}"
            )

            st.info(
                "Please authorize Gmail using the "
                "same Google account."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN TO SQLITE
        # ====================================================

        token_json = credentials.to_json()

        conn = get_db()

        try:

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
                    gmail_email,
                    token_json,
                ),
            )

            conn.commit()

        finally:

            conn.close()


        # ====================================================
        # DELETE USED OAUTH STATE
        # ====================================================

        delete_oauth_state(state)


        # ====================================================
        # CLEAR URL
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
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    if not user_id:
        return None, None

    init_db()

    conn = get_db()

    try:

        row = conn.execute(
            """
            SELECT email, token_json
            FROM gmail_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if not row:

            return None, None

        return (
            row["email"],
            row["token_json"],
        )

    finally:

        conn.close()


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

        if not token_json:
            return False

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(token_json),
                GMAIL_SCOPES,
            )
        )

        # Check credentials by creating service
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

    try:

        email, token_json = load_gmail_token(
            user_id
        )

        if not token_json:
            return None

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

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(token_json),
                GMAIL_SCOPES,
            )
        )

        # ----------------------------------------------------
        # Refresh expired token automatically
        # ----------------------------------------------------

        if credentials.expired and credentials.refresh_token:

            from google.auth.transport.requests import Request

            credentials.refresh(
                Request()
            )

            # Save refreshed credentials
            conn = get_db()

            try:

                conn.execute(
                    """
                    UPDATE gmail_tokens
                    SET token_json = ?
                    WHERE user_id = ?
                    """,
                    (
                        credentials.to_json(),
                        user_id,
                    ),
                )

                conn.commit()

            finally:

                conn.close()


        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return service

    except Exception as e:

        st.error(
            f"Gmail service error: {e}"
        )

        return None


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail():

    if not st.user.is_logged_in:
        return

    user_id = st.user.get("sub")

    if not user_id:
        return

    conn = get_db()

    try:

        conn.execute(
            """
            DELETE FROM gmail_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        )

        conn.commit()

    finally:

        conn.close()

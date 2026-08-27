# ============================================================
# gmail_auth.py
# AgentForge Gmail OAuth
# ============================================================

import json
import sqlite3
import secrets
import time
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

# Use a NEW database so old broken schemas are not reused.
DB_PATH = Path("agentforge_gmail_v3.db")

# IMPORTANT:
# Only request the Gmail permission actually required.
# Do NOT add userinfo.profile / userinfo.email / openid here.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# DATABASE
# ============================================================

def get_db():
    """
    Open SQLite database and make sure the required tables exist.
    """

    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    # --------------------------------------------------------
    # Gmail tokens
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            token_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # OAuth temporary state
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            user_email TEXT NOT NULL,
            code_verifier TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )

    conn.commit()

    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_tokens (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )

        conn.commit()

    finally:

        conn.close()


# Initialize DB when module loads
init_db()


# ============================================================
# CURRENT USER HELPERS
# ============================================================

def get_current_user_id():

    try:

        if not st.user.is_logged_in:
            return None

        return st.user.get("sub")

    except Exception:

        return None


def get_current_user_email():

    try:

        if not st.user.is_logged_in:
            return None

        return st.user.email

    except Exception:

        return None


# ============================================================
# GOOGLE OAUTH FLOW
# ============================================================

def get_gmail_flow(code_verifier=None):

    oauth_config = st.secrets["gmail_oauth"]

    client_id = oauth_config["client_id"]
    client_secret = oauth_config["client_secret"]
    redirect_uri = oauth_config["redirect_uri"]

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

    # --------------------------------------------------------
    # IMPORTANT:
    # PKCE verifier is explicitly supplied.
    # --------------------------------------------------------

    flow = Flow.from_client_config(

        config,

        scopes=GMAIL_SCOPES,

        code_verifier=code_verifier

    )

    flow.redirect_uri = redirect_uri

    return flow


# ============================================================
# SAVE OAUTH STATE
# ============================================================

def save_oauth_state(
    state,
    user_id,
    user_email,
    code_verifier
):

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT OR REPLACE INTO gmail_oauth_states
            (
                state,
                user_id,
                user_email,
                code_verifier,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state,
                user_id,
                user_email,
                code_verifier,
                time.time()
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def load_oauth_state(state):

    conn = get_db()

    try:

        cursor = conn.execute(
            """
            SELECT
                state,
                user_id,
                user_email,
                code_verifier,
                created_at
            FROM gmail_oauth_states
            WHERE state = ?
            """,
            (state,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        conn.close()


# ============================================================
# DELETE OAUTH STATE
# ============================================================

def delete_oauth_state(state):

    if not state:
        return

    conn = get_db()

    try:

        conn.execute(
            """
            DELETE FROM gmail_oauth_states
            WHERE state = ?
            """,
            (state,)
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# CLEAN OLD OAUTH STATES
# ============================================================

def cleanup_old_oauth_states():

    conn = get_db()

    try:

        cutoff = time.time() - 900

        conn.execute(
            """
            DELETE FROM gmail_oauth_states
            WHERE created_at < ?
            """,
            (cutoff,)
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    email,
    token_json
):

    if not user_id:
        return False

    conn = get_db()

    now = time.time()

    try:

        conn.execute(
            """
            INSERT INTO gmail_tokens
            (
                user_id,
                email,
                token_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET

                email = excluded.email,

                token_json =
                    excluded.token_json,

                updated_at =
                    excluded.updated_at
            """,
            (
                user_id,
                email,
                token_json,
                now,
                now
            )
        )

        conn.commit()

        return True

    finally:

        conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    if not user_id:
        return None, None

    conn = get_db()

    try:

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

        if row is None:

            return None, None

        return (
            row["email"],
            row["token_json"]
        )

    finally:

        conn.close()


# ============================================================
# DELETE GMAIL TOKEN
# ============================================================

def delete_gmail_token(user_id):

    if not user_id:
        return

    conn = get_db()

    try:

        conn.execute(
            """
            DELETE FROM gmail_tokens
            WHERE user_id = ?
            """,
            (user_id,)
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:

        return None

    user_id = get_current_user_id()
    user_email = get_current_user_email()

    if not user_id or not user_email:

        st.error(
            "Unable to identify the logged-in Google user."
        )

        return None

    try:

        cleanup_old_oauth_states()

        # ----------------------------------------------------
        # Generate PKCE verifier
        # ----------------------------------------------------

        code_verifier = secrets.token_urlsafe(64)

        # ----------------------------------------------------
        # Create OAuth flow
        # ----------------------------------------------------

        flow = get_gmail_flow(
            code_verifier=code_verifier
        )

        # ----------------------------------------------------
        # Generate authorization URL
        # ----------------------------------------------------

        authorization_url, state = (
            flow.authorization_url(

                access_type="offline",

                prompt="consent",

                # IMPORTANT:
                # Don't merge old scopes.
                include_granted_scopes="false",

                login_hint=user_email
            )
        )

        # ----------------------------------------------------
        # Save OAuth state in SQLite
        #
        # This is important because the browser returns to
        # Streamlit as a new request.
        # ----------------------------------------------------

        save_oauth_state(
            state=state,
            user_id=user_id,
            user_email=user_email,
            code_verifier=code_verifier
        )

        return authorization_url

    except Exception as e:

        st.error(
            f"OAuth setup error: {e}"
        )

        return None


# ============================================================
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

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
    # No callback
    # --------------------------------------------------------

    if not code:

        return False

    # --------------------------------------------------------
    # State missing
    # --------------------------------------------------------

    if not state:

        st.error(
            "Gmail OAuth state was not received."
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # AgentForge login check
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "Please login to AgentForge first."
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # Load OAuth state
    # --------------------------------------------------------

    oauth_state = load_oauth_state(state)

    if oauth_state is None:

        st.error(
            "Gmail OAuth session expired. "
            "Please click Connect My Gmail again."
        )

        st.query_params.clear()

        return False

    current_user_id = get_current_user_id()
    current_user_email = get_current_user_email()

    # --------------------------------------------------------
    # Verify user
    # --------------------------------------------------------

    if oauth_state["user_id"] != current_user_id:

        st.error(
            "OAuth user mismatch."
        )

        delete_oauth_state(state)

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # Get PKCE verifier
    # --------------------------------------------------------

    code_verifier = oauth_state["code_verifier"]

    # ========================================================
    # EXCHANGE CODE
    # ========================================================

    try:

        flow = get_gmail_flow(
            code_verifier=code_verifier
        )

        flow.fetch_token(
            code=code,
            code_verifier=code_verifier
        )

        credentials = flow.credentials

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Do NOT call Gmail getProfile().
        #
        # gmail.send permission does not grant profile access.
        #
        # We already know the Gmail account from st.user.email.
        # ----------------------------------------------------

        gmail_email = current_user_email

        if not gmail_email:

            raise Exception(
                "Unable to determine Gmail email."
            )

        # ----------------------------------------------------
        # Save token
        # ----------------------------------------------------

        save_gmail_token(
            user_id=current_user_id,
            email=gmail_email,
            token_json=credentials.to_json()
        )

        # ----------------------------------------------------
        # Session
        # ----------------------------------------------------

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email

        # ----------------------------------------------------
        # Delete temporary OAuth state
        # ----------------------------------------------------

        delete_oauth_state(state)

        # ----------------------------------------------------
        # Remove callback parameters
        # ----------------------------------------------------

        st.query_params.clear()

        return True

    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        delete_oauth_state(state)

        st.query_params.clear()

        return False


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    user_id = get_current_user_id()

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

    user_id = get_current_user_id()

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

    user_id = get_current_user_id()

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
        # Refresh expired token
        # ----------------------------------------------------

        if (
            credentials.expired
            and credentials.refresh_token
        ):

            from google.auth.transport.requests import Request

            credentials.refresh(
                Request()
            )

            save_gmail_token(
                user_id=user_id,
                email=email,
                token_json=credentials.to_json()
            )

        # ----------------------------------------------------
        # Build Gmail API
        # ----------------------------------------------------

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

    user_id = get_current_user_id()

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

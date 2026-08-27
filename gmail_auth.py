# gmail_auth.py

import json
import sqlite3
import time
import secrets
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "gmail_oauth_v3.sqlite3"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


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


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def init_db():

    conn = get_db()

    try:

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

        conn.commit()

    finally:
        conn.close()


init_db()


# ============================================================
# USER HELPERS
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

    gmail_config = st.secrets["gmail_oauth"]

    client_id = gmail_config["client_id"]

    client_secret = gmail_config["client_secret"]

    redirect_uri = gmail_config["redirect_uri"]

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

    flow = Flow.from_client_config(

        config,

        scopes=GMAIL_SCOPES,

        code_verifier=code_verifier,

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
    code_verifier,
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
                time.time(),
            ),
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
            (state,),
        )

        return cursor.fetchone()

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
# CLEAN OLD STATES
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
            (cutoff,),
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
    token_json,
):

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

                token_json = excluded.token_json,

                updated_at = excluded.updated_at
            """,
            (
                user_id,
                email,
                token_json,
                now,
                now,
            ),
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    if not user_id:
        return None

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
            (user_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return (
            row["email"],
            row["token_json"],
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
            (user_id,),
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# CONNECT GMAIL
# ============================================================

def connect_gmail():

    cleanup_old_oauth_states()

    user_id = get_current_user_id()

    user_email = get_current_user_email()

    if not user_id:
        return None

    if not user_email:
        return None

    try:

        # ----------------------------------------------------
        # PKCE
        # ----------------------------------------------------

        code_verifier = secrets.token_urlsafe(64)

        # ----------------------------------------------------
        # FLOW
        # ----------------------------------------------------

        flow = get_gmail_flow(
            code_verifier=code_verifier
        )

        # ----------------------------------------------------
        # AUTHORIZATION URL
        # ----------------------------------------------------

        authorization_url, state = (
            flow.authorization_url(

                access_type="offline",

                prompt="consent",

                include_granted_scopes="false",

                login_hint=user_email,
            )
        )

        # ----------------------------------------------------
        # SAVE STATE
        # ----------------------------------------------------

        save_oauth_state(

            state=state,

            user_id=user_id,

            user_email=user_email,

            code_verifier=code_verifier,
        )

        return authorization_url

    except Exception as e:

        raise Exception(
            f"OAuth setup error: {e}"
        )


# ============================================================
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    params = st.query_params

    code = params.get("code")

    state = params.get("state")

    error = params.get("error")

    # --------------------------------------------------------
    # GOOGLE ERROR
    # --------------------------------------------------------

    if error:

        raise Exception(
            f"Google authorization failed: {error}"
        )

    # --------------------------------------------------------
    # NO CODE
    # --------------------------------------------------------

    if not code:
        return False

    # --------------------------------------------------------
    # NO STATE
    # --------------------------------------------------------

    if not state:

        raise Exception(
            "OAuth state was not received."
        )

    # --------------------------------------------------------
    # LOGIN CHECK
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        raise Exception(
            "Please login to AgentForge first."
        )

    # --------------------------------------------------------
    # LOAD STATE
    # --------------------------------------------------------

    oauth_state = load_oauth_state(state)

    if oauth_state is None:

        raise Exception(
            "OAuth session expired. "
            "Please click Connect My Gmail again."
        )

    current_user_id = get_current_user_id()

    current_user_email = get_current_user_email()

    # --------------------------------------------------------
    # SECURITY CHECK
    # --------------------------------------------------------

    if oauth_state["user_id"] != current_user_id:

        delete_oauth_state(state)

        raise Exception(
            "OAuth user mismatch."
        )

    code_verifier = oauth_state["code_verifier"]

    # ========================================================
    # TOKEN EXCHANGE
    # ========================================================

    try:

        flow = get_gmail_flow(
            code_verifier=code_verifier
        )

        flow.fetch_token(
            code=code,
            code_verifier=code_verifier,
        )

        credentials = flow.credentials

        # ====================================================
        # BUILD SERVICE
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
                "Unable to determine Gmail email address."
            )

        # ====================================================
        # ACCOUNT MATCH
        # ====================================================

        if (
            not current_user_email
            or
            gmail_email.lower()
            !=
            current_user_email.lower()
        ):

            delete_oauth_state(state)

            raise Exception(
                "Google account mismatch. "
                f"AgentForge account: {current_user_email}, "
                f"Gmail account: {gmail_email}"
            )

        # ====================================================
        # SAVE TOKEN
        # ====================================================

        save_gmail_token(

            user_id=current_user_id,

            email=gmail_email,

            token_json=credentials.to_json(),
        )

        # ====================================================
        # SESSION
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email

        # ====================================================
        # CLEANUP
        # ====================================================

        delete_oauth_state(state)

        st.query_params.clear()

        return True

    except Exception:

        delete_oauth_state(state)

        st.query_params.clear()

        raise


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    user_id = get_current_user_id()

    if not user_id:
        return False

    try:

        result = load_gmail_token(
            user_id
        )

        return result is not None

    except Exception:

        return False


# ============================================================
# GET CONNECTED EMAIL
# ============================================================

def get_connected_gmail_email():

    user_id = get_current_user_id()

    if not user_id:
        return None

    try:

        result = load_gmail_token(
            user_id
        )

        if result is None:
            return None

        email, token_json = result

        return email

    except Exception:

        return None


# ============================================================
# GET GMAIL SERVICE
#
# IMPORTANT:
# This is the ONLY Gmail service function.
# backend.py imports this function.
# ============================================================

def get_gmail_service():

    user_id = get_current_user_id()

    if not user_id:
        return None

    result = load_gmail_token(
        user_id
    )

    if result is None:
        return None

    email, token_json = result

    if not token_json:
        return None

    try:

        token_data = json.loads(
            token_json
        )

        credentials = (
            Credentials.from_authorized_user_info(
                token_data,
                GMAIL_SCOPES,
            )
        )

        # ----------------------------------------------------
        # REFRESH
        # ----------------------------------------------------

        if (
            credentials.expired
            and
            credentials.refresh_token
        ):

            credentials.refresh(
                Request()
            )

            save_gmail_token(

                user_id=user_id,

                email=email,

                token_json=credentials.to_json(),
            )

        # ----------------------------------------------------
        # VALIDATE
        # ----------------------------------------------------

        if not credentials.valid:

            return None

        # ----------------------------------------------------
        # BUILD SERVICE
        # ----------------------------------------------------

        service = build(

            "gmail",

            "v1",

            credentials=credentials,

            cache_discovery=False,
        )

        return service

    except Exception as e:

        raise Exception(
            f"Gmail authentication error: {e}"
        )


# ============================================================
# DISCONNECT
# ============================================================

def disconnect_gmail():

    user_id = get_current_user_id()

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

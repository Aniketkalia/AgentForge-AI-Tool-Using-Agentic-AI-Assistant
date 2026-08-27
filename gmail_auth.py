# ============================================================
# gmail_auth.py
# ============================================================

import os
import json
import sqlite3
import secrets
from datetime import datetime, timezone

import streamlit as st

# ------------------------------------------------------------
# IMPORTANT:
# Google can return additional identity scopes.
# ------------------------------------------------------------

os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# DATABASE
# ============================================================

DB_FILE = "gmail_tokens.db"


# ============================================================
# GMAIL / GOOGLE SCOPES
# ============================================================
#
# We explicitly request the identity scopes too.
# This prevents:
#
# Scope has changed from gmail.send to
# openid profile gmail.send userinfo.email
#
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# CREATE TABLES
# ============================================================

def init_db():

    conn = get_db()

    try:

        # ----------------------------------------------------
        # Gmail tokens
        # ----------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_tokens (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # ----------------------------------------------------
        # OAuth temporary state
        #
        # This is VERY IMPORTANT.
        #
        # We do NOT depend on Streamlit session_state for
        # OAuth state or PKCE verifier.
        #
        # This allows the OAuth flow to work even when
        # Streamlit opens the Google page in a new tab.
        # ----------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.commit()

    finally:

        conn.close()


# Initialize database when module loads
init_db()


# ============================================================
# GET OAUTH CONFIG
# ============================================================

def get_gmail_flow(
    state=None,
    code_verifier=None,
):

    config = {

        "web": {

            "client_id": st.secrets[
                "gmail_oauth"
            ]["client_id"],

            "client_secret": st.secrets[
                "gmail_oauth"
            ]["client_secret"],

            "auth_uri":
                "https://accounts.google.com/o/oauth2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",
        }
    }

    # --------------------------------------------------------
    # Create Flow
    # --------------------------------------------------------

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES,
        state=state,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # This MUST exactly match the redirect URI registered
    # in Google Cloud Console.
    # --------------------------------------------------------

    flow.redirect_uri = st.secrets[
        "gmail_oauth"
    ]["redirect_uri"]

    # --------------------------------------------------------
    # Restore PKCE verifier when handling callback
    # --------------------------------------------------------

    if code_verifier:

        flow.code_verifier = code_verifier

    return flow


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    # --------------------------------------------------------
    # AgentForge user must be logged in
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        return None

    user_id = st.user.get("sub")

    user_email = st.user.email

    if not user_id or not user_email:

        return None

    # --------------------------------------------------------
    # Create OAuth flow
    # --------------------------------------------------------

    flow = get_gmail_flow()

    # --------------------------------------------------------
    # Generate our own PKCE verifier.
    #
    # This fixes:
    #
    # invalid_grant: Missing code verifier
    # --------------------------------------------------------

    code_verifier = secrets.token_urlsafe(64)

    flow.code_verifier = code_verifier

    # --------------------------------------------------------
    # Generate Google authorization URL
    # --------------------------------------------------------

    authorization_url, state = flow.authorization_url(

        access_type="offline",

        include_granted_scopes=False,

        prompt="consent",

        login_hint=user_email,

    )

    # --------------------------------------------------------
    # Save OAuth state + PKCE verifier in SQLite.
    #
    # NOT session_state.
    #
    # This survives opening Google in another browser tab.
    # --------------------------------------------------------

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
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )

        conn.commit()

    finally:

        conn.close()

    return authorization_url


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def load_oauth_state(state):

    conn = get_db()

    try:

        row = conn.execute(
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
        ).fetchone()

        if not row:

            return None

        return dict(row)

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
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    email,
    credentials,
):

    token_json = credentials.to_json()

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT OR REPLACE INTO gmail_tokens
            (
                user_id,
                email,
                token_json,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                email,
                token_json,
                datetime.now(
                    timezone.utc
                ).isoformat(),
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

        row = conn.execute(
            """
            SELECT
                email,
                token_json
            FROM gmail_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if not row:

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
# HANDLE GMAIL CALLBACK
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
            f"❌ Gmail authorization failed: {error}"
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # Missing state
    # --------------------------------------------------------

    if not state:

        st.error(
            "❌ Gmail OAuth state was not received."
        )

        st.query_params.clear()

        return False

    # --------------------------------------------------------
    # Load state from SQLite
    #
    # NOT session_state.
    # --------------------------------------------------------

    oauth_data = load_oauth_state(state)

    if not oauth_data:

        st.error(
            "❌ Gmail OAuth session expired. "
            "Please click Connect Gmail again."
        )

        st.query_params.clear()

        return False

    oauth_user_id = oauth_data["user_id"]

    oauth_user_email = oauth_data["user_email"]

    code_verifier = oauth_data["code_verifier"]

    # --------------------------------------------------------
    # Security check against current AgentForge user
    # --------------------------------------------------------

    if st.user.is_logged_in:

        current_user_id = st.user.get("sub")

        current_email = st.user.email

        if current_user_id != oauth_user_id:

            st.error(
                "❌ Google account mismatch."
            )

            delete_oauth_state(state)

            st.query_params.clear()

            return False

        if (
            current_email
            and oauth_user_email
            and current_email.lower()
            != oauth_user_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            delete_oauth_state(state)

            st.query_params.clear()

            return False

    # ========================================================
    # EXCHANGE AUTHORIZATION CODE
    # ========================================================

    try:

        flow = get_gmail_flow(
            state=state,
            code_verifier=code_verifier,
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # flow.code_verifier has been restored.
        #
        # This fixes:
        #
        # invalid_grant: Missing code verifier
        # ----------------------------------------------------

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
        # SECURITY:
        # GMAIL ACCOUNT MUST MATCH AGENTFORGE ACCOUNT
        # ====================================================

        if (
            oauth_user_email.lower()
            != gmail_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge account: "
                f"{oauth_user_email}"
            )

            st.warning(
                f"Gmail account: "
                f"{gmail_email}"
            )

            delete_oauth_state(state)

            st.query_params.clear()

            return False

        # ====================================================
        # SAVE TOKEN
        # ====================================================

        save_gmail_token(
            user_id=oauth_user_id,
            email=gmail_email,
            credentials=credentials,
        )

        # ====================================================
        # CLEANUP
        # ====================================================

        delete_oauth_state(state)

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email

        st.session_state[
            "gmail_oauth_in_progress"
        ] = False

        st.query_params.clear()

        st.success(
            f"✅ Gmail connected successfully: "
            f"{gmail_email}"
        )

        return True

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        # Don't leave OAuth state behind
        delete_oauth_state(state)

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

    token_data = load_gmail_token(
        user_id
    )

    if not token_data:

        return None

    email, token_json = token_data

    try:

        token_info = json.loads(
            token_json
        )

        credentials = (
            Credentials.from_authorized_user_info(
                token_info,
                GMAIL_SCOPES,
            )
        )

        # ----------------------------------------------------
        # Refresh expired access token
        # ----------------------------------------------------

        if credentials.expired:

            if credentials.refresh_token:

                from google.auth.transport.requests import Request

                credentials.refresh(
                    Request()
                )

                # Save refreshed credentials
                save_gmail_token(
                    user_id=user_id,
                    email=email,
                    credentials=credentials,
                )

            else:

                delete_gmail_token(
                    user_id
                )

                return None

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return service

    except Exception as e:

        print(
            f"Gmail service error: {e}"
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

    token_data = load_gmail_token(
        user_id
    )

    if not token_data:

        return False

    try:

        service = get_gmail_service()

        if service is None:

            return False

        service.users().getProfile(
            userId="me"
        ).execute()

        return True

    except Exception as e:

        print(
            f"Gmail connection check failed: {e}"
        )

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

    token_data = load_gmail_token(
        user_id
    )

    if not token_data:

        return None

    email, token_json = token_data

    # --------------------------------------------------------
    # Verify token still works
    # --------------------------------------------------------

    try:

        service = get_gmail_service()

        if service is None:

            return None

        profile = (
            service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        return profile.get(
            "emailAddress",
            email,
        )

    except Exception as e:

        print(
            f"Gmail email check failed: {e}"
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
        None,
    )

    st.session_state.pop(
        "gmail_email",
        None,
    )

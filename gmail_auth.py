import os
import json
import time
import sqlite3
import secrets
from pathlib import Path

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# GMAIL SCOPE
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# DATABASE
# ============================================================
#
# IMPORTANT:
# We intentionally use a NEW database filename.
#
# This avoids your old broken SQLite schema:
#
# gmail_oauth_states
#     missing user_email
#
# gmail_tokens
#     missing email
#
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "gmail_oauth_v2.sqlite3"


# ============================================================
# DATABASE CONNECTION
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

        # ----------------------------------------------------
        # OAuth temporary state
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Gmail tokens
        # ----------------------------------------------------

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


# ============================================================
# INITIALIZE DATABASE WHEN MODULE LOADS
# ============================================================

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
# CREATE GOOGLE OAUTH FLOW
# ============================================================

def get_gmail_flow(
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

    flow = Flow.from_client_config(

        config,

        scopes=GMAIL_SCOPES,

        code_verifier=code_verifier,

    )

    flow.redirect_uri = st.secrets[
        "gmail_oauth"
    ]["redirect_uri"]

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

        row = cursor.fetchone()

        return row

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
# DELETE OLD OAUTH STATES
# ============================================================

def cleanup_old_oauth_states():

    conn = get_db()

    try:

        # Remove states older than 15 minutes

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
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    cleanup_old_oauth_states()

    user_id = get_current_user_id()

    user_email = get_current_user_email()

    if not user_id:

        st.error(
            "You must be logged into AgentForge first."
        )

        return None


    if not user_email:

        st.error(
            "Unable to determine AgentForge email."
        )

        return None


    try:

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
        # Generate Google authorization URL
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
        # Store state OUTSIDE Streamlit session
        #
        # This is important because Streamlit session state
        # resets after browser refresh.
        # ----------------------------------------------------

        save_oauth_state(

            state=state,

            user_id=user_id,

            user_email=user_email,

            code_verifier=code_verifier,

        )


        return authorization_url


    except Exception as e:

        st.error(
            f"OAuth setup error: {e}"
        )

        return None


# ============================================================
# HANDLE GOOGLE CALLBACK
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
    # No OAuth callback
    # --------------------------------------------------------

    if not code:

        return False


    if not state:

        st.error(
            "Gmail OAuth state was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # User must still be logged into AgentForge
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        st.error(
            "Please login to AgentForge first."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Load state from database
    # --------------------------------------------------------

    oauth_state = load_oauth_state(state)


    if oauth_state is None:

        st.error(
            "Gmail OAuth session expired. "
            "Please click Connect My Gmail again."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Verify state belongs to current AgentForge user
    # --------------------------------------------------------

    current_user_id = get_current_user_id()

    current_user_email = get_current_user_email()


    if oauth_state["user_id"] != current_user_id:

        st.error(
            "OAuth user mismatch."
        )

        delete_oauth_state(state)

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Get stored PKCE verifier
    # --------------------------------------------------------

    code_verifier = oauth_state[
        "code_verifier"
    ]


    # ========================================================
    # EXCHANGE AUTHORIZATION CODE
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
        # CREATE GMAIL API SERVICE
        # ====================================================

        service = build(

            "gmail",

            "v1",

            credentials=credentials,

            cache_discovery=False,

        )


        # ====================================================
        # GET REAL GMAIL ACCOUNT
        # ====================================================

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )


        gmail_email = profile[
            "emailAddress"
        ]


        # ====================================================
        # SECURITY CHECK
        # ====================================================

        if (
            not current_user_email
            or
            gmail_email.lower()
            != current_user_email.lower()
        ):

            st.error(
                "❌ Google account mismatch."
            )

            st.warning(
                f"AgentForge account: "
                f"{current_user_email}"
            )

            st.warning(
                f"Gmail account: "
                f"{gmail_email}"
            )

            st.info(
                "Authorize Gmail using the same "
                "Google account used to login to AgentForge."
            )

            delete_oauth_state(state)

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN
        # ====================================================

        token_json = credentials.to_json()

        now = time.time()


        conn = get_db()

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
                    current_user_id,

                    gmail_email,

                    token_json,

                    now,

                    now,
                ),
            )

            conn.commit()

        finally:

            conn.close()


        # ====================================================
        # REMOVE TEMPORARY OAUTH STATE
        # ====================================================

        delete_oauth_state(state)


        # ====================================================
        # UPDATE SESSION CACHE
        # ====================================================

        st.session_state[
            "gmail_connected"
        ] = True

        st.session_state[
            "gmail_email"
        ] = gmail_email


        # ====================================================
        # REMOVE CALLBACK PARAMETERS
        # ====================================================

        st.query_params.clear()


        st.success(
            f"✅ Gmail connected successfully: "
            f"{gmail_email}"
        )


        return True


    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )

        delete_oauth_state(state)

        st.query_params.clear()

        return False


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

    except Exception as e:

        # Do NOT crash the entire Streamlit app
        st.warning(
            f"Gmail storage check failed: {e}"
        )

        return False


# ============================================================
# GET CONNECTED GMAIL EMAIL
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


    except Exception as e:

        st.warning(
            f"Gmail storage check failed: {e}"
        )

        return None


# ============================================================
# GET GMAIL SERVICE
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


    try:

        token_data = json.loads(
            token_json
        )


        # ----------------------------------------------------
        # Recreate credentials
        # ----------------------------------------------------

        credentials = (
            Credentials.from_authorized_user_info(
                token_data
            )
        )


        # ----------------------------------------------------
        # Refresh expired token
        # ----------------------------------------------------

        if (
            credentials.expired
            and credentials.refresh_token
        ):

            credentials.refresh(
                Request()
            )


            # Save refreshed credentials

            save_refreshed_credentials(

                user_id=user_id,

                email=email,

                credentials=credentials,

            )


        # ----------------------------------------------------
        # Build Gmail API
        # ----------------------------------------------------

        service = build(

            "gmail",

            "v1",

            credentials=credentials,

            cache_discovery=False,

        )


        return service


    except Exception as e:

        st.error(
            f"Unable to create Gmail service: {e}"
        )

        return None


# ============================================================
# SAVE REFRESHED TOKEN
# ============================================================

def save_refreshed_credentials(
    user_id,
    email,
    credentials,
):

    conn = get_db()

    try:

        conn.execute(

            """
            UPDATE gmail_tokens

            SET
                email = ?,
                token_json = ?,
                updated_at = ?

            WHERE user_id = ?
            """,

            (
                email,

                credentials.to_json(),

                time.time(),

                user_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail():

    user_id = get_current_user_id()

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


    st.session_state.pop(
        "gmail_connected",
        None
    )

    st.session_state.pop(
        "gmail_email",
        None
    )

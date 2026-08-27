import json
import sqlite3
import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
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

DB_FILE = "gmail_tokens.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            user_id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            gmail_email TEXT NOT NULL,
            token_json TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# SAVE USER GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    user_email,
    gmail_email,
    credentials
):
    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        INSERT OR REPLACE INTO gmail_tokens
        (
            user_id,
            user_email,
            gmail_email,
            token_json
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            user_email,
            gmail_email,
            credentials.to_json()
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# LOAD USER GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    conn = sqlite3.connect(DB_FILE)

    row = conn.execute(
        """
        SELECT user_email, gmail_email, token_json
        FROM gmail_tokens
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not row:
        return None

    return {
        "user_email": row[0],
        "gmail_email": row[1],
        "token_json": row[2]
    }


# ============================================================
# DELETE USER GMAIL TOKEN
# ============================================================

def delete_gmail_token(user_id):

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        "DELETE FROM gmail_tokens WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# CREATE OAUTH FLOW
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

    flow.redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]

    return flow


# ============================================================
# CHECK WHETHER CURRENT USER HAS GMAIL
# ============================================================

def is_gmail_connected():

    if not st.user.is_logged_in:
        return False

    user_id = st.user.get("sub")

    if not user_id:
        return False

    token = load_gmail_token(user_id)

    return token is not None


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None

    token = load_gmail_token(user_id)

    if not token:
        return None

    return token["gmail_email"]


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")
    user_email = st.user.email

    if not user_id:
        return None

    flow = get_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=user_email
    )

    # Store OAuth information for current browser session
    st.session_state["gmail_oauth_state"] = state
    st.session_state["gmail_oauth_user_id"] = user_id
    st.session_state["gmail_oauth_user_email"] = user_email

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
    # OAuth error
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
            "AgentForge login session is missing. "
            "Please login again."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # Authorization code
    # --------------------------------------------------------

    if not code:

        st.error(
            "Gmail authorization code was not received."
        )

        st.query_params.clear()

        return False


    # --------------------------------------------------------
    # OAuth state
    # --------------------------------------------------------

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:

        st.error(
            "Gmail OAuth state was lost. "
            "Please click Connect Gmail again."
        )

        st.query_params.clear()

        return False


    if state != saved_state:

        st.error(
            "Invalid Gmail OAuth state."
        )

        st.query_params.clear()

        return False


    # ========================================================
    # CURRENT AGENTFORGE USER
    # ========================================================

    user_id = st.user.get("sub")
    logged_in_email = st.user.email

    if not user_id:

        st.error(
            "Unable to identify AgentForge user."
        )

        st.query_params.clear()

        return False


    # ========================================================
    # EXCHANGE CODE FOR GMAIL TOKEN
    # ========================================================

    try:

        flow = get_gmail_flow()

        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials


        # ====================================================
        # CREATE GMAIL API SERVICE
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
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = profile["emailAddress"]


        # ====================================================
        # SECURITY CHECK
        # ====================================================

        if gmail_email.lower() != logged_in_email.lower():

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
                "Authorize Gmail using the same "
                "Google account used for AgentForge."
            )

            st.query_params.clear()

            return False


        # ====================================================
        # SAVE TOKEN PER USER
        # ====================================================

        save_gmail_token(
            user_id=user_id,
            user_email=logged_in_email,
            gmail_email=gmail_email,
            credentials=credentials
        )


        # ====================================================
        # SESSION CACHE
        # ====================================================

        st.session_state["gmail_connected"] = True
        st.session_state["gmail_email"] = gmail_email


        # Remove temporary OAuth data
        st.session_state.pop(
            "gmail_oauth_state",
            None
        )

        st.session_state.pop(
            "gmail_oauth_user_id",
            None
        )

        st.session_state.pop(
            "gmail_oauth_user_email",
            None
        )


        # Remove callback parameters
        st.query_params.clear()


        return True


    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        st.query_params.clear()

        return False


# ============================================================
# GET CURRENT USER'S GMAIL SERVICE
# ============================================================

def get_gmail_service():

    if not st.user.is_logged_in:
        return None

    user_id = st.user.get("sub")

    if not user_id:
        return None


    # Load token from persistent DB
    token_data = load_gmail_token(user_id)

    if not token_data:
        return None


    try:

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(
                    token_data["token_json"]
                ),
                GMAIL_SCOPES
            )
        )


        # ====================================================
        # REFRESH TOKEN IF REQUIRED
        # ====================================================

        if credentials.expired and credentials.refresh_token:

            from google.auth.transport.requests import Request

            credentials.refresh(
                Request()
            )

            # Save refreshed credentials
            save_gmail_token(
                user_id=user_id,
                user_email=token_data["user_email"],
                gmail_email=token_data["gmail_email"],
                credentials=credentials
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

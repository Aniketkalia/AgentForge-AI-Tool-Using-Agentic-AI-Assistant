# ============================================================
# gmail_auth.py
# AgentForge AI
#
# Gmail OAuth for sending emails
#
# IMPORTANT:
# - Only requests gmail.send
# - Does NOT request gmail.readonly
# - Does NOT request gmail.modify
# - Does NOT request openid/email/profile scopes
# - Does NOT use PKCE
# - Does NOT call Gmail profile API
# - Uses the already logged-in AgentForge Google email
# ============================================================

import os
import json
import sqlite3
import time
from urllib.parse import urlencode

import requests

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = "agentforge.db"

GOOGLE_AUTH_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

GOOGLE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)

GMAIL_SCOPE = (
    "https://www.googleapis.com/auth/gmail.send"
)


# ============================================================
# STREAMLIT SECRETS
# ============================================================

def _get_secret(name):
    """
    Safely read a Streamlit secret.
    Falls back to environment variable.
    """

    # Streamlit
    try:
        import streamlit as st

        value = st.secrets.get(name)

        if value:
            return str(value).strip()

    except Exception:
        pass

    # Environment
    value = os.getenv(name)

    if value:
        return str(value).strip()

    return None


def get_google_client_id():
    """
    Get Google OAuth Client ID.

    Supports:

        GOOGLE_CLIENT_ID

    or:

        [gmail_oauth]
        client_id = "..."
    """

    # --------------------------------------------------------
    # TOP LEVEL
    # --------------------------------------------------------

    value = _get_secret("GOOGLE_CLIENT_ID")

    if value:
        return value

    # --------------------------------------------------------
    # gmail_oauth FALLBACK
    # --------------------------------------------------------

    try:
        import streamlit as st

        gmail_config = st.secrets.get(
            "gmail_oauth",
            {}
        )

        value = gmail_config.get("client_id")

        if value:
            return str(value).strip()

    except Exception:
        pass

    return None


def get_google_client_secret():
    """
    Get Google OAuth Client Secret.
    """

    # --------------------------------------------------------
    # TOP LEVEL
    # --------------------------------------------------------

    value = _get_secret(
        "GOOGLE_CLIENT_SECRET"
    )

    if value:
        return value

    # --------------------------------------------------------
    # gmail_oauth FALLBACK
    # --------------------------------------------------------

    try:
        import streamlit as st

        gmail_config = st.secrets.get(
            "gmail_oauth",
            {}
        )

        value = gmail_config.get(
            "client_secret"
        )

        if value:
            return str(value).strip()

    except Exception:
        pass

    return None


def get_redirect_uri():
    """
    Get Gmail OAuth redirect URI.

    Must EXACTLY match the URI registered
    in Google Cloud Console.
    """

    # --------------------------------------------------------
    # TOP LEVEL
    # --------------------------------------------------------

    value = _get_secret(
        "GOOGLE_REDIRECT_URI"
    )

    if value:
        return value.rstrip("/")


    # --------------------------------------------------------
    # gmail_oauth FALLBACK
    # --------------------------------------------------------

    try:
        import streamlit as st

        gmail_config = st.secrets.get(
            "gmail_oauth",
            {}
        )

        value = gmail_config.get(
            "redirect_uri"
        )

        if value:
            return str(value).strip().rstrip("/")

    except Exception:
        pass


    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    return "http://localhost:8501"


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    """
    Open SQLite database.
    """

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_database():
    """
    Create Gmail tables if they don't exist.
    """

    conn = get_connection()

    # --------------------------------------------------------
    # GMAIL TOKEN TABLE
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth (
            user_id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            token_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # OAUTH STATE TABLE
    #
    # No PKCE verifier is used.
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


# Initialize database
init_database()


# ============================================================
# CURRENT AGENTFORGE USER
# ============================================================

def get_current_user_id():
    """
    Get the Google 'sub' of the currently logged-in
    AgentForge user.
    """

    try:
        import streamlit as st

        if st.user.is_logged_in:

            user_id = st.user.get("sub")

            if user_id:
                return str(user_id)

    except Exception:
        pass

    return None


def get_current_user_email():
    """
    Get the email of the currently logged-in
    AgentForge Google account.
    """

    try:
        import streamlit as st

        if st.user.is_logged_in:

            email = st.user.get("email")

            if email:
                return str(email).strip().lower()

    except Exception:
        pass

    return None


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():
    """
    Create Gmail OAuth authorization URL.

    IMPORTANT:
    Only gmail.send is requested.

    No:
        openid
        email
        profile
        gmail.readonly
        gmail.modify

    This prevents the previous scope mismatch.
    """

    init_database()

    # --------------------------------------------------------
    # GET CONFIG
    # --------------------------------------------------------

    client_id = get_google_client_id()

    redirect_uri = get_redirect_uri()

    user_id = get_current_user_id()

    user_email = get_current_user_email()


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not client_id:

        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from "
            "Streamlit secrets."
        )


    if not get_google_client_secret():

        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from "
            "Streamlit secrets."
        )


    if not user_id:

        raise RuntimeError(
            "AgentForge user is not logged in."
        )


    if not user_email:

        raise RuntimeError(
            "Unable to get logged-in Google email."
        )


    if not redirect_uri:

        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is missing."
        )


    # --------------------------------------------------------
    # CREATE OAUTH STATE
    # --------------------------------------------------------

    import secrets

    state = secrets.token_urlsafe(32)


    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    conn = get_connection()

    # Clean old states for this user
    conn.execute(
        """
        DELETE FROM gmail_oauth_states
        WHERE user_id = ?
        """,
        (user_id,)
    )


    conn.execute(
        """
        INSERT INTO gmail_oauth_states
        (
            state,
            user_id,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            state,
            user_id,
            int(time.time())
        )
    )

    conn.commit()
    conn.close()


    # --------------------------------------------------------
    # GOOGLE OAUTH PARAMETERS
    # --------------------------------------------------------

    params = {

        "client_id":
            client_id,

        "redirect_uri":
            redirect_uri,

        "response_type":
            "code",

        # ONLY Gmail send
        "scope":
            GMAIL_SCOPE,

        # Get refresh token
        "access_type":
            "offline",

        # Always show consent screen
        "prompt":
            "consent",

        # OAuth CSRF protection
        "state":
            state,
    }


    # --------------------------------------------------------
    # BUILD URL
    # --------------------------------------------------------

    auth_url = (
        GOOGLE_AUTH_URL
        + "?"
        + urlencode(params)
    )


    return auth_url


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def load_oauth_state(state):
    """
    Load OAuth state from SQLite.
    """

    if not state:
        return None


    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            user_id,
            created_at
        FROM gmail_oauth_states
        WHERE state = ?
        """,
        (state,)
    ).fetchone()

    conn.close()


    if not row:
        return None


    # --------------------------------------------------------
    # STATE EXPIRATION
    # --------------------------------------------------------

    created_at = row["created_at"]

    if not created_at:
        return None


    # 15 minute expiration
    if time.time() - created_at > 900:

        delete_oauth_state(state)

        return None


    return row


# ============================================================
# DELETE OAUTH STATE
# ============================================================

def delete_oauth_state(state):

    if not state:
        return


    conn = get_connection()

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
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    user_email,
    token_data
):
    """
    Save Gmail OAuth token.
    """

    if not user_id:
        raise ValueError(
            "user_id is required"
        )


    if not user_email:
        raise ValueError(
            "user_email is required"
        )


    if not token_data:
        raise ValueError(
            "token_data is required"
        )


    conn = get_connection()

    now = int(time.time())


    conn.execute(
        """
        INSERT OR REPLACE INTO gmail_oauth
        (
            user_id,
            user_email,
            token_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            user_email,
            json.dumps(token_data),
            now,
            now
        )
    )


    conn.commit()
    conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id=None):

    if user_id is None:
        user_id = get_current_user_id()


    if not user_id:
        return None, None


    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            user_email,
            token_json
        FROM gmail_oauth
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()


    if not row:
        return None, None


    return (
        row["user_email"],
        row["token_json"]
    )


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail(user_id=None):
    """
    Disconnect Gmail for current user.
    """

    if user_id is None:
        user_id = get_current_user_id()


    if not user_id:
        return False


    conn = get_connection()


    conn.execute(
        """
        DELETE FROM gmail_oauth
        WHERE user_id = ?
        """,
        (user_id,)
    )


    conn.commit()
    conn.close()


    return True


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    user_id = get_current_user_id()

    if not user_id:
        return None


    email, token_json = (
        load_gmail_token(user_id)
    )


    if not token_json:
        return None


    return email


# ============================================================
# HANDLE GOOGLE CALLBACK
# ============================================================

def handle_gmail_callback():
    """
    Handle:

        ?code=...
        &state=...

    returned by Google.
    """

    import streamlit as st

    init_database()


    # --------------------------------------------------------
    # READ QUERY PARAMETERS
    # --------------------------------------------------------

    code = st.query_params.get(
        "code"
    )

    state = st.query_params.get(
        "state"
    )

    error = st.query_params.get(
        "error"
    )


    # --------------------------------------------------------
    # GOOGLE ERROR
    # --------------------------------------------------------

    if error:

        raise RuntimeError(
            f"Google authorization failed: {error}"
        )


    # --------------------------------------------------------
    # CODE REQUIRED
    # --------------------------------------------------------

    if not code:

        return False


    # --------------------------------------------------------
    # STATE REQUIRED
    # --------------------------------------------------------

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )


    # --------------------------------------------------------
    # LOAD STATE
    # --------------------------------------------------------

    oauth_state = load_oauth_state(
        state
    )


    if not oauth_state:

        raise RuntimeError(
            "Gmail OAuth state is missing or expired. "
            "Please click Connect Gmail again."
        )


    user_id = oauth_state[
        "user_id"
    ]


    # --------------------------------------------------------
    # VERIFY CURRENT USER
    # --------------------------------------------------------

    current_user_id = (
        get_current_user_id()
    )


    if (
        current_user_id
        and current_user_id != user_id
    ):

        delete_oauth_state(state)

        raise RuntimeError(
            "OAuth user mismatch. "
            "Please restart Gmail connection."
        )


    # --------------------------------------------------------
    # GET GOOGLE CONFIG
    # --------------------------------------------------------

    client_id = (
        get_google_client_id()
    )

    client_secret = (
        get_google_client_secret()
    )

    redirect_uri = (
        get_redirect_uri()
    )


    if not client_id:

        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing "
            "from Streamlit secrets."
        )


    if not client_secret:

        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing "
            "from Streamlit secrets."
        )


    if not redirect_uri:

        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is missing."
        )


    # --------------------------------------------------------
    # TOKEN EXCHANGE
    #
    # IMPORTANT:
    # NO code_verifier
    # NO PKCE
    # --------------------------------------------------------

    token_payload = {

        "code":
            code,

        "client_id":
            client_id,

        "client_secret":
            client_secret,

        "redirect_uri":
            redirect_uri,

        "grant_type":
            "authorization_code",
    }


    try:

        response = requests.post(
            GOOGLE_TOKEN_URL,
            data=token_payload,
            timeout=30
        )

    except Exception as e:

        raise RuntimeError(
            f"Google token request failed: {e}"
        )


    # --------------------------------------------------------
    # TOKEN ERROR
    # --------------------------------------------------------

    if response.status_code != 200:

        try:
            details = response.json()
        except Exception:
            details = response.text

        raise RuntimeError(
            "Google token exchange failed: "
            f"{details}"
        )


    # --------------------------------------------------------
    # PARSE TOKEN
    # --------------------------------------------------------

    try:

        token_data = response.json()

    except Exception as e:

        raise RuntimeError(
            f"Invalid Google token response: {e}"
        )


    access_token = (
        token_data.get(
            "access_token"
        )
    )


    if not access_token:

        raise RuntimeError(
            "Google did not return an access token."
        )


    # --------------------------------------------------------
    # GET AGENTFORGE LOGGED-IN EMAIL
    #
    # We deliberately DO NOT call:
    #
    # gmail.googleapis.com/gmail/v1/users/me/profile
    #
    # because gmail.send doesn't grant that permission.
    # --------------------------------------------------------

    user_email = (
        get_current_user_email()
    )


    if not user_email:

        raise RuntimeError(
            "Unable to determine the "
            "Google account email."
        )


    # --------------------------------------------------------
    # SAVE TOKEN
    # --------------------------------------------------------

    save_gmail_token(
        user_id=user_id,
        user_email=user_email,
        token_data=token_data
    )


    # --------------------------------------------------------
    # DELETE USED STATE
    # --------------------------------------------------------

    delete_oauth_state(state)


    # --------------------------------------------------------
    # CLEAR QUERY PARAMETERS
    # --------------------------------------------------------

    try:
        st.query_params.clear()
    except Exception:
        pass


    return True


# ============================================================
# GET GMAIL CREDENTIALS
# ============================================================

def get_gmail_credentials():

    user_id = (
        get_current_user_id()
    )


    if not user_id:
        return None


    email, token_json = (
        load_gmail_token(user_id)
    )


    if not token_json:
        return None


    # --------------------------------------------------------
    # PARSE TOKEN
    # --------------------------------------------------------

    try:

        token_data = json.loads(
            token_json
        )

    except Exception:

        disconnect_gmail(user_id)

        return None


    # --------------------------------------------------------
    # CLIENT CONFIG
    # --------------------------------------------------------

    client_id = (
        get_google_client_id()
    )

    client_secret = (
        get_google_client_secret()
    )


    if not client_id or not client_secret:

        return None


    # --------------------------------------------------------
    # CREATE GOOGLE CREDENTIALS
    # --------------------------------------------------------

    credentials = Credentials(

        token=
            token_data.get(
                "access_token"
            ),

        refresh_token=
            token_data.get(
                "refresh_token"
            ),

        token_uri=
            GOOGLE_TOKEN_URL,

        client_id=
            client_id,

        client_secret=
            client_secret,

        scopes=[
            GMAIL_SCOPE
        ],
    )


    # --------------------------------------------------------
    # RESTORE EXPIRY IF AVAILABLE
    # --------------------------------------------------------

    expiry = token_data.get(
        "expiry"
    )

    if expiry:

        try:

            from datetime import datetime

            credentials.expiry = (
                datetime.fromisoformat(
                    expiry
                )
            )

        except Exception:
            pass


    # --------------------------------------------------------
    # REFRESH TOKEN
    # --------------------------------------------------------

    if credentials.expired:

        if not credentials.refresh_token:

            disconnect_gmail(
                user_id
            )

            return None


        try:

            credentials.refresh(
                Request()
            )

        except Exception:

            disconnect_gmail(
                user_id
            )

            return None


        # ----------------------------------------------------
        # SAVE REFRESHED TOKEN
        # ----------------------------------------------------

        updated_token = {
            **token_data,
            "access_token":
                credentials.token,
        }


        if credentials.expiry:

            updated_token[
                "expiry"
            ] = (
                credentials.expiry
                .isoformat()
            )


        save_gmail_token(
            user_id=user_id,
            user_email=email,
            token_data=updated_token
        )


    return credentials


# ============================================================
# GMAIL SERVICE
# ============================================================

def get_gmail_service():

    credentials = (
        get_gmail_credentials()
    )


    if not credentials:
        return None


    try:

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        return service

    except Exception:

        return None


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    user_id = (
        get_current_user_id()
    )


    if not user_id:
        return False


    email, token_json = (
        load_gmail_token(user_id)
    )


    if not token_json:
        return False


    credentials = (
        get_gmail_credentials()
    )


    return credentials is not None


# ============================================================
# TEST GMAIL CONNECTION
# ============================================================

def test_gmail_connection():

    service = (
        get_gmail_service()
    )


    if not service:
        return False


    try:

        # IMPORTANT:
        # Do NOT call users/me/profile.
        #
        # gmail.send doesn't grant profile permission.
        #
        # Instead, simply return True if credentials
        # are valid and service was created.

        return True

    except Exception:

        return False


# ============================================================
# END
# ============================================================

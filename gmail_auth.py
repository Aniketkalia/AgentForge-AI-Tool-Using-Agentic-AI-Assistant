# gmail_auth.py

import os
import json
import sqlite3
import secrets
import base64
import hashlib
import time
from urllib.parse import urlencode

import requests

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# CONFIG
# ============================================================

DB_PATH = "agentforge.db"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# IMPORTANT:
# Only request gmail.send.
# Do NOT request gmail.readonly or gmail.modify.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"

# OIDC scopes are used only to identify the Google account.
OIDC_SCOPES = "openid email"

SCOPES = f"{GMAIL_SCOPE} {OIDC_SCOPES}"


# ============================================================
# GOOGLE CREDENTIALS
# ============================================================

def get_google_client_id():
    try:
        import streamlit as st

        return st.secrets["GOOGLE_CLIENT_ID"]

    except Exception:
        return os.getenv("GOOGLE_CLIENT_ID")


def get_google_client_secret():
    try:
        import streamlit as st

        return st.secrets["GOOGLE_CLIENT_SECRET"]

    except Exception:
        return os.getenv("GOOGLE_CLIENT_SECRET")


def get_redirect_uri():
    """
    IMPORTANT:
    Set this to the EXACT URL registered in Google Cloud.

    Example:
    https://your-app.streamlit.app/
    """

    try:
        import streamlit as st

        # Recommended Streamlit Cloud setting
        redirect_uri = st.secrets.get("GOOGLE_REDIRECT_URI")

        if redirect_uri:
            return redirect_uri

    except Exception:
        pass

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

    if redirect_uri:
        return redirect_uri

    # Local development fallback
    return "http://localhost:8501/"


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    conn = get_connection()

    # Gmail tokens
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth (
            user_id TEXT PRIMARY KEY,
            user_email TEXT,
            token_json TEXT,
            created_at INTEGER,
            updated_at INTEGER
        )
        """
    )

    # OAuth state + PKCE verifier
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            code_verifier TEXT NOT NULL,
            created_at INTEGER
        )
        """
    )

    conn.commit()
    conn.close()


# Initialize database when module loads
init_database()


# ============================================================
# PKCE
# ============================================================

def generate_code_verifier():

    return secrets.token_urlsafe(64)


def generate_code_challenge(code_verifier):

    digest = hashlib.sha256(
        code_verifier.encode("utf-8")
    ).digest()

    challenge = base64.urlsafe_b64encode(
        digest
    ).decode("utf-8")

    return challenge.rstrip("=")


# ============================================================
# CURRENT USER
# ============================================================

def get_current_user_id():

    try:
        import streamlit as st

        if st.user.is_logged_in:
            return st.user.get("sub")

    except Exception:
        pass

    return None


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    init_database()

    client_id = get_google_client_id()

    redirect_uri = get_redirect_uri()

    user_id = get_current_user_id()

    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from Streamlit secrets."
        )

    if not user_id:
        raise RuntimeError(
            "AgentForge user is not logged in."
        )

    # Generate OAuth state
    state = secrets.token_urlsafe(32)

    # Generate PKCE verifier
    code_verifier = generate_code_verifier()

    code_challenge = generate_code_challenge(
        code_verifier
    )

    # Store state + verifier in DB
    conn = get_connection()

    conn.execute(
        """
        INSERT OR REPLACE INTO gmail_oauth_states
        (
            state,
            user_id,
            code_verifier,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            state,
            user_id,
            code_verifier,
            int(time.time()),
        ),
    )

    conn.commit()
    conn.close()

    params = {
        "client_id": client_id,

        "redirect_uri": redirect_uri,

        "response_type": "code",

        "scope": SCOPES,

        "access_type": "offline",

        "prompt": "consent",

        "include_granted_scopes": "false",

        "state": state,

        "code_challenge": code_challenge,

        "code_challenge_method": "S256",
    }

    return (
        GOOGLE_AUTH_URL
        + "?"
        + urlencode(params)
    )


# ============================================================
# LOAD OAUTH STATE
# ============================================================

def load_oauth_state(state):

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            user_id,
            code_verifier,
            created_at
        FROM gmail_oauth_states
        WHERE state = ?
        """,
        (state,),
    ).fetchone()

    conn.close()

    return row


# ============================================================
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    user_email,
    token_data,
):

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
            now,
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

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
        (user_id,),
    ).fetchone()

    conn.close()

    if not row:
        return None, None

    return (
        row["user_email"],
        row["token_json"],
    )


# ============================================================
# DELETE GMAIL TOKEN
# ============================================================

def disconnect_gmail(user_id=None):

    if user_id is None:
        user_id = get_current_user_id()

    if not user_id:
        return

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM gmail_oauth
        WHERE user_id = ?
        """,
        (user_id,),
    )

    conn.commit()
    conn.close()


# ============================================================
# GET CONNECTED EMAIL
# ============================================================

def get_connected_gmail_email():

    user_id = get_current_user_id()

    if not user_id:
        return None

    email, token_json = load_gmail_token(
        user_id
    )

    if not token_json:
        return None

    return email


# ============================================================
# CALLBACK
# ============================================================

def handle_gmail_callback():

    import streamlit as st

    init_database()

    code = st.query_params.get("code")

    state = st.query_params.get("state")

    error = st.query_params.get("error")

    # --------------------------------------------------------
    # GOOGLE RETURNED ERROR
    # --------------------------------------------------------

    if error:

        st.error(
            f"Gmail authorization failed: {error}"
        )

        return False

    if not code:

        return False

    if not state:

        st.error(
            "Gmail authorization failed: missing state."
        )

        return False

    # --------------------------------------------------------
    # LOAD STATE
    # --------------------------------------------------------

    oauth_state = load_oauth_state(
        state
    )

    if not oauth_state:

        st.error(
            "Gmail authorization session expired. "
            "Please click Connect Gmail again."
        )

        return False

    user_id = oauth_state["user_id"]

    code_verifier = oauth_state[
        "code_verifier"
    ]

    # --------------------------------------------------------
    # CURRENT AGENTFORGE USER CHECK
    # --------------------------------------------------------

    current_user_id = get_current_user_id()

    if (
        current_user_id
        and current_user_id != user_id
    ):

        st.error(
            "OAuth user mismatch. "
            "Please restart Gmail connection."
        )

        return False

    # --------------------------------------------------------
    # EXCHANGE CODE
    # --------------------------------------------------------

    client_id = get_google_client_id()

    client_secret = get_google_client_secret()

    redirect_uri = get_redirect_uri()

    if not client_id:
        st.error(
            "GOOGLE_CLIENT_ID is missing."
        )

        return False

    if not client_secret:
        st.error(
            "GOOGLE_CLIENT_SECRET is missing."
        )

        return False

    token_payload = {

        "code": code,

        "client_id": client_id,

        "client_secret": client_secret,

        "redirect_uri": redirect_uri,

        "grant_type": "authorization_code",

        "code_verifier": code_verifier,
    }

    try:

        response = requests.post(
            GOOGLE_TOKEN_URL,
            data=token_payload,
            timeout=30,
        )

        if response.status_code != 200:

            st.error(
                "Gmail token exchange failed: "
                f"{response.text}"
            )

            return False

        token_data = response.json()

    except Exception as e:

        st.error(
            f"Gmail token request failed: {e}"
        )

        return False

    # --------------------------------------------------------
    # CHECK ACCESS TOKEN
    # --------------------------------------------------------

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        st.error(
            "Google did not return an access token."
        )

        return False

    # --------------------------------------------------------
    # GET EMAIL FROM ID TOKEN
    #
    # IMPORTANT:
    # We DO NOT call:
    #
    # gmail.googleapis.com/gmail/v1/users/me/profile
    #
    # because gmail.send does not provide profile permission.
    # --------------------------------------------------------

    user_email = None

    id_token = token_data.get(
        "id_token"
    )

    if id_token:

        try:

            # Decode JWT payload without
            # needing Google's profile API.
            parts = id_token.split(".")

            if len(parts) == 3:

                payload = parts[1]

                payload += "=" * (
                    4 - len(payload) % 4
                )

                decoded = base64.urlsafe_b64decode(
                    payload
                )

                id_payload = json.loads(
                    decoded.decode("utf-8")
                )

                user_email = id_payload.get(
                    "email"
                )

        except Exception:
            user_email = None

    # --------------------------------------------------------
    # FALLBACK TO USERINFO
    # --------------------------------------------------------

    if not user_email:

        try:

            userinfo_response = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={
                    "Authorization":
                        f"Bearer {access_token}"
                },
                timeout=30,
            )

            if (
                userinfo_response.status_code
                == 200
            ):

                userinfo = (
                    userinfo_response.json()
                )

                user_email = userinfo.get(
                    "email"
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # LAST FALLBACK
    # --------------------------------------------------------

    if not user_email:

        user_email = (
            get_email_from_id_token(
                id_token
            )
        )

    if not user_email:

        st.error(
            "Gmail connected, but Google email "
            "address could not be detected."
        )

        return False

    # --------------------------------------------------------
    # SAVE TOKEN
    # --------------------------------------------------------

    save_gmail_token(
        user_id=user_id,
        user_email=user_email,
        token_data=token_data,
    )

    # --------------------------------------------------------
    # REMOVE USED OAUTH STATE
    # --------------------------------------------------------

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM gmail_oauth_states
        WHERE state = ?
        """,
        (state,),
    )

    conn.commit()
    conn.close()

    # --------------------------------------------------------
    # CLEAR URL PARAMETERS
    # --------------------------------------------------------

    try:

        st.query_params.clear()

    except Exception:
        pass

    return True


# ============================================================
# ID TOKEN EMAIL
# ============================================================

def get_email_from_id_token(
    id_token
):

    if not id_token:
        return None

    try:

        parts = id_token.split(".")

        if len(parts) != 3:
            return None

        payload = parts[1]

        payload += "=" * (
            4 - len(payload) % 4
        )

        decoded = base64.urlsafe_b64decode(
            payload
        )

        data = json.loads(
            decoded.decode("utf-8")
        )

        return data.get("email")

    except Exception:

        return None


# ============================================================
# CREATE GOOGLE CREDENTIALS
# ============================================================

def get_gmail_credentials():

    user_id = get_current_user_id()

    if not user_id:
        return None

    email, token_json = load_gmail_token(
        user_id
    )

    if not token_json:
        return None

    token_data = json.loads(
        token_json
    )

    credentials = Credentials(
        token=token_data.get(
            "access_token"
        ),

        refresh_token=token_data.get(
            "refresh_token"
        ),

        token_uri=GOOGLE_TOKEN_URL,

        client_id=get_google_client_id(),

        client_secret=get_google_client_secret(),

        scopes=[
            GMAIL_SCOPE
        ],
    )

    # --------------------------------------------------------
    # REFRESH EXPIRED TOKEN
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

            # Save refreshed token
            updated_token = {
                **token_data,
                "access_token":
                    credentials.token,
            }

            if credentials.expiry:

                updated_token[
                    "expiry"
                ] = credentials.expiry.isoformat()

            save_gmail_token(
                user_id=user_id,
                user_email=email,
                token_data=updated_token,
            )

        except Exception:

            disconnect_gmail(
                user_id
            )

            return None

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
            cache_discovery=False,
        )

        return service

    except Exception:

        return None


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    user_id = get_current_user_id()

    if not user_id:
        return False

    email, token_json = load_gmail_token(
        user_id
    )

    if not token_json:
        return False

    credentials = (
        get_gmail_credentials()
    )

    return credentials is not None

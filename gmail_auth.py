import os
import json
import sqlite3
import secrets
import base64
import hashlib
import time
from urllib.parse import urlencode

import requests
import streamlit as st

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# CONFIG
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

OIDC_SCOPES = "openid email"

SCOPES = f"{GMAIL_SCOPE} {OIDC_SCOPES}"


# ============================================================
# GOOGLE CREDENTIALS
# ============================================================

def get_google_client_id():

    try:
        value = st.secrets.get("GOOGLE_CLIENT_ID")

        if value:
            return value

    except Exception:
        pass

    return os.getenv("GOOGLE_CLIENT_ID")


def get_google_client_secret():

    try:
        value = st.secrets.get("GOOGLE_CLIENT_SECRET")

        if value:
            return value

    except Exception:
        pass

    return os.getenv("GOOGLE_CLIENT_SECRET")


def get_redirect_uri():

    try:
        value = st.secrets.get("GOOGLE_REDIRECT_URI")

        if value:
            return value

    except Exception:
        pass

    value = os.getenv("GOOGLE_REDIRECT_URI")

    if value:
        return value

    return "http://localhost:8501/"


# ============================================================
# DATABASE
# ============================================================

def get_connection():

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth (
            user_id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            token_json TEXT NOT NULL,
            created_at INTEGER,
            updated_at INTEGER
        )
        """
    )

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

        if st.user.is_logged_in:

            return st.user.get("sub")

    except Exception:

        pass

    return None


def get_current_user_email():

    try:

        if st.user.is_logged_in:

            return st.user.email

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

    if not get_google_client_secret():

        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from Streamlit secrets."
        )

    if not user_id:

        raise RuntimeError(
            "AgentForge user is not logged in."
        )

    # --------------------------------------------------------
    # Generate OAuth state
    # --------------------------------------------------------

    state = secrets.token_urlsafe(32)

    # --------------------------------------------------------
    # PKCE
    # --------------------------------------------------------

    code_verifier = generate_code_verifier()

    code_challenge = generate_code_challenge(
        code_verifier
    )

    # --------------------------------------------------------
    # Save state in SQLite
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Google OAuth parameters
    # --------------------------------------------------------

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
        VALUES (
            ?,
            ?,
            ?,
            COALESCE(
                (
                    SELECT created_at
                    FROM gmail_oauth
                    WHERE user_id = ?
                ),
                ?
            ),
            ?
        )
        """,
        (
            user_id,
            user_email,
            json.dumps(token_data),
            user_id,
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
# DISCONNECT GMAIL
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
# GET CONNECTED GMAIL EMAIL
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
# HANDLE GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    init_database()

    code = st.query_params.get("code")

    state = st.query_params.get("state")

    error = st.query_params.get("error")

    # --------------------------------------------------------
    # Google returned error
    # --------------------------------------------------------

    if error:

        st.error(
            f"Gmail authorization failed: {error}"
        )

        return False

    # --------------------------------------------------------
    # No code
    # --------------------------------------------------------

    if not code:

        return False

    # --------------------------------------------------------
    # No state
    # --------------------------------------------------------

    if not state:

        st.error(
            "Gmail authorization failed: missing state."
        )

        return False

    # --------------------------------------------------------
    # Load state
    # --------------------------------------------------------

    oauth_state = load_oauth_state(state)

    if not oauth_state:

        st.error(
            "Gmail authorization session expired. "
            "Please click Connect Gmail again."
        )

        return False

    user_id = oauth_state["user_id"]

    code_verifier = oauth_state["code_verifier"]

    # --------------------------------------------------------
    # Check logged-in user
    # --------------------------------------------------------

    current_user_id = get_current_user_id()

    if not current_user_id:

        st.error(
            "Your AgentForge login session expired. "
            "Please login again."
        )

        return False

    if current_user_id != user_id:

        st.error(
            "OAuth user mismatch. "
            "Please restart Gmail connection."
        )

        return False

    # --------------------------------------------------------
    # Credentials
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

    # --------------------------------------------------------
    # Exchange authorization code
    # --------------------------------------------------------

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
                "Gmail token exchange failed."
            )

            st.code(
                response.text
            )

            return False

        token_data = response.json()

    except Exception as e:

        st.error(
            f"Gmail token request failed: {e}"
        )

        return False

    # --------------------------------------------------------
    # Access token
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
    # Get email from ID token
    # --------------------------------------------------------

    user_email = None

    id_token = token_data.get(
        "id_token"
    )

    if id_token:

        try:

            user_email = get_email_from_id_token(
                id_token
            )

        except Exception:

            user_email = None

    # --------------------------------------------------------
    # Userinfo fallback
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

            if userinfo_response.status_code == 200:

                userinfo = (
                    userinfo_response.json()
                )

                user_email = userinfo.get(
                    "email"
                )

        except Exception:

            pass

    # --------------------------------------------------------
    # Final email check
    # --------------------------------------------------------

    if not user_email:

        st.error(
            "Gmail connected, but Google email "
            "address could not be detected."
        )

        return False

    # --------------------------------------------------------
    # Match AgentForge account
    # --------------------------------------------------------

    logged_in_email = (
        get_current_user_email()
    )

    if (
        logged_in_email
        and user_email.lower()
        != logged_in_email.lower()
    ):

        st.error(
            "❌ Google account mismatch."
        )

        st.warning(
            f"AgentForge account: {logged_in_email}"
        )

        st.warning(
            f"Gmail account: {user_email}"
        )

        return False

    # --------------------------------------------------------
    # Save Gmail token in SQLite
    # --------------------------------------------------------

    save_gmail_token(
        user_id=user_id,
        user_email=user_email,
        token_data=token_data,
    )

    # --------------------------------------------------------
    # Delete used OAuth state
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
    # Clear callback parameters
    # --------------------------------------------------------

    try:

        st.query_params.clear()

    except Exception:

        pass

    # --------------------------------------------------------
    # Session cache
    # --------------------------------------------------------

    st.session_state["gmail_connected"] = True

    st.session_state["gmail_email"] = user_email

    return True


# ============================================================
# EMAIL FROM ID TOKEN
# ============================================================

def get_email_from_id_token(id_token):

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
# CREATE GMAIL CREDENTIALS
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

    try:

        token_data = json.loads(
            token_json
        )

    except Exception:

        disconnect_gmail(user_id)

        return None

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
    # Refresh expired token
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

            updated_token = {
                **token_data,
                "access_token":
                    credentials.token,
            }

            if credentials.expiry:

                updated_token["expiry"] = (
                    credentials.expiry.isoformat()
                )

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

    credentials = get_gmail_credentials()

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

    credentials = get_gmail_credentials()

    return credentials is not None

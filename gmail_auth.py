# ============================================================
# gmail_auth.py
# AgentForge AI - Gmail OAuth
# ============================================================

import os
import json
import sqlite3
import secrets
import base64
import hashlib
import hmac
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

# Gmail permission required to SEND email
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"

# Used only to identify the Google account
OIDC_SCOPES = "openid email"

# IMPORTANT:
# Keep these together and use exactly the same scopes
# every time.
SCOPES = f"{GMAIL_SCOPE} {OIDC_SCOPES}"


# ============================================================
# STREAMLIT
# ============================================================

def get_streamlit():
    import streamlit as st
    return st


# ============================================================
# GOOGLE CLIENT ID
# ============================================================

def get_google_client_id():
    try:
        st = get_streamlit()

        value = st.secrets.get("GOOGLE_CLIENT_ID")

        if value:
            return str(value).strip()

    except Exception:
        pass

    value = os.getenv("GOOGLE_CLIENT_ID")

    if value:
        return value.strip()

    return None


# ============================================================
# GOOGLE CLIENT SECRET
# ============================================================

def get_google_client_secret():
    try:
        st = get_streamlit()

        value = st.secrets.get("GOOGLE_CLIENT_SECRET")

        if value:
            return str(value).strip()

    except Exception:
        pass

    value = os.getenv("GOOGLE_CLIENT_SECRET")

    if value:
        return value.strip()

    return None


# ============================================================
# REDIRECT URI
# ============================================================

def get_redirect_uri():

    # Streamlit secrets
    try:
        st = get_streamlit()

        value = st.secrets.get("GOOGLE_REDIRECT_URI")

        if value:
            return str(value).strip()

    except Exception:
        pass

    # Environment variable
    value = os.getenv("GOOGLE_REDIRECT_URI")

    if value:
        return value.strip()

    # Local development
    return "http://localhost:8501/"


# ============================================================
# CURRENT AGENTFORGE USER
# ============================================================

def get_current_user_id():

    try:
        st = get_streamlit()

        if st.user.is_logged_in:
            return st.user.get("sub")

    except Exception:
        pass

    return None


def get_current_user_email():

    try:
        st = get_streamlit()

        if st.user.is_logged_in:
            return st.user.get("email")

    except Exception:
        pass

    return None


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

    # OAuth states
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at INTEGER
        )
        """
    )

    conn.commit()
    conn.close()


init_database()


# ============================================================
# OAUTH STATE SIGNING
# ============================================================

def get_cookie_secret():

    try:
        st = get_streamlit()

        value = st.secrets.get("auth", {}).get("cookie_secret")

        if value:
            return str(value)

    except Exception:
        pass

    value = os.getenv("COOKIE_SECRET")

    if value:
        return value

    # Development fallback
    return "agentforge-development-secret"


def create_signed_state(user_id):

    nonce = secrets.token_urlsafe(32)

    timestamp = str(int(time.time()))

    raw = f"{user_id}|{timestamp}|{nonce}"

    secret = get_cookie_secret().encode("utf-8")

    signature = hmac.new(
        secret,
        raw.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    state = base64.urlsafe_b64encode(
        f"{raw}|{signature}".encode("utf-8")
    ).decode("utf-8")

    return state


def verify_signed_state(state):

    try:

        secret = get_cookie_secret().encode("utf-8")

        decoded = base64.urlsafe_b64decode(
            state.encode("utf-8")
        ).decode("utf-8")

        parts = decoded.split("|")

        if len(parts) != 4:
            return None

        user_id = parts[0]
        timestamp = parts[1]
        nonce = parts[2]
        signature = parts[3]

        raw = f"{user_id}|{timestamp}|{nonce}"

        expected = hmac.new(
            secret,
            raw.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            signature,
            expected
        ):
            return None

        # State valid for 10 minutes
        if abs(
            int(time.time()) - int(timestamp)
        ) > 600:
            return None

        return user_id

    except Exception:
        return None


# ============================================================
# START GMAIL OAUTH
# ============================================================

def connect_gmail():

    client_id = get_google_client_id()
    redirect_uri = get_redirect_uri()
    user_id = get_current_user_id()

    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from Streamlit secrets."
        )

    client_secret = get_google_client_secret()

    if not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from Streamlit secrets."
        )

    if not redirect_uri:
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is missing."
        )

    if not user_id:
        raise RuntimeError(
            "AgentForge user is not logged in."
        )

    # --------------------------------------------------------
    # Create signed state
    # --------------------------------------------------------

    state = create_signed_state(user_id)

    # Also store in DB as backup
    try:

        conn = get_connection()

        conn.execute(
            """
            INSERT OR REPLACE INTO gmail_oauth_states
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

    except Exception:
        pass

    # --------------------------------------------------------
    # GOOGLE AUTH PARAMETERS
    # --------------------------------------------------------

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",

        # IMPORTANT:
        # Do not add gmail.readonly or gmail.modify.
        "scope": SCOPES,

        "access_type": "offline",

        # Forces Google to return refresh token
        "prompt": "consent",

        "include_granted_scopes": "false",

        "state": state,
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

    try:

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

        return row

    except Exception:
        return None


# ============================================================
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    user_email,
    token_data
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
            now
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    if not user_id:
        return None, None

    try:

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

    except Exception:
        return None, None


# ============================================================
# DISCONNECT GMAIL
# ============================================================

# IMPORTANT:
# streamlit_frontend.py may import this function.
# Keep it here.

def disconnect_gmail(user_id=None):

    if user_id is None:
        user_id = get_current_user_id()

    if not user_id:
        return False

    try:

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

    except Exception:
        return False


# ============================================================
# GET CONNECTED EMAIL
# ============================================================

def get_connected_gmail_email():

    user_id = get_current_user_id()

    if not user_id:
        return None

    email, token_json = load_gmail_token(user_id)

    if not token_json:
        return None

    return email


# ============================================================
# CREATE CREDENTIALS
# ============================================================

def get_gmail_credentials():

    user_id = get_current_user_id()

    if not user_id:
        return None

    email, token_json = load_gmail_token(user_id)

    if not token_json:
        return None

    try:

        token_data = json.loads(token_json)

    except Exception:
        disconnect_gmail(user_id)
        return None

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        disconnect_gmail(user_id)
        return None

    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=get_google_client_id(),
        client_secret=get_google_client_secret(),

        # Gmail API needs ONLY gmail.send.
        # OIDC scopes are not needed here.
        scopes=[
            GMAIL_SCOPE
        ],
    )

    # --------------------------------------------------------
    # REFRESH EXPIRED ACCESS TOKEN
    # --------------------------------------------------------

    if credentials.expired:

        if not credentials.refresh_token:
            disconnect_gmail(user_id)
            return None

        try:

            credentials.refresh(
                Request()
            )

            updated_token = dict(token_data)

            updated_token[
                "access_token"
            ] = credentials.token

            if credentials.expiry:

                updated_token[
                    "expiry"
                ] = credentials.expiry.isoformat()

            save_gmail_token(
                user_id=user_id,
                user_email=email,
                token_data=updated_token
            )

        except Exception:

            disconnect_gmail(user_id)

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
            cache_discovery=False
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

    email, token_json = load_gmail_token(user_id)

    if not email or not token_json:
        return False

    credentials = get_gmail_credentials()

    return credentials is not None


# ============================================================
# ID TOKEN EMAIL
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
# CALLBACK
# ============================================================

def handle_gmail_callback():

    st = get_streamlit()

    init_database()

    code = st.query_params.get("code")
    state = st.query_params.get("state")
    error = st.query_params.get("error")

    # --------------------------------------------------------
    # GOOGLE ERROR
    # --------------------------------------------------------

    if error:

        raise RuntimeError(
            f"Google authorization failed: {error}"
        )

    if not code:
        return False

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )

    # --------------------------------------------------------
    # VERIFY STATE
    # --------------------------------------------------------

    state_user_id = verify_signed_state(
        state
    )

    if not state_user_id:

        # Backup: check database
        oauth_state = load_oauth_state(
            state
        )

        if oauth_state:

            state_user_id = oauth_state[
                "user_id"
            ]

    if not state_user_id:

        raise RuntimeError(
            "Gmail OAuth state is invalid or expired. "
            "Please click Connect Gmail again."
        )

    # --------------------------------------------------------
    # CURRENT USER
    # --------------------------------------------------------

    current_user_id = get_current_user_id()

    if not current_user_id:

        raise RuntimeError(
            "AgentForge login session is missing. "
            "Please login again."
        )

    if current_user_id != state_user_id:

        raise RuntimeError(
            "OAuth user mismatch. "
            "Please restart Gmail connection."
        )

    # --------------------------------------------------------
    # GOOGLE CREDENTIALS
    # --------------------------------------------------------

    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    redirect_uri = get_redirect_uri()

    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from Streamlit secrets."
        )

    if not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from Streamlit secrets."
        )

    if not redirect_uri:
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is missing."
        )

    # --------------------------------------------------------
    # TOKEN EXCHANGE
    # --------------------------------------------------------

    token_payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
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

    if response.status_code != 200:

        raise RuntimeError(
            "Google token exchange failed: "
            + response.text
        )

    try:

        token_data = response.json()

    except Exception:

        raise RuntimeError(
            "Google returned an invalid token response."
        )

    # --------------------------------------------------------
    # ACCESS TOKEN
    # --------------------------------------------------------

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        raise RuntimeError(
            "Google did not return an access token."
        )

    # --------------------------------------------------------
    # GET EMAIL
    # --------------------------------------------------------
    #
    # We intentionally DO NOT call:
    #
    # gmail.googleapis.com/gmail/v1/users/me/profile
    #
    # because gmail.send does not give Gmail profile permission.
    #
    # Instead Google returns an ID token because we requested
    # openid/email.
    # --------------------------------------------------------

    user_email = None

    id_token = token_data.get(
        "id_token"
    )

    if id_token:

        user_email = get_email_from_id_token(
            id_token
        )

    # --------------------------------------------------------
    # FALLBACK USERINFO
    # --------------------------------------------------------

    if not user_email:

        try:

            userinfo_response = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={
                    "Authorization":
                        f"Bearer {access_token}"
                },
                timeout=30
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
    # FINAL EMAIL CHECK
    # --------------------------------------------------------

    if not user_email:

        raise RuntimeError(
            "Gmail connected, but Google email "
            "address could not be detected."
        )

    # --------------------------------------------------------
    # SECURITY:
    # Make sure Gmail account is same as AgentForge login
    # --------------------------------------------------------

    logged_in_email = (
        get_current_user_email()
    )

    if (
        logged_in_email
        and user_email.lower()
        != logged_in_email.lower()
    ):

        raise RuntimeError(
            "Google account mismatch. "
            f"AgentForge login: {logged_in_email}, "
            f"Gmail account: {user_email}. "
            "Please use the same Google account."
        )

    # --------------------------------------------------------
    # SAVE TOKEN
    # --------------------------------------------------------

    save_gmail_token(
        user_id=state_user_id,
        user_email=user_email,
        token_data=token_data
    )

    # --------------------------------------------------------
    # DELETE USED STATE
    # --------------------------------------------------------

    try:

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

    except Exception:
        pass

    return True

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time

import streamlit as st

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIGURATION
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "gmail_tokens.db"
)


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return conn


def init_database():

    conn = get_db_connection()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_tokens (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_oauth (
                nonce TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )

        conn.commit()

    finally:

        conn.close()


init_database()


# ============================================================
# STREAMLIT AUTH SECRET
# ============================================================

def get_auth_secret():

    try:

        secret = st.secrets["auth"]["cookie_secret"]

    except Exception as e:

        raise RuntimeError(
            "Streamlit [auth] cookie_secret is missing."
        ) from e

    if not secret:

        raise RuntimeError(
            "Streamlit [auth] cookie_secret is empty."
        )

    return str(secret)


# ============================================================
# GMAIL OAUTH CONFIG
# ============================================================

def get_gmail_config():

    try:

        client_id = (
            st.secrets["gmail_oauth"]["client_id"]
        )

        client_secret = (
            st.secrets["gmail_oauth"]["client_secret"]
        )

        redirect_uri = (
            st.secrets["gmail_oauth"]["redirect_uri"]
        )

    except Exception as e:

        raise RuntimeError(
            "Missing Gmail OAuth configuration. "
            "Check [gmail_oauth] in Streamlit secrets."
        ) from e

    if not client_id:

        raise RuntimeError(
            "gmail_oauth.client_id is missing."
        )

    if not client_secret:

        raise RuntimeError(
            "gmail_oauth.client_secret is missing."
        )

    if not redirect_uri:

        raise RuntimeError(
            "gmail_oauth.redirect_uri is missing."
        )

    return (
        str(client_id),
        str(client_secret),
        str(redirect_uri)
    )


# ============================================================
# CREATE GMAIL OAUTH FLOW
# ============================================================

def get_gmail_flow():

    client_id, client_secret, redirect_uri = (
        get_gmail_config()
    )

    config = {

        "web": {

            "client_id": client_id,

            "client_secret": client_secret,

            "auth_uri":
                "https://accounts.google.com/o/oauth2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",

            "redirect_uris": [
                redirect_uri
            ]
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=GMAIL_SCOPES
    )

    flow.redirect_uri = redirect_uri

    return flow


# ============================================================
# PKCE
# ============================================================

def create_code_verifier():

    return secrets.token_urlsafe(64)


def create_code_challenge(code_verifier):

    digest = hashlib.sha256(
        code_verifier.encode("ascii")
    ).digest()

    challenge = (
        base64.urlsafe_b64encode(digest)
        .decode("ascii")
        .rstrip("=")
    )

    return challenge


# ============================================================
# OAUTH STATE
# ============================================================

def create_state(user_id, nonce):

    payload = {

        "user_id": str(user_id),

        "nonce": str(nonce),

        "timestamp": int(time.time())
    }

    payload_json = json.dumps(
        payload,
        separators=(",", ":")
    )

    payload_encoded = (
        base64.urlsafe_b64encode(
            payload_json.encode("utf-8")
        )
        .decode("ascii")
    )

    secret = get_auth_secret()

    signature = hmac.new(
        secret.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return (
        payload_encoded
        + "."
        + signature
    )


def verify_state(state):

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )

    parts = state.split(".")

    if len(parts) != 2:

        raise RuntimeError(
            "Invalid Gmail OAuth state."
        )

    payload_encoded = parts[0]

    received_signature = parts[1]

    secret = get_auth_secret()

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(
        received_signature,
        expected_signature
    ):

        raise RuntimeError(
            "Invalid Gmail OAuth state signature."
        )

    try:

        payload_json = (
            base64.urlsafe_b64decode(
                payload_encoded
            )
            .decode("utf-8")
        )

        payload = json.loads(
            payload_json
        )

    except Exception as e:

        raise RuntimeError(
            "Invalid Gmail OAuth state payload."
        ) from e

    user_id = payload.get("user_id")

    nonce = payload.get("nonce")

    timestamp = payload.get("timestamp")

    if not user_id:

        raise RuntimeError(
            "OAuth user ID is missing."
        )

    if not nonce:

        raise RuntimeError(
            "OAuth nonce is missing."
        )

    if timestamp is None:

        raise RuntimeError(
            "OAuth timestamp is missing."
        )

    try:

        timestamp = int(timestamp)

    except Exception:

        raise RuntimeError(
            "Invalid OAuth timestamp."
        )

    now = int(time.time())

    if now - timestamp > 600:

        raise RuntimeError(
            "Gmail OAuth state has expired. "
            "Please click Connect Gmail again."
        )

    if timestamp > now + 60:

        raise RuntimeError(
            "Invalid Gmail OAuth timestamp."
        )

    return (
        str(user_id),
        str(nonce)
    )


# ============================================================
# SAVE OAUTH VERIFIER
# ============================================================

def save_oauth_verifier(
    nonce,
    user_id,
    code_verifier
):

    conn = get_db_connection()

    try:

        conn.execute(
            """
            INSERT OR REPLACE INTO gmail_oauth
            (
                nonce,
                user_id,
                code_verifier,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                str(nonce),
                str(user_id),
                str(code_verifier),
                int(time.time())
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# LOAD OAUTH VERIFIER
# ============================================================

def load_oauth_verifier(nonce):

    conn = get_db_connection()

    try:

        cursor = conn.execute(
            """
            SELECT
                user_id,
                code_verifier,
                created_at
            FROM gmail_oauth
            WHERE nonce = ?
            """,
            (str(nonce),)
        )

        row = cursor.fetchone()

    finally:

        conn.close()

    if not row:

        return None

    user_id = row[0]

    code_verifier = row[1]

    created_at = row[2]

    if int(time.time()) - int(created_at) > 600:

        delete_oauth_verifier(nonce)

        return None

    return {

        "user_id": str(user_id),

        "code_verifier": str(code_verifier)
    }


# ============================================================
# DELETE OAUTH VERIFIER
# ============================================================

def delete_oauth_verifier(nonce):

    conn = get_db_connection()

    try:

        conn.execute(
            """
            DELETE FROM gmail_oauth
            WHERE nonce = ?
            """,
            (str(nonce),)
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# START GMAIL CONNECTION
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:

        raise RuntimeError(
            "Please login to AgentForge first."
        )

    user_id = st.user.get("sub")

    if not user_id:

        raise RuntimeError(
            "Unable to identify AgentForge user."
        )

    # --------------------------------------------------------
    # CREATE PKCE
    # --------------------------------------------------------

    code_verifier = create_code_verifier()

    code_challenge = create_code_challenge(
        code_verifier
    )

    # --------------------------------------------------------
    # CREATE NONCE
    # --------------------------------------------------------

    nonce = secrets.token_urlsafe(32)

    # --------------------------------------------------------
    # SAVE VERIFIER IN SQLITE
    # --------------------------------------------------------

    save_oauth_verifier(
        nonce=nonce,
        user_id=user_id,
        code_verifier=code_verifier
    )

    # --------------------------------------------------------
    # CREATE STATE
    # --------------------------------------------------------

    state = create_state(
        user_id=user_id,
        nonce=nonce
    )

    # --------------------------------------------------------
    # CREATE FLOW
    # --------------------------------------------------------

    flow = get_gmail_flow()

    authorization_url, _ = (
        flow.authorization_url(
            access_type="offline",

            include_granted_scopes="true",

            prompt="consent",

            login_hint=st.user.email,

            state=state,

            code_challenge=code_challenge,

            code_challenge_method="S256"
        )
    )

    return authorization_url


# ============================================================
# SAVE GMAIL TOKEN
# ============================================================

def save_gmail_token(
    user_id,
    email,
    credentials
):

    token_json = credentials.to_json()

    conn = get_db_connection()

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
                str(user_id),
                str(email),
                token_json,
                int(time.time())
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# LOAD GMAIL TOKEN
# ============================================================

def load_gmail_token(user_id):

    if not user_id:

        return None, None

    conn = get_db_connection()

    try:

        cursor = conn.execute(
            """
            SELECT
                email,
                token_json
            FROM gmail_tokens
            WHERE user_id = ?
            """,
            (str(user_id),)
        )

        row = cursor.fetchone()

    finally:

        conn.close()

    if not row:

        return None, None

    return (
        row[0],
        row[1]
    )


# ============================================================
# DELETE GMAIL TOKEN
# ============================================================

def delete_gmail_token(user_id):

    if not user_id:

        return

    conn = get_db_connection()

    try:

        conn.execute(
            """
            DELETE FROM gmail_tokens
            WHERE user_id = ?
            """,
            (str(user_id),)
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
    # GOOGLE ERROR
    # --------------------------------------------------------

    if error:

        raise RuntimeError(
            f"Google authorization failed: {error}"
        )

    # --------------------------------------------------------
    # CODE
    # --------------------------------------------------------

    if not code:

        raise RuntimeError(
            "Gmail authorization code was not received."
        )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )

    # --------------------------------------------------------
    # VERIFY STATE
    # --------------------------------------------------------

    oauth_user_id, nonce = verify_state(
        state
    )

    # --------------------------------------------------------
    # LOAD PKCE VERIFIER
    # --------------------------------------------------------

    oauth_data = load_oauth_verifier(
        nonce
    )

    if not oauth_data:

        raise RuntimeError(
            "Gmail OAuth code verifier is missing "
            "or expired. Please click Connect Gmail again."
        )

    stored_user_id = oauth_data[
        "user_id"
    ]

    code_verifier = oauth_data[
        "code_verifier"
    ]

    # --------------------------------------------------------
    # CHECK USER
    # --------------------------------------------------------

    if stored_user_id != str(oauth_user_id):

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            "Gmail OAuth user mismatch."
        )

    if not st.user.is_logged_in:

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            "AgentForge login session is missing. "
            "Please login again."
        )

    current_user_id = st.user.get(
        "sub"
    )

    agentforge_email = st.user.email

    if not current_user_id:

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            "Unable to identify AgentForge user."
        )

    if str(current_user_id) != str(oauth_user_id):

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            "AgentForge user mismatch."
        )

    # ========================================================
    # EXCHANGE AUTHORIZATION CODE
    # ========================================================

    try:

        flow = get_gmail_flow()

        flow.fetch_token(
            code=code,
            code_verifier=code_verifier
        )

        credentials = flow.credentials

    except Exception as e:

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            f"Google token exchange failed: {e}"
        ) from e

    # ========================================================
    # CHECK THAT GMAIL SEND SCOPE WAS GRANTED
    # ========================================================

    granted_scopes = credentials.scopes or []

    gmail_send_scope = (
        "https://www.googleapis.com/auth/gmail.send"
    )

    if gmail_send_scope not in granted_scopes:

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            "Google did not grant Gmail send permission. "
            "Please authorize Gmail again."
        )

    # ========================================================
    # CREATE GMAIL SERVICE
    # ========================================================

    try:

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        # IMPORTANT:
        #
        # DO NOT CALL:
        #
        # service.users().getProfile(...)
        #
        # because gmail.send does not provide permission
        # for that API.
        #

    except Exception as e:

        delete_oauth_verifier(nonce)

        raise RuntimeError(
            f"Unable to create Gmail service: {e}"
        ) from e

    # ========================================================
    # USE AGENTFORGE GOOGLE EMAIL
    # ========================================================

    gmail_email = agentforge_email

    # ========================================================
    # SAVE TOKEN
    # ========================================================

    save_gmail_token(
        user_id=current_user_id,
        email=gmail_email,
        credentials=credentials
    )

    # ========================================================
    # DELETE OAUTH DATA
    # ========================================================

    delete_oauth_verifier(nonce)

    # ========================================================
    # UPDATE STREAMLIT SESSION
    # ========================================================

    st.session_state[
        "gmail_connected"
    ] = True

    st.session_state[
        "gmail_email"
    ] = gmail_email

    return True


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

def is_gmail_connected():

    if not st.user.is_logged_in:

        return False

    user_id = st.user.get("sub")

    if not user_id:

        return False

    email, token_json = load_gmail_token(
        user_id
    )

    if not email or not token_json:

        return False

    try:

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(token_json),
                GMAIL_SCOPES
            )
        )

        granted_scopes = (
            credentials.scopes or []
        )

        return (
            "https://www.googleapis.com/auth/gmail.send"
            in granted_scopes
        )

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

    email, token_json = load_gmail_token(
        user_id
    )

    if not email or not token_json:

        return None

    return email


# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service():

    if not st.user.is_logged_in:

        return None

    user_id = st.user.get("sub")

    if not user_id:

        return None

    email, token_json = load_gmail_token(
        user_id
    )

    if not token_json:

        return None

    try:

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(token_json),
                GMAIL_SCOPES
            )
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
            f"Gmail service error: {e}"
        )

        return None

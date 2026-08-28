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
# GMAIL SCOPES
# ============================================================

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# DATABASE
# ============================================================

DB_PATH = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
    ),
    "gmail_tokens.db"
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

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
# DATABASE CONNECTION
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


# ============================================================
# OAUTH SECRET
# ============================================================

def get_oauth_secret():

    try:

        secret = st.secrets[
            "auth"
        ][
            "cookie_secret"
        ]

    except Exception:

        raise RuntimeError(
            "Streamlit [auth] cookie_secret is missing."
        )

    if not secret:

        raise RuntimeError(
            "Streamlit auth cookie_secret is empty."
        )

    return str(secret)


# ============================================================
# CREATE PKCE CODE VERIFIER
# ============================================================

def create_code_verifier():

    return secrets.token_urlsafe(64)


# ============================================================
# CREATE CODE CHALLENGE
# ============================================================

def create_code_challenge(
    code_verifier
):

    digest = hashlib.sha256(
        code_verifier.encode("ascii")
    ).digest()

    challenge = (
        base64.urlsafe_b64encode(
            digest
        )
        .decode("ascii")
        .rstrip("=")
    )

    return challenge


# ============================================================
# CREATE SIGNED STATE
# ============================================================

def create_oauth_state(
    user_id,
    nonce
):

    payload = {

        "user_id": str(user_id),

        "nonce": str(nonce),

        "timestamp": int(
            time.time()
        )
    }


    payload_json = json.dumps(
        payload,
        separators=(
            ",",
            ":"
        )
    )


    payload_encoded = (
        base64.urlsafe_b64encode(
            payload_json.encode()
        )
        .decode()
    )


    secret = get_oauth_secret()


    signature = hmac.new(
        secret.encode(),
        payload_encoded.encode(),
        hashlib.sha256
    ).hexdigest()


    return (
        payload_encoded
        + "."
        + signature
    )


# ============================================================
# VERIFY STATE
# ============================================================

def verify_oauth_state(
    state
):

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


    secret = get_oauth_secret()


    expected_signature = hmac.new(
        secret.encode(),
        payload_encoded.encode(),
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
            .decode()
        )


        payload = json.loads(
            payload_json
        )

    except Exception:

        raise RuntimeError(
            "Invalid Gmail OAuth state payload."
        )


    user_id = payload.get(
        "user_id"
    )

    nonce = payload.get(
        "nonce"
    )

    timestamp = payload.get(
        "timestamp"
    )


    if not user_id:

        raise RuntimeError(
            "OAuth user ID is missing."
        )


    if not nonce:

        raise RuntimeError(
            "OAuth nonce is missing."
        )


    if not timestamp:

        raise RuntimeError(
            "OAuth timestamp is missing."
        )


    try:

        timestamp = int(
            timestamp
        )

    except Exception:

        raise RuntimeError(
            "Invalid OAuth timestamp."
        )


    now = int(
        time.time()
    )


    # OAuth state valid for 10 minutes
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
# SAVE PKCE VERIFIER
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
# LOAD PKCE VERIFIER
# ============================================================

def load_oauth_verifier(
    nonce
):

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
            (
                str(nonce),
            )
        )

        row = cursor.fetchone()

    finally:

        conn.close()


    if not row:

        return None


    user_id = row[0]

    code_verifier = row[1]

    created_at = row[2]


    # Expire after 10 minutes
    if int(time.time()) - int(
        created_at
    ) > 600:

        delete_oauth_verifier(
            nonce
        )

        return None


    return {
        "user_id": user_id,
        "code_verifier": code_verifier
    }


# ============================================================
# DELETE PKCE VERIFIER
# ============================================================

def delete_oauth_verifier(
    nonce
):

    conn = get_db_connection()

    try:

        conn.execute(
            """
            DELETE FROM gmail_oauth
            WHERE nonce = ?
            """,
            (
                str(nonce),
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# GMAIL OAUTH FLOW
# ============================================================

def get_gmail_flow():

    try:

        client_id = st.secrets[
            "gmail_oauth"
        ][
            "client_id"
        ]

        client_secret = st.secrets[
            "gmail_oauth"
        ][
            "client_secret"
        ]

        redirect_uri = st.secrets[
            "gmail_oauth"
        ][
            "redirect_uri"
        ]

    except Exception as e:

        raise RuntimeError(
            "Missing [gmail_oauth] configuration "
            "in Streamlit secrets."
        ) from e


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
# CONNECT GMAIL
# ============================================================

def connect_gmail():

    if not st.user.is_logged_in:

        raise RuntimeError(
            "Please login to AgentForge first."
        )


    user_id = st.user.get(
        "sub"
    )


    if not user_id:

        raise RuntimeError(
            "Unable to identify AgentForge user."
        )


    # --------------------------------------------------------
    # PKCE
    # --------------------------------------------------------

    code_verifier = (
        create_code_verifier()
    )


    code_challenge = (
        create_code_challenge(
            code_verifier
        )
    )


    # --------------------------------------------------------
    # NONCE
    # --------------------------------------------------------

    nonce = secrets.token_urlsafe(
        32
    )


    # --------------------------------------------------------
    # SAVE VERIFIER IN SQLITE
    # --------------------------------------------------------

    save_oauth_verifier(
        nonce=nonce,
        user_id=user_id,
        code_verifier=code_verifier
    )


    # --------------------------------------------------------
    # CREATE SIGNED STATE
    # --------------------------------------------------------

    state = create_oauth_state(
        user_id=user_id,
        nonce=nonce
    )


    # --------------------------------------------------------
    # GOOGLE FLOW
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

def load_gmail_token(
    user_id
):

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
            (
                str(user_id),
            )
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

def delete_gmail_token(
    user_id
):

    if not user_id:

        return


    conn = get_db_connection()

    try:

        conn.execute(
            """
            DELETE FROM gmail_tokens
            WHERE user_id = ?
            """,
            (
                str(user_id),
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# GMAIL CALLBACK
# ============================================================

def handle_gmail_callback():

    params = st.query_params


    code = params.get(
        "code"
    )

    state = params.get(
        "state"
    )

    error = params.get(
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

    oauth_user_id, nonce = (
        verify_oauth_state(
            state
        )
    )


    # --------------------------------------------------------
    # GET PKCE VERIFIER
    # --------------------------------------------------------

    oauth_data = load_oauth_verifier(
        nonce
    )


    if not oauth_data:

        raise RuntimeError(
            "Gmail OAuth code verifier is missing or expired. "
            "Please click Connect Gmail again."
        )


    stored_user_id = str(
        oauth_data["user_id"]
    )


    code_verifier = (
        oauth_data["code_verifier"]
    )


    # --------------------------------------------------------
    # USER MATCH
    # --------------------------------------------------------

    if (
        stored_user_id
        != str(oauth_user_id)
    ):

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "Gmail OAuth user mismatch."
        )


    # --------------------------------------------------------
    # AGENTFORGE LOGIN
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "AgentForge login session is missing. "
            "Please login again."
        )


    current_user_id = st.user.get(
        "sub"
    )


    if not current_user_id:

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "Unable to identify current AgentForge user."
        )


    if (
        str(current_user_id)
        != str(oauth_user_id)
    ):

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "Gmail OAuth account mismatch."
        )


    # --------------------------------------------------------
    # CREATE FLOW
    # --------------------------------------------------------

    flow = get_gmail_flow()


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Pass the SAME code_verifier used to create
    # the authorization request.
    # --------------------------------------------------------

    flow.fetch_token(
        code=code,
        code_verifier=code_verifier
    )


    credentials = (
        flow.credentials
    )


    # --------------------------------------------------------
    # GMAIL SERVICE
    # --------------------------------------------------------

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False
    )


    # --------------------------------------------------------
    # GET GMAIL PROFILE
    # --------------------------------------------------------

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

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "Unable to determine Gmail account."
        )


    # --------------------------------------------------------
    # ACCOUNT MATCH
    # --------------------------------------------------------

    agentforge_email = (
        st.user.email
    )


    if (
        not agentforge_email
        or gmail_email.lower()
        != agentforge_email.lower()
    ):

        delete_oauth_verifier(
            nonce
        )

        raise RuntimeError(
            "Google account mismatch.\n\n"
            f"AgentForge account: {agentforge_email}\n"
            f"Gmail account: {gmail_email}\n\n"
            "Please use the same Google account."
        )


    # --------------------------------------------------------
    # SAVE TOKEN
    # --------------------------------------------------------

    save_gmail_token(
        user_id=current_user_id,
        email=gmail_email,
        credentials=credentials
    )


    # --------------------------------------------------------
    # DELETE USED VERIFIER
    # --------------------------------------------------------

    delete_oauth_verifier(
        nonce
    )


    # --------------------------------------------------------
    # UPDATE SESSION
    # --------------------------------------------------------

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


    user_id = st.user.get(
        "sub"
    )


    if not user_id:

        return False


    email, token_json = (
        load_gmail_token(
            user_id
        )
    )


    if not email or not token_json:

        return False


    try:

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(
                    token_json
                ),
                GMAIL_SCOPES
            )
        )


        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )


        service.users().getProfile(
            userId="me"
        ).execute()


        return True


    except Exception:

        return False


# ============================================================
# GET CONNECTED EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:

        return None


    user_id = st.user.get(
        "sub"
    )


    if not user_id:

        return None


    email, token_json = (
        load_gmail_token(
            user_id
        )
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


    user_id = st.user.get(
        "sub"
    )


    if not user_id:

        return None


    email, token_json = (
        load_gmail_token(
            user_id
        )
    )


    if not token_json:

        return None


    try:

        credentials = (
            Credentials.from_authorized_user_info(
                json.loads(
                    token_json
                ),
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

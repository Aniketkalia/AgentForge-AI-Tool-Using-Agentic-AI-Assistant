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


# ============================================================
# DATABASE
# ============================================================

# Keep the database outside the source-code logic.
# Streamlit Cloud can use this path while the app instance exists.
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
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

        conn.commit()

    finally:

        conn.close()


# Initialize database when module loads
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

    """
    Uses Streamlit auth cookie_secret as the signing secret.

    This allows us to create a signed OAuth state without
    depending on st.session_state.
    """

    try:

        secret = st.secrets["auth"]["cookie_secret"]

    except Exception:

        try:

            secret = st.secrets["OAUTH_STATE_SECRET"]

        except Exception:

            raise RuntimeError(
                "OAuth signing secret is missing. "
                "Add [auth] cookie_secret to Streamlit secrets."
            )

    if not secret:

        raise RuntimeError(
            "OAuth signing secret is empty."
        )

    return str(secret)


# ============================================================
# CREATE SIGNED STATE
# ============================================================

def create_oauth_state(user_id):

    """
    Creates:

        random nonce
        +
        current timestamp
        +
        user_id

    Then signs the payload using HMAC-SHA256.

    The state is self-contained, so it survives opening
    Google OAuth in another browser tab.
    """

    if not user_id:

        raise RuntimeError(
            "Unable to create Gmail OAuth state: user ID missing."
        )

    timestamp = str(int(time.time()))

    nonce = secrets.token_urlsafe(32)

    payload = {
        "user_id": str(user_id),
        "timestamp": timestamp,
        "nonce": nonce
    }

    payload_json = json.dumps(
        payload,
        separators=(",", ":")
    )

    payload_encoded = base64.urlsafe_b64encode(
        payload_json.encode()
    ).decode()
    
    secret = get_oauth_secret()

    signature = hmac.new(
        secret.encode(),
        payload_encoded.encode(),
        hashlib.sha256
    ).hexdigest()

    state = (
        payload_encoded
        + "."
        + signature
    )

    return state


# ============================================================
# VERIFY SIGNED STATE
# ============================================================

def verify_oauth_state(state):

    """
    Verifies:

    1. State exists
    2. Signature is valid
    3. Payload is valid
    4. State is not expired
    """

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )

    try:

        parts = state.split(".")

        if len(parts) != 2:

            raise RuntimeError(
                "Invalid Gmail OAuth state format."
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

        payload_json = base64.urlsafe_b64decode(
            payload_encoded.encode()
        ).decode()

        payload = json.loads(
            payload_json
        )

        user_id = payload.get(
            "user_id"
        )

        timestamp = int(
            payload.get(
                "timestamp",
                0
            )
        )

        nonce = payload.get(
            "nonce"
        )

        if not user_id or not nonce:

            raise RuntimeError(
                "Invalid Gmail OAuth state payload."
            )

        # State valid for 10 minutes
        current_time = int(
            time.time()
        )

        if current_time - timestamp > 600:

            raise RuntimeError(
                "Gmail OAuth state has expired. "
                "Please click Connect Gmail again."
            )

        if timestamp > current_time + 60:

            raise RuntimeError(
                "Invalid Gmail OAuth timestamp."
            )

        return user_id

    except RuntimeError:

        raise

    except Exception as e:

        raise RuntimeError(
            f"Unable to verify Gmail OAuth state: {e}"
        )


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
            "Gmail OAuth configuration is missing. "
            "Check [gmail_oauth] in Streamlit secrets."
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
# START GMAIL CONNECTION
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


    user_email = st.user.email


    # IMPORTANT:
    # State is NOT stored only in session_state.
    state = create_oauth_state(
        user_id
    )


    flow = get_gmail_flow()


    authorization_url, generated_state = (
        flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            login_hint=user_email,
            state=state
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
            INSERT INTO gmail_tokens
            (
                user_id,
                email,
                token_json,
                updated_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                email = excluded.email,
                token_json = excluded.token_json,
                updated_at = excluded.updated_at
            """,
            (
                str(user_id),
                email,
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
            (
                str(user_id),
            )
        )

        row = cursor.fetchone()

    finally:

        conn.close()


    if not row:

        return None, None


    return row[0], row[1]


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
            (
                str(user_id),
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# HANDLE GMAIL CALLBACK
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
            f"Google Gmail authorization failed: {error}"
        )


    # --------------------------------------------------------
    # CODE CHECK
    # --------------------------------------------------------

    if not code:

        raise RuntimeError(
            "Gmail authorization code was not received."
        )


    # --------------------------------------------------------
    # STATE CHECK
    # --------------------------------------------------------

    if not state:

        raise RuntimeError(
            "Gmail OAuth state is missing."
        )


    # --------------------------------------------------------
    # VERIFY STATE
    # --------------------------------------------------------

    oauth_user_id = verify_oauth_state(
        state
    )


    # --------------------------------------------------------
    # CURRENT AGENTFORGE USER
    # --------------------------------------------------------

    if not st.user.is_logged_in:

        raise RuntimeError(
            "AgentForge login session is missing. "
            "Please login again."
        )


    current_user_id = st.user.get(
        "sub"
    )


    if not current_user_id:

        raise RuntimeError(
            "Unable to identify current AgentForge user."
        )


    # State belongs to this user
    if str(oauth_user_id) != str(current_user_id):

        raise RuntimeError(
            "Gmail OAuth user mismatch."
        )


    # --------------------------------------------------------
    # EXCHANGE AUTHORIZATION CODE
    # --------------------------------------------------------

    flow = get_gmail_flow()


    flow.fetch_token(
        code=code
    )


    credentials = flow.credentials


    # --------------------------------------------------------
    # BUILD GMAIL SERVICE
    # --------------------------------------------------------

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False
    )


    # --------------------------------------------------------
    # GET GMAIL ACCOUNT
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

        raise RuntimeError(
            "Unable to determine Gmail account."
        )


    # --------------------------------------------------------
    # AGENTFORGE EMAIL
    # --------------------------------------------------------

    agentforge_email = st.user.email


    # --------------------------------------------------------
    # ACCOUNT MATCH
    # --------------------------------------------------------

    if (
        not agentforge_email
        or gmail_email.lower()
        != agentforge_email.lower()
    ):

        raise RuntimeError(
            "Google account mismatch.\n\n"
            f"AgentForge account: {agentforge_email}\n"
            f"Gmail account: {gmail_email}\n\n"
            "Please authorize Gmail using the same "
            "Google account used to login to AgentForge."
        )


    # --------------------------------------------------------
    # SAVE TOKEN
    # --------------------------------------------------------

    save_gmail_token(
        current_user_id,
        gmail_email,
        credentials
    )


    # --------------------------------------------------------
    # SESSION CACHE
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


        # Build service.
        # If token is expired and has refresh token,
        # Google credentials can refresh when used.

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )


        # Verify token actually works
        service.users().getProfile(
            userId="me"
        ).execute()


        return True


    except Exception:

        return False


# ============================================================
# GET CONNECTED GMAIL EMAIL
# ============================================================

def get_connected_gmail_email():

    if not st.user.is_logged_in:

        return None


    user_id = st.user.get(
        "sub"
    )


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


    user_id = st.user.get(
        "sub"
    )


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

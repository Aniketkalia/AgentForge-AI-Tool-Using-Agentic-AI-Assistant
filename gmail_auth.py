# ============================================================
# gmail_auth.py
# AgentForge AI
#
# Gmail OAuth:
# - Gmail send permission
# - User email permission
# - Works with Google OAuth
# - OAuth state survives a NEW TAB
# - No PKCE / code_verifier problem
# - No Gmail users/me/profile API call
# ============================================================

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from email.message import EmailMessage
from urllib.parse import urlencode

import streamlit as st

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# CONFIG
# ============================================================

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

GOOGLE_USERINFO_ENDPOINT = (
    "https://openidconnect.googleapis.com/v1/userinfo"
)

GMAIL_SEND_SCOPE = (
    "https://www.googleapis.com/auth/gmail.send"
)

USERINFO_EMAIL_SCOPE = (
    "https://www.googleapis.com/auth/userinfo.email"
)

USERINFO_PROFILE_SCOPE = (
    "https://www.googleapis.com/auth/userinfo.profile"
)

OPENID_SCOPE = "openid"


# IMPORTANT:
# These scopes MUST remain identical between authorization
# and token exchange.
SCOPES = [
    OPENID_SCOPE,
    GMAIL_SEND_SCOPE,
    USERINFO_PROFILE_SCOPE,
    USERINFO_EMAIL_SCOPE,
]


# ============================================================
# STREAMLIT SECRETS
# ============================================================

def _get_secret(name: str, default=None):
    """
    Read a Streamlit secret safely.
    """

    try:
        value = st.secrets.get(name)

        if value:
            return value
    except Exception:
        pass

    return os.getenv(name, default)


def _get_google_client_id():
    """
    Google OAuth client ID.
    """

    value = _get_secret("GOOGLE_CLIENT_ID")

    if not value:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from Streamlit secrets."
        )

    return str(value).strip()


def _get_google_client_secret():
    """
    Google OAuth client secret.
    """

    value = _get_secret("GOOGLE_CLIENT_SECRET")

    if not value:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from Streamlit secrets."
        )

    return str(value).strip()


def _get_redirect_uri():
    """
    Gmail OAuth callback URL.

    IMPORTANT:
    Use the same URL in:
    Google Cloud Console
    +
    Streamlit secrets.
    """

    value = _get_secret("GOOGLE_REDIRECT_URI")

    if value:
        return str(value).strip().rstrip("/")

    # Fallback for your Streamlit deployment
    return (
        "https://agentforge-ai-tool-using-agentic-ai-assistant-"
        "bxq2braoxb5b6yfa.streamlit.app"
    )


def _get_cookie_secret():
    """
    Secret used to sign OAuth state.

    This allows OAuth to work when Google opens
    in another browser tab/session.
    """

    value = _get_secret("GMAIL_OAUTH_STATE_SECRET")

    if value:
        return str(value)

    # Use Streamlit auth cookie secret as fallback.
    value = _get_secret("cookie_secret")

    if value:
        return str(value)

    try:
        auth_section = st.secrets.get("auth")

        if auth_section:
            value = auth_section.get("cookie_secret")

            if value:
                return str(value)
    except Exception:
        pass

    raise RuntimeError(
        "GMAIL_OAUTH_STATE_SECRET or auth.cookie_secret "
        "is missing from Streamlit secrets."
    )


# ============================================================
# SIGNED OAUTH STATE
# ============================================================

def _base64url_encode(data: bytes) -> str:
    return (
        base64.urlsafe_b64encode(data)
        .decode("utf-8")
        .rstrip("=")
    )


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)

    return base64.urlsafe_b64decode(
        data + padding
    )


def _create_signed_state(user_id: str, user_email: str):
    """
    Create a self-contained signed OAuth state.

    This is NOT stored in Streamlit session_state.

    Therefore it works when Google OAuth opens in a new tab.
    """

    payload = {
        "user_id": str(user_id),
        "user_email": str(user_email),
        "nonce": secrets.token_urlsafe(24),
        "created": int(time.time()),
    }

    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    encoded = _base64url_encode(raw)

    secret = _get_cookie_secret().encode("utf-8")

    signature = hmac.new(
        secret,
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    signature_encoded = _base64url_encode(
        signature
    )

    return f"{encoded}.{signature_encoded}"


def _verify_signed_state(state: str):
    """
    Verify OAuth state and return payload.
    """

    if not state:
        raise RuntimeError(
            "OAuth state is missing."
        )

    parts = state.split(".")

    if len(parts) != 2:
        raise RuntimeError(
            "Invalid OAuth state."
        )

    encoded = parts[0]
    received_signature = parts[1]

    secret = _get_cookie_secret().encode("utf-8")

    expected_signature = hmac.new(
        secret,
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    expected_encoded = _base64url_encode(
        expected_signature
    )

    if not hmac.compare_digest(
        received_signature,
        expected_encoded,
    ):
        raise RuntimeError(
            "Invalid OAuth state signature."
        )

    try:
        payload = json.loads(
            _base64url_decode(encoded)
            .decode("utf-8")
        )
    except Exception as e:
        raise RuntimeError(
            "Invalid OAuth state payload."
        ) from e

    created = int(
        payload.get("created", 0)
    )

    # OAuth state expires after 15 minutes.
    if (
        created <= 0
        or
        time.time() - created > 900
    ):
        raise RuntimeError(
            "OAuth state has expired. "
            "Please click Connect My Gmail again."
        )

    return payload


# ============================================================
# HTTP REQUEST
# ============================================================

def _post_form(url: str, data: dict):
    """
    POST form data without requiring requests directly.
    """

    import requests

    response = requests.post(
        url,
        data=data,
        timeout=30,
    )

    try:
        response_json = response.json()
    except Exception:
        response_json = {}

    if response.status_code >= 400:
        error_description = (
            response_json.get(
                "error_description"
            )
            or
            response_json.get("error")
            or
            response.text
        )

        raise RuntimeError(
            f"Google token exchange failed: "
            f"{error_description}"
        )

    return response_json


# ============================================================
# CREATE GMAIL AUTHORIZATION URL
# ============================================================

def connect_gmail():
    """
    Create Google Gmail OAuth URL.

    IMPORTANT:
    This function does NOT store OAuth state in
    st.session_state.

    Therefore the URL can safely be opened in a new tab.
    """

    if not st.user.is_logged_in:
        raise RuntimeError(
            "Please login to AgentForge first."
        )

    user_id = st.user.get("sub")
    user_email = st.user.get("email")

    if not user_id:
        raise RuntimeError(
            "Unable to identify AgentForge user."
        )

    if not user_email:
        raise RuntimeError(
            "Unable to identify AgentForge email."
        )

    client_id = _get_google_client_id()
    redirect_uri = _get_redirect_uri()

    state = _create_signed_state(
        user_id=user_id,
        user_email=user_email,
    )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",

        # EXACT same scopes used during token exchange.
        "scope": " ".join(SCOPES),

        "state": state,

        # Force Google consent when needed.
        "access_type": "offline",
        "prompt": "consent",

        # Helps Google select the current account.
        "login_hint": user_email,
    }

    authorization_url = (
        GOOGLE_AUTH_ENDPOINT
        + "?"
        + urlencode(params)
    )

    return authorization_url


# ============================================================
# GOOGLE USER INFO
# ============================================================

def _get_google_userinfo(access_token: str):
    """
    Get the Gmail/Google account email.

    This uses userinfo.email permission instead of
    Gmail users/me/profile.

    Therefore we avoid the previous 403:
    'insufficient authentication scopes'.
    """

    import requests

    response = requests.get(
        GOOGLE_USERINFO_ENDPOINT,
        headers={
            "Authorization":
                f"Bearer {access_token}"
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            "Unable to read Google account information: "
            f"{response.text}"
        )

    return response.json()


# ============================================================
# CALLBACK
# ============================================================

def handle_gmail_callback():
    """
    Handle Google OAuth callback.

    Expected:
        ?code=...
        &state=...
    """

    params = st.query_params

    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    # --------------------------------------------------------
    # No callback
    # --------------------------------------------------------

    if not code and not error:
        return False

    # --------------------------------------------------------
    # Google returned error
    # --------------------------------------------------------

    if error:
        description = params.get(
            "error_description",
            error,
        )

        raise RuntimeError(
            f"Google authorization failed: "
            f"{description}"
        )

    # --------------------------------------------------------
    # Login check
    # --------------------------------------------------------

    if not st.user.is_logged_in:
        raise RuntimeError(
            "Please login to AgentForge first."
        )

    # --------------------------------------------------------
    # CODE CHECK
    # --------------------------------------------------------

    if not code:
        raise RuntimeError(
            "Google authorization code was not received."
        )

    # --------------------------------------------------------
    # STATE CHECK
    # --------------------------------------------------------

    payload = _verify_signed_state(
        state
    )

    oauth_user_id = str(
        payload.get("user_id", "")
    )

    oauth_user_email = str(
        payload.get("user_email", "")
    )

    current_user_id = str(
        st.user.get("sub", "")
    )

    current_user_email = str(
        st.user.get("email", "")
    )

    if not oauth_user_id:
        raise RuntimeError(
            "OAuth state does not contain user ID."
        )

    if oauth_user_id != current_user_id:
        raise RuntimeError(
            "OAuth user mismatch. "
            "Please connect Gmail again."
        )

    if (
        oauth_user_email.lower()
        != current_user_email.lower()
    ):
        raise RuntimeError(
            "OAuth email mismatch. "
            "Please use the same Google account."
        )

    # ========================================================
    # TOKEN EXCHANGE
    # ========================================================

    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()
    redirect_uri = _get_redirect_uri()

    token_data = _post_form(
        GOOGLE_TOKEN_ENDPOINT,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    access_token = token_data.get(
        "access_token"
    )

    refresh_token = token_data.get(
        "refresh_token"
    )

    expires_in = token_data.get(
        "expires_in"
    )

    if not access_token:
        raise RuntimeError(
            "Google did not return an access token."
        )

    # ========================================================
    # GET GOOGLE ACCOUNT
    # ========================================================

    userinfo = _get_google_userinfo(
        access_token
    )

    gmail_email = userinfo.get(
        "email"
    )

    if not gmail_email:
        raise RuntimeError(
            "Unable to determine Gmail account."
        )

    # ========================================================
    # VERIFY SAME GOOGLE ACCOUNT
    # ========================================================

    if (
        gmail_email.lower()
        != current_user_email.lower()
    ):
        raise RuntimeError(
            "Google account mismatch.\n\n"
            f"AgentForge account: "
            f"{current_user_email}\n\n"
            f"Gmail account: "
            f"{gmail_email}\n\n"
            "Please authorize the same Google account."
        )

    # ========================================================
    # SAVE TOKEN IN SESSION
    # ========================================================

    st.session_state[
        "gmail_access_token"
    ] = access_token

    if refresh_token:
        st.session_state[
            "gmail_refresh_token"
        ] = refresh_token

    st.session_state[
        "gmail_token_expires_in"
    ] = expires_in

    st.session_state[
        "gmail_email"
    ] = gmail_email

    st.session_state[
        "gmail_connected"
    ] = True

    # ========================================================
    # SAVE A SERIALIZABLE TOKEN
    # ========================================================

    st.session_state[
        "gmail_token"
    ] = {
        "token": access_token,
        "refresh_token": refresh_token,
        "token_uri": GOOGLE_TOKEN_ENDPOINT,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
    }

    return True


# ============================================================
# GMAIL CREDENTIALS
# ============================================================

def _build_credentials():
    """
    Build Google Credentials from current session.
    """

    token = st.session_state.get(
        "gmail_token"
    )

    if not token:
        return None

    credentials = Credentials(
        token=token.get("token"),
        refresh_token=token.get(
            "refresh_token"
        ),
        token_uri=token.get(
            "token_uri",
            GOOGLE_TOKEN_ENDPOINT,
        ),
        client_id=token.get(
            "client_id",
            _get_google_client_id(),
        ),
        client_secret=token.get(
            "client_secret",
            _get_google_client_secret(),
        ),
        scopes=token.get(
            "scopes",
            SCOPES,
        ),
    )

    # --------------------------------------------------------
    # Refresh expired access token
    # --------------------------------------------------------

    if credentials.expired:
        if not credentials.refresh_token:
            return None

        credentials.refresh(
            Request()
        )

        st.session_state[
            "gmail_access_token"
        ] = credentials.token

        st.session_state[
            "gmail_token"
        ]["token"] = credentials.token

    return credentials


# ============================================================
# GMAIL SERVICE
# ============================================================

def get_gmail_service():
    """
    Return Gmail API service.

    Returns None if Gmail isn't connected.
    """

    try:
        credentials = _build_credentials()

        if credentials is None:
            return None

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
# CONNECTION STATUS
# ============================================================

def is_gmail_connected():
    """
    Check whether Gmail is currently connected.
    """

    if not st.session_state.get(
        "gmail_connected",
        False,
    ):
        return False

    service = get_gmail_service()

    return service is not None


def get_connected_gmail_email():
    """
    Return connected Gmail address.
    """

    if not is_gmail_connected():
        return None

    return st.session_state.get(
        "gmail_email"
    )


# ============================================================
# SEND EMAIL
# ============================================================

def send_gmail_email(
    to: str,
    subject: str,
    body: str,
):
    """
    Send email through Gmail API.
    """

    service = get_gmail_service()

    if service is None:
        raise RuntimeError(
            "Gmail is not connected. "
            "Please connect Gmail first."
        )

    gmail_email = get_connected_gmail_email()

    if not gmail_email:
        raise RuntimeError(
            "Connected Gmail account is missing."
        )

    message = EmailMessage()

    message["From"] = gmail_email
    message["To"] = to
    message["Subject"] = subject

    message.set_content(body)

    encoded_message = (
        base64.urlsafe_b64encode(
            message.as_bytes()
        )
        .decode("utf-8")
    )

    result = (
        service.users()
        .messages()
        .send(
            userId="me",
            body={
                "raw": encoded_message
            },
        )
        .execute()
    )

    return result


# ============================================================
# DISCONNECT
# ============================================================

def disconnect_gmail():
    """
    Disconnect Gmail from current Streamlit session.
    """

    keys = [
        "gmail_access_token",
        "gmail_refresh_token",
        "gmail_token_expires_in",
        "gmail_token",
        "gmail_email",
        "gmail_connected",
    ]

    for key in keys:
        st.session_state.pop(
            key,
            None,
        )

    st.session_state[
        "gmail_connected"
    ] = False

    st.session_state[
        "gmail_email"
    ] = None

    return True

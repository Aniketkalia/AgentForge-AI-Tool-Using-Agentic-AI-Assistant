# ============================================================
# gmail_auth.py
# AgentForge AI - Gmail OAuth
# ============================================================

import base64
import hashlib
import secrets
import urllib.parse
from email.mime.text import MIMEText

import requests
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


# ============================================================
# GOOGLE OAUTH CONFIG
# ============================================================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_URL = "https://gmail.googleapis.com/gmail/v1"


# IMPORTANT:
# Keep these scopes consistent.
#
# openid/email -> lets us identify the Google account
# gmail.send   -> allows sending Gmail
#
# Do NOT change these between authorization and token exchange.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
]


# ============================================================
# READ STREAMLIT SECRETS
# ============================================================

def _get_secret(name: str):
    """
    Read a top-level Streamlit secret.
    """

    try:
        value = st.secrets.get(name)

        if value:
            return str(value).strip()

    except Exception:
        pass

    return None


def _get_client_id():
    client_id = _get_secret("GOOGLE_CLIENT_ID")

    if not client_id:
        # fallback to [gmail_oauth]
        try:
            client_id = st.secrets["gmail_oauth"]["client_id"]
        except Exception:
            client_id = None

    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is missing from Streamlit secrets."
        )

    return client_id


def _get_client_secret():
    client_secret = _get_secret("GOOGLE_CLIENT_SECRET")

    if not client_secret:
        try:
            client_secret = st.secrets["gmail_oauth"]["client_secret"]
        except Exception:
            client_secret = None

    if not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is missing from Streamlit secrets."
        )

    return client_secret


def _get_redirect_uri():
    """
    Use ONE redirect URI everywhere.

    This MUST exactly match the URI configured
    in Google Cloud Console.
    """

    redirect_uri = _get_secret("GOOGLE_REDIRECT_URI")

    if not redirect_uri:
        try:
            redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]
        except Exception:
            redirect_uri = None

    if not redirect_uri:
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is missing from Streamlit secrets."
        )

    return str(redirect_uri).strip()


# ============================================================
# PKCE HELPERS
# ============================================================

def _generate_code_verifier():
    """
    Generate OAuth PKCE code verifier.
    """

    return secrets.token_urlsafe(64)


def _generate_code_challenge(verifier):
    """
    Generate S256 PKCE challenge.
    """

    digest = hashlib.sha256(
        verifier.encode("utf-8")
    ).digest()

    return base64.urlsafe_b64encode(
        digest
    ).decode("utf-8").rstrip("=")


# ============================================================
# CONNECT GMAIL
# ============================================================

def connect_gmail():
    """
    Create Google Gmail OAuth authorization URL.

    The returned URL can be opened in a new browser tab.
    """

    client_id = _get_client_id()
    redirect_uri = _get_redirect_uri()

    # Create OAuth state
    state = secrets.token_urlsafe(32)

    # Create PKCE verifier
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(
        code_verifier
    )

    # Save OAuth information in Streamlit session
    st.session_state["gmail_oauth_state"] = state
    st.session_state["gmail_code_verifier"] = code_verifier

    # --------------------------------------------------------
    # IMPORTANT:
    # response_type MUST be "code"
    # --------------------------------------------------------

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = (
        GOOGLE_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return auth_url


# ============================================================
# CALLBACK
# ============================================================

def handle_gmail_callback():
    """
    Handle Google OAuth callback.

    Expected query parameters:

        ?code=...
        &state=...
    """

    query_params = st.query_params

    code = query_params.get("code")
    state = query_params.get("state")

    if not code:
        raise RuntimeError(
            "Google callback did not contain an authorization code."
        )

    if not state:
        raise RuntimeError(
            "Gmail OAuth state is missing or expired. "
            "Please click Connect Gmail again."
        )

    saved_state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not saved_state:
        raise RuntimeError(
            "Gmail OAuth state is missing or expired. "
            "Please click Connect Gmail again."
        )

    if state != saved_state:
        raise RuntimeError(
            "Invalid Gmail OAuth state. "
            "Please click Connect Gmail again."
        )

    # --------------------------------------------------------
    # PKCE verifier
    # --------------------------------------------------------

    code_verifier = st.session_state.get(
        "gmail_code_verifier"
    )

    if not code_verifier:
        raise RuntimeError(
            "Gmail OAuth code verifier is missing or expired. "
            "Please click Connect Gmail again."
        )

    client_id = _get_client_id()
    client_secret = _get_client_secret()
    redirect_uri = _get_redirect_uri()

    # --------------------------------------------------------
    # Exchange authorization code for token
    # --------------------------------------------------------

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    try:

        response = requests.post(
            GOOGLE_TOKEN_URL,
            data=token_data,
            timeout=30,
        )

    except Exception as e:

        raise RuntimeError(
            f"Google token request failed: {e}"
        )

    if response.status_code != 200:

        try:
            error_json = response.json()
        except Exception:
            error_json = response.text

        raise RuntimeError(
            f"Google token exchange failed: {error_json}"
        )

    token = response.json()

    access_token = token.get("access_token")

    if not access_token:
        raise RuntimeError(
            "Google did not return an access token."
        )

    refresh_token = token.get("refresh_token")

    expires_in = token.get("expires_in")

    # --------------------------------------------------------
    # Save token in session
    # --------------------------------------------------------

    st.session_state["gmail_access_token"] = (
        access_token
    )

    if refresh_token:
        st.session_state["gmail_refresh_token"] = (
            refresh_token
        )

    if expires_in:
        st.session_state["gmail_expires_in"] = (
            expires_in
        )

    # --------------------------------------------------------
    # Get Google account email using userinfo endpoint
    #
    # We do NOT call Gmail /users/me/profile here.
    # That endpoint caused your previous 403 insufficient
    # authentication scopes error.
    # --------------------------------------------------------

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:

        userinfo_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers=headers,
            timeout=30,
        )

    except Exception as e:

        raise RuntimeError(
            f"Unable to get Google account information: {e}"
        )

    if userinfo_response.status_code != 200:

        try:
            error_json = userinfo_response.json()
        except Exception:
            error_json = userinfo_response.text

        raise RuntimeError(
            f"Unable to identify Google account: {error_json}"
        )

    userinfo = userinfo_response.json()

    email = userinfo.get("email")

    if not email:
        raise RuntimeError(
            "Google did not return the Gmail account email."
        )

    # --------------------------------------------------------
    # Save connected Gmail account
    # --------------------------------------------------------

    st.session_state["gmail_email"] = email
    st.session_state["gmail_connected"] = True

    # --------------------------------------------------------
    # Clear temporary OAuth data
    # --------------------------------------------------------

    st.session_state.pop(
        "gmail_oauth_state",
        None,
    )

    st.session_state.pop(
        "gmail_code_verifier",
        None,
    )

    return True


# ============================================================
# CHECK CONNECTION
# ============================================================

def is_gmail_connected():
    """
    Return True if Gmail OAuth is currently connected.
    """

    access_token = st.session_state.get(
        "gmail_access_token"
    )

    email = st.session_state.get(
        "gmail_email"
    )

    return bool(
        access_token
        and email
    )


# ============================================================
# GET CONNECTED EMAIL
# ============================================================

def get_connected_gmail_email():
    """
    Return connected Gmail email.
    """

    if not is_gmail_connected():
        return None

    return st.session_state.get(
        "gmail_email"
    )


# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service():
    """
    Return authenticated Gmail API service.
    """

    access_token = st.session_state.get(
        "gmail_access_token"
    )

    if not access_token:
        raise RuntimeError(
            "Gmail is not connected."
        )

    refresh_token = st.session_state.get(
        "gmail_refresh_token"
    )

    credentials_kwargs = {
        "token": access_token,
        "scopes": [
            "https://www.googleapis.com/auth/gmail.send"
        ],
    }

    if refresh_token:
        credentials_kwargs["refresh_token"] = (
            refresh_token
        )

    credentials = Credentials(
        **credentials_kwargs
    )

    try:

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return service

    except Exception as e:

        raise RuntimeError(
            f"Unable to create Gmail service: {e}"
        )


# ============================================================
# SEND EMAIL
# ============================================================

def send_gmail(
    to_email: str,
    subject: str,
    body: str,
):
    """
    Send an email through Gmail API.
    """

    if not is_gmail_connected():
        raise RuntimeError(
            "Gmail is not connected."
        )

    if not to_email:
        raise ValueError(
            "Recipient email is required."
        )

    if not subject:
        raise ValueError(
            "Email subject is required."
        )

    if not body:
        raise ValueError(
            "Email body is required."
        )

    service = get_gmail_service()

    message = MIMEText(
        body,
        "plain",
        "utf-8",
    )

    message["To"] = to_email

    message["Subject"] = subject

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    gmail_message = {
        "raw": raw_message
    }

    try:

        result = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=gmail_message,
            )
            .execute()
        )

        return result

    except Exception as e:

        raise RuntimeError(
            f"Gmail send failed: {e}"
        )


# ============================================================
# DISCONNECT GMAIL
# ============================================================

def disconnect_gmail(user_id=None):
    """
    Disconnect Gmail from the current Streamlit session.
    """

    # Try to revoke Google token
    access_token = st.session_state.get(
        "gmail_access_token"
    )

    if access_token:

        try:

            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={
                    "token": access_token
                },
                timeout=10,
            )

        except Exception:
            pass

    # Remove Gmail session data

    keys_to_remove = [
        "gmail_access_token",
        "gmail_refresh_token",
        "gmail_expires_in",
        "gmail_email",
        "gmail_connected",
        "gmail_oauth_state",
        "gmail_code_verifier",
        "gmail_auth_url",
    ]

    for key in keys_to_remove:

        st.session_state.pop(
            key,
            None,
        )

    return True

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

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
]

# ============================================================
# READ STREAMLIT SECRETS
# ============================================================

def _get_secret(name: str):
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
        try:
            client_id = st.secrets["gmail_oauth"]["client_id"]
        except Exception:
            client_id = None
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is missing from Streamlit secrets.")
    return client_id

def _get_client_secret():
    client_secret = _get_secret("GOOGLE_CLIENT_SECRET")
    if not client_secret:
        try:
            client_secret = st.secrets["gmail_oauth"]["client_secret"]
        except Exception:
            client_secret = None
    if not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_SECRET is missing from Streamlit secrets.")
    return client_secret

def _get_redirect_uri():
    redirect_uri = _get_secret("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        try:
            redirect_uri = st.secrets["gmail_oauth"]["redirect_uri"]
        except Exception:
            redirect_uri = None
    if not redirect_uri:
        raise RuntimeError("GOOGLE_REDIRECT_URI is missing from Streamlit secrets.")
    return str(redirect_uri).strip()

# ============================================================
# PKCE HELPERS & GLOBAL CACHE
# ============================================================

def _generate_code_verifier():
    return secrets.token_urlsafe(64)

def _generate_code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

@st.cache_resource
def get_oauth_store():
    """Keeps OAuth verification data alive when Streamlit redirects tabs."""
    return {}

# ============================================================
# CONNECT GMAIL
# ============================================================

def connect_gmail(user_email: str):
    client_id = _get_client_id()
    redirect_uri = _get_redirect_uri()

    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    # Save to global cache instead of session_state so it survives the redirect
    store = get_oauth_store()
    store[user_email] = {
        "state": state,
        "code_verifier": code_verifier
    }

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

    auth_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return auth_url

# ============================================================
# CALLBACK
# ============================================================

def handle_gmail_callback(user_email: str):
    query_params = st.query_params
    code = query_params.get("code")
    state = query_params.get("state")

    if not code:
        raise RuntimeError("Google callback did not contain an authorization code.")

    # Retrieve OAuth state from global cache
    store = get_oauth_store()
    auth_data = store.get(user_email, {})
    saved_state = auth_data.get("state")
    code_verifier = auth_data.get("code_verifier")

    if not state or not saved_state or state != saved_state:
        raise RuntimeError("Invalid or expired Gmail OAuth state. Please click Connect Gmail again.")

    if not code_verifier:
        raise RuntimeError("Gmail OAuth code verifier is missing or expired.")

    client_id = _get_client_id()
    client_secret = _get_client_secret()
    redirect_uri = _get_redirect_uri()

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=30)
    except Exception as e:
        raise RuntimeError(f"Google token request failed: {e}")

    if response.status_code != 200:
        raise RuntimeError(f"Google token exchange failed: {response.text}")

    token = response.json()
    access_token = token.get("access_token")
    if not access_token:
        raise RuntimeError("Google did not return an access token.")

    refresh_token = token.get("refresh_token")
    expires_in = token.get("expires_in")

    st.session_state["gmail_access_token"] = access_token
    if refresh_token:
        st.session_state["gmail_refresh_token"] = refresh_token
    if expires_in:
        st.session_state["gmail_expires_in"] = expires_in

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        userinfo_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers=headers,
            timeout=30,
        )
    except Exception as e:
        raise RuntimeError(f"Unable to get Google account information: {e}")

    if userinfo_response.status_code != 200:
        raise RuntimeError(f"Unable to identify Google account: {userinfo_response.text}")

    userinfo = userinfo_response.json()
    email = userinfo.get("email")

    if not email:
        raise RuntimeError("Google did not return the Gmail account email.")

    st.session_state["gmail_email"] = email
    st.session_state["gmail_connected"] = True

    # Clean up the cache
    store.pop(user_email, None)

    return True


def is_gmail_connected():
    access_token = st.session_state.get("gmail_access_token")
    email = st.session_state.get("gmail_email")
    return bool(access_token and email)

def get_connected_gmail_email():
    if not is_gmail_connected():
        return None
    return st.session_state.get("gmail_email")

# ============================================================
# GET GMAIL SERVICE
# ============================================================

# ============================================================
# GET GMAIL SERVICE
# ============================================================

def get_gmail_service(access_token=None, refresh_token=None):
    """
    Return authenticated Gmail API service with refresh token setup.
    """
    # Use provided tokens if available, otherwise fallback to Streamlit memory
    if access_token is None:
        access_token = st.session_state.get("gmail_access_token")
        
    if not access_token:
        raise RuntimeError("Gmail is not connected.")

    if refresh_token is None:
        refresh_token = st.session_state.get("gmail_refresh_token")

    credentials_kwargs = {
        "token": access_token,
        "token_uri": GOOGLE_TOKEN_URL,
        "client_id": _get_client_id(),
        "client_secret": _get_client_secret(),
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
    }

    if refresh_token:
        credentials_kwargs["refresh_token"] = refresh_token

    credentials = Credentials(**credentials_kwargs)

    try:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return service
    except Exception as e:
        raise RuntimeError(f"Unable to create Gmail service: {e}")

def send_gmail(to_email: str, subject: str, body: str):
    if not is_gmail_connected():
        raise RuntimeError("Gmail is not connected.")
    
    service = get_gmail_service()
    message = MIMEText(body, "plain", "utf-8")
    message["To"] = to_email
    message["Subject"] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    gmail_message = {"raw": raw_message}

    try:
        result = service.users().messages().send(userId="me", body=gmail_message).execute()
        return result
    except Exception as e:
        raise RuntimeError(f"Gmail send failed: {e}")

def disconnect_gmail(user_id=None):
    access_token = st.session_state.get("gmail_access_token")
    if access_token:
        try:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
                timeout=10,
            )
        except Exception:
            pass

    keys_to_remove = [
        "gmail_access_token",
        "gmail_refresh_token",
        "gmail_expires_in",
        "gmail_email",
        "gmail_connected",
    ]

    for key in keys_to_remove:
        st.session_state.pop(key, None)

    return True

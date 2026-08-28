# ============================================================
# streamlit_frontend.py
# AgentForge AI
# ============================================================

import html
import uuid

import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
    get_connected_gmail_email,
    is_gmail_connected,
    disconnect_gmail,
)

from backend import chatbot


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AgentForge AI",
    page_icon="🤖",
    layout="wide",
)


# ============================================================
# SESSION STATE
# ============================================================

if "gmail_auth_url" not in st.session_state:
    st.session_state.gmail_auth_url = None

if "gmail_connected" not in st.session_state:
    st.session_state.gmail_connected = False

if "gmail_email" not in st.session_state:
    st.session_state.gmail_email = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(
        uuid.uuid4()
    )


# ============================================================
# GMAIL CALLBACK
# ============================================================
#
# Google redirects to:
#
# https://YOUR-APP.streamlit.app/
#       ?code=...
#       &state=...
#
# Process callback BEFORE normal Gmail UI.
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Get connected account
            email = get_connected_gmail_email()

            st.session_state.gmail_email = email
            st.session_state.gmail_connected = bool(
                email
            )

            # Remove OAuth parameters
            st.query_params.clear()

            # Refresh application
            st.rerun()

    except Exception as e:

        st.error(
            f"❌ Gmail callback error: {e}"
        )

        try:
            st.query_params.clear()
        except Exception:
            pass

        st.stop()


# ============================================================
# AGENTFORGE GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title("🤖 AgentForge AI")

    st.subheader(
        "Tool-Using Agentic AI Assistant"
    )

    st.write(
        "Login with Google to continue."
    )

    if st.button(
        "🔐 Login with Google",
        use_container_width=True,
        type="primary",
    ):
        st.login()

    st.stop()


# ============================================================
# CURRENT USER
# ============================================================

user_email = st.user.email
user_id = st.user.get("sub")

if not user_id:

    st.error(
        "❌ Unable to identify logged-in Google user."
    )

    st.stop()


# ============================================================
# LANGGRAPH THREAD
# ============================================================

thread_id = (
    f"agentforge-user-{user_id}"
)


config = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ============================================================
# LOAD GMAIL STATUS
# ============================================================

gmail_email = None
gmail_connected = False
gmail_error = None

try:

    gmail_email = (
        get_connected_gmail_email()
    )

    gmail_connected = (
        gmail_email is not None
        and gmail_email != ""
    )

except Exception as e:

    gmail_error = str(e)


st.session_state.gmail_connected = (
    gmail_connected
)

st.session_state.gmail_email = (
    gmail_email
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 AgentForge")

    st.caption(
        "LangGraph • Groq • Gmail • Web Search • Tools"
    )

    st.divider()

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    st.success(
        f"👤 {user_email}"
    )

    st.divider()

    # --------------------------------------------------------
    # GMAIL
    # --------------------------------------------------------

    st.subheader("📧 Gmail")

    # ========================================================
    # CONNECTED
    # ========================================================

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        st.markdown(
            f"**Connected account:**  \n"
            f"{gmail_email}"
        )

        st.caption(
            "AgentForge can send emails using this Gmail account."
        )

        st.divider()

        # Refresh
        if st.button(
            "🔄 Refresh Gmail",
            use_container_width=True,
        ):
            st.rerun()

        # Disconnect
        if st.button(
            "🔌 Disconnect Gmail",
            use_container_width=True,
        ):

            try:

                disconnect_gmail(
                    user_id
                )

                st.session_state.gmail_connected = (
                    False
                )

                st.session_state.gmail_email = (
                    None
                )

                st.session_state.gmail_auth_url = (
                    None
                )

                st.success(
                    "Gmail disconnected."
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"Disconnect failed: {e}"
                )

    # ========================================================
    # NOT CONNECTED
    # ========================================================

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        st.caption(
            "Connect your Gmail to allow AgentForge "
            "to send emails."
        )

        # ----------------------------------------------------
        # CREATE AUTH URL
        # ----------------------------------------------------

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True,
            type="primary",
        ):

            try:

                auth_url = connect_gmail()

                if auth_url:

                    st.session_state.gmail_auth_url = (
                        auth_url
                    )

                    st.rerun()

                else:

                    st.error(
                        "Unable to create Gmail authorization URL."
                    )

            except Exception as e:

                st.error(
                    f"❌ Gmail authorization error: {e}"
                )

        # ----------------------------------------------------
        # NEW TAB AUTHORIZATION
        # ----------------------------------------------------

        auth_url = (
            st.session_state.gmail_auth_url
        )

        if auth_url:

            safe_url = html.escape(
                auth_url,
                quote=True
            )

            st.markdown(
                f"""
                <a
                    href="{safe_url}"
                    target="_blank"
                    rel="noopener noreferrer"
                    style="
                        display:block;
                        width:100%;
                        padding:0.75rem 1rem;
                        background:#FF4B4B;
                        color:white;
                        text-align:center;
                        text-decoration:none;
                        border-radius:0.5rem;
                        font-weight:600;
                        margin-top:0.75rem;
                        box-sizing:border-box;
                    "
                >
                    🔐 Continue with Google
                </a>
                """,
                unsafe_allow_html=True,
            )

            st.info(
                """
                **Gmail connection**

                1. Click **Continue with Google**
                2. Google opens in a **new tab**
                3. Select your Gmail account
                4. Click **Allow**
                5. Google redirects back to AgentForge
                6. Return to the AgentForge tab
                7. Click **🔄 Refresh Gmail**
                """
            )

            if st.button(
                "❌ Cancel",
                use_container_width=True,
            ):

                st.session_state.gmail_auth_url = (
                    None
                )

                st.rerun()

    # ========================================================
    # ERROR
    # ========================================================

    if gmail_error:

        st.error(
            f"Gmail status error: {gmail_error}"
        )

    # ========================================================
    # NEW CHAT
    # ========================================================

    st.divider()

    if st.button(
        "🆕 New Chat",
        use_container_width=True,
    ):

        st.session_state.messages = []

        st.session_state.thread_id = str(
            uuid.uuid4()
        )

        st.rerun()

    # ========================================================
    # DEBUG
    # ========================================================

    with st.expander("🔧 Debug"):

        st.write(
            "AgentForge User ID:",
            user_id
        )

        st.write(
            "AgentForge Email:",
            user_email
        )

        st.write(
            "Gmail Connected:",
            gmail_connected
        )

        st.write(
            "Gmail Account:",
            gmail_email
        )

        st.write(
            "LangGraph Thread:",
            thread_id
        )

    # ========================================================
    # LOGOUT
    # ========================================================

    st.divider()

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        st.session_state.messages = []

        st.session_state.gmail_auth_url = (
            None
        )

        st.logout()


# ============================================================
# MAIN PAGE
# ============================================================

st.title(
    "🤖 AgentForge AI"
)

st.caption(
    f"Logged in as: {user_email}"
)


# ============================================================
# GMAIL STATUS
# ============================================================

if gmail_connected:

    st.success(
        f"📧 Gmail connected: {gmail_email}"
    )

else:

    st.info(
        "📧 Gmail is not connected. "
        "Connect Gmail from the sidebar to send emails."
    )


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    if isinstance(
        message,
        HumanMessage
    ):

        with st.chat_message("user"):

            st.markdown(
                message.content
            )

    elif isinstance(
        message,
        AIMessage
    ):

        content = message.content

        if (
            isinstance(content, str)
            and content.strip()
        ):

            with st.chat_message(
                "assistant"
            ):

                st.markdown(
                    content
                )


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state.messages:

    st.info(
        "👋 Welcome to AgentForge AI!"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.markdown(
            """
            **🧮 Calculator**

            `Calculate 125 * 48`
            """
        )

    with col2:

        st.markdown(
            """
            **📧 Gmail**

            `Send an email to someone@example.com`
            """
        )

    with col3:

        st.markdown(
            """
            **🌐 Web Search**

            `Search the latest AI news`
            """
        )


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask me anything..."
)


# ============================================================
# PROCESS MESSAGE
# ============================================================

if prompt:

    human_message = HumanMessage(
        content=prompt
    )

    st.session_state.messages.append(
        human_message
    )

    with st.chat_message("user"):

        st.markdown(
            prompt
        )

    # --------------------------------------------------------
    # AGENT
    # --------------------------------------------------------

    try:

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "🤖 AgentForge is thinking..."
            ):

                response = chatbot.invoke(
                    {
                        "messages": [
                            human_message
                        ]
                    },
                    config=config
                )

            # ------------------------------------------------
            # FIND ANSWER
            # ------------------------------------------------

            answer = ""

            if isinstance(
                response,
                dict
            ):

                response_messages = (
                    response.get(
                        "messages",
                        []
                    )
                )

                for msg in reversed(
                    response_messages
                ):

                    content = getattr(
                        msg,
                        "content",
                        None
                    )

                    if (
                        isinstance(
                            content,
                            str
                        )
                        and content.strip()
                    ):

                        answer = content

                        break

            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            if not answer:

                answer = str(
                    response
                )

            st.markdown(
                answer
            )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        st.session_state.messages.append(
            AIMessage(
                content=answer
            )
        )

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

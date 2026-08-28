# ============================================================
# streamlit_frontend.py
# AgentForge AI
#
# Google Login
# Gmail OAuth
# LangGraph
# Groq
# Web Search
# Tools
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
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

def initialize_session_state():

    if "gmail_connected" not in st.session_state:
        st.session_state[
            "gmail_connected"
        ] = False

    if "gmail_email" not in st.session_state:
        st.session_state[
            "gmail_email"
        ] = None

    if "gmail_auth_url" not in st.session_state:
        st.session_state[
            "gmail_auth_url"
        ] = None

    if "message_history" not in st.session_state:
        st.session_state[
            "message_history"
        ] = []

    if "thread_id" not in st.session_state:
        st.session_state[
            "thread_id"
        ] = str(uuid.uuid4())


initialize_session_state()


# ============================================================
# GMAIL OAUTH CALLBACK
# ============================================================

# Google redirects to:
#
# https://your-app.streamlit.app/
#       ?code=XXXX
#       &state=XXXX
#
# Process Gmail callback BEFORE normal UI.

if (
    "code" in st.query_params
    or
    "error" in st.query_params
):

    try:

        success = handle_gmail_callback()

        if success:

            # Get connected Gmail account.
            try:
                email = (
                    get_connected_gmail_email()
                )

                st.session_state[
                    "gmail_email"
                ] = email

                st.session_state[
                    "gmail_connected"
                ] = bool(email)

            except Exception:
                pass

            # Remove OAuth parameters.
            st.query_params.clear()

            # Reload application.
            st.rerun()

        else:
            st.query_params.clear()

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
        "❌ Unable to identify the logged-in "
        "Google user."
    )

    st.stop()


# ============================================================
# LANGGRAPH THREAD
# ============================================================

if "thread_id" not in st.session_state:

    st.session_state[
        "thread_id"
    ] = str(uuid.uuid4())


thread_id = st.session_state[
    "thread_id"
]


# IMPORTANT:
# LangGraph checkpoint requires thread_id.

config = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

try:

    gmail_connected = (
        is_gmail_connected()
    )

    if gmail_connected:

        gmail_email = (
            get_connected_gmail_email()
        )

    else:

        gmail_email = None

except Exception:

    gmail_connected = False
    gmail_email = None


# Synchronize UI state.

st.session_state[
    "gmail_connected"
] = gmail_connected

st.session_state[
    "gmail_email"
] = gmail_email


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 AgentForge")

    st.caption(
        "LangGraph • Groq • Gmail • "
        "Web Search • Tools"
    )

    st.divider()

    # --------------------------------------------------------
    # CURRENT USER
    # --------------------------------------------------------

    st.success(
        f"👤 {user_email}"
    )

    st.divider()

    # --------------------------------------------------------
    # GMAIL
    # --------------------------------------------------------

    st.subheader("📧 Gmail")

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        st.markdown(
            f"**Connected account:**\n\n"
            f"{gmail_email}"
        )

        st.caption(
            "AgentForge can send emails "
            "using this Gmail account."
        )

        # ----------------------------------------------------
        # DISCONNECT
        # ----------------------------------------------------

        if st.button(
            "🔌 Disconnect Gmail",
            use_container_width=True,
        ):

            disconnect_gmail()

            st.session_state[
                "gmail_auth_url"
            ] = None

            st.rerun()

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        st.caption(
            "Connect Gmail to allow "
            "AgentForge to send emails."
        )

        # ----------------------------------------------------
        # CREATE OAUTH URL
        # ----------------------------------------------------

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True,
            type="primary",
        ):

            try:

                auth_url = connect_gmail()

                if not auth_url:

                    st.error(
                        "❌ Unable to create "
                        "Gmail authorization URL."
                    )

                else:

                    st.session_state[
                        "gmail_auth_url"
                    ] = auth_url

                    st.rerun()

            except Exception as e:

                st.error(
                    f"❌ Gmail authorization error: {e}"
                )

        # ----------------------------------------------------
        # NEW TAB LINK
        # ----------------------------------------------------

        auth_url = st.session_state.get(
            "gmail_auth_url"
        )

        if auth_url:

            safe_url = html.escape(
                auth_url,
                quote=True,
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
                        padding:12px;
                        margin-top:10px;
                        background:#FF4B4B;
                        color:white;
                        text-align:center;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:600;
                    "
                >
                    🔗 Open Google Gmail
                    Authorization
                </a>
                """,
                unsafe_allow_html=True,
            )

            st.info(
                """
                **Gmail connection**

                1. Click **Open Google Gmail Authorization**.
                2. Google opens in a new tab.
                3. Select your Google account.
                4. Click **Allow**.
                5. Google redirects back to AgentForge.
                6. Gmail will show as connected.

                You can keep this AgentForge tab open.
                """
            )

    st.divider()

    # --------------------------------------------------------
    # NEW CHAT
    # --------------------------------------------------------

    if st.button(
        "🆕 New Chat",
        use_container_width=True,
    ):

        st.session_state[
            "thread_id"
        ] = str(uuid.uuid4())

        st.session_state[
            "message_history"
        ] = []

        st.rerun()

    st.divider()

    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        # Gmail credentials are cleared from
        # the current session.

        disconnect_gmail()

        st.logout()


# ============================================================
# MAIN HEADER
# ============================================================

st.title("🤖 AgentForge AI")

st.markdown(
    """
### Tool-Using Agentic AI Assistant

Ask questions, perform calculations, search the web,
check stock prices, or send emails using natural language.
"""
)


# ============================================================
# GMAIL STATUS
# ============================================================

if gmail_connected:

    st.success(
        f"📧 Gmail connected: **{gmail_email}**"
    )

else:

    st.info(
        "📧 Gmail is not connected. "
        "Connect Gmail from the sidebar to send emails."
    )


# ============================================================
# CONVERSATION DETAILS
# ============================================================

with st.expander(
    "💬 Conversation Details",
    expanded=False,
):

    st.write(
        f"**Thread ID:** "
        f"`{thread_id}`"
    )

    st.write(
        f"**Messages:** "
        f"{len(st.session_state['message_history'])}"
    )


# ============================================================
# DISPLAY CHAT HISTORY
# ============================================================

for message in st.session_state[
    "message_history"
]:

    role = message.get(
        "role",
        "assistant",
    )

    content = message.get(
        "content",
        "",
    )

    if not content:
        continue

    with st.chat_message(role):

        st.markdown(content)


# ============================================================
# CHAT INPUT
# ============================================================

user_input = st.chat_input(
    "Ask me anything..."
)


# ============================================================
# CHAT PROCESSING
# ============================================================

if user_input:

    # --------------------------------------------------------
    # DISPLAY USER MESSAGE
    # --------------------------------------------------------

    st.session_state[
        "message_history"
    ].append(
        {
            "role": "user",
            "content": user_input,
        }
    )

    with st.chat_message("user"):

        st.markdown(
            user_input
        )

    # --------------------------------------------------------
    # RUN AGENT
    # --------------------------------------------------------

    with st.chat_message(
        "assistant"
    ):

        try:

            response = chatbot.invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=user_input
                        )
                    ]
                },
                config=config,
            )

            # ------------------------------------------------
            # GET FINAL MESSAGE
            # ------------------------------------------------

            ai_content = None

            if isinstance(
                response,
                dict,
            ):

                messages = response.get(
                    "messages",
                    [],
                )

                if messages:

                    for message in reversed(
                        messages
                    ):

                        if isinstance(
                            message,
                            AIMessage,
                        ):

                            content = (
                                message.content
                            )

                            if isinstance(
                                content,
                                str,
                            ) and content.strip():

                                ai_content = content

                                break

            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            if not ai_content:

                ai_content = (
                    "I couldn't generate a response."
                )

            # ------------------------------------------------
            # DISPLAY
            # ------------------------------------------------

            st.markdown(
                ai_content
            )

            # ------------------------------------------------
            # SAVE
            # ------------------------------------------------

            st.session_state[
                "message_history"
            ].append(
                {
                    "role": "assistant",
                    "content": ai_content,
                }
            )

        except Exception as e:

            error_message = (
                f"❌ Agent error: {e}"
            )

            st.error(
                error_message
            )

            st.session_state[
                "message_history"
            ].append(
                {
                    "role": "assistant",
                    "content": error_message,
                }
            )

# ============================================================
# streamlit_frontend.py
# AgentForge AI
# ============================================================

import uuid

import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
    get_gmail_service,
    is_gmail_connected,
    get_connected_gmail_email,
    disconnect_gmail,
)


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
# GMAIL OAUTH CALLBACK
# ============================================================
#
# Gmail redirects to:
#
# https://YOUR-APP.streamlit.app/?code=...&state=...
#
# This is NOT /oauth2callback.
#
# /oauth2callback belongs to Streamlit st.login().
# ============================================================

if "code" in st.query_params or "error" in st.query_params:

    try:

        gmail_success = handle_gmail_callback()

        if gmail_success:

            st.session_state[
                "gmail_connected"
            ] = True

            st.rerun()

        else:

            st.stop()

    except Exception as e:

        st.error(
            f"❌ Gmail callback error: {e}"
        )

        st.query_params.clear()

        st.stop()


# ============================================================
# AGENTFORGE GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title(
        "🤖 AgentForge"
    )

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
        "❌ Unable to identify the logged-in Google user."
    )

    st.stop()


# ============================================================
# LOAD GMAIL STATUS
# ============================================================

gmail_email = get_connected_gmail_email()

gmail_connected = (
    gmail_email is not None
    and gmail_email != ""
)


# ============================================================
# SESSION CACHE
# ============================================================

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

    st.title(
        "🤖 AgentForge"
    )

    st.success(
        f"👤 {user_email}"
    )

    st.divider()

    # ========================================================
    # GMAIL
    # ========================================================

    st.subheader(
        "📧 Gmail"
    )

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        st.caption(
            gmail_email
        )

        st.caption(
            "Agent can send emails using this Gmail account."
        )

        st.divider()

        if st.button(
            "🔌 Disconnect Gmail",
            use_container_width=True,
        ):

            disconnect_gmail()

            st.success(
                "Gmail disconnected."
            )

            st.rerun()

    else:

        st.info(
            "Gmail is not connected."
        )

        st.caption(
            "Connect Gmail to allow AgentForge to send emails."
        )

        # ----------------------------------------------------
        # Generate URL only when button is clicked
        # ----------------------------------------------------

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True,
            type="primary",
        ):

            auth_url = connect_gmail()

            if auth_url:

                # ------------------------------------------------
                # SAME TAB
                #
                # No popup.
                # No new Chrome tab.
                # No iframe.
                # ------------------------------------------------

                st.markdown(
                    f"""
                    <meta
                        http-equiv="refresh"
                        content="0; url={auth_url}"
                    >
                    """,
                    unsafe_allow_html=True,
                )

                st.info(
                    "Redirecting to Google Gmail authorization..."
                )

                st.stop()

            else:

                st.error(
                    "Unable to create Gmail authorization URL."
                )

    st.divider()

    # ========================================================
    # DEBUG
    # ========================================================

    with st.expander(
        "🔧 Debug"
    ):

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
            "Gmail Email:",
            gmail_email
        )

    st.divider()

    # ========================================================
    # LOGOUT
    # ========================================================

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        # Only clear temporary UI state.
        # Gmail token remains stored.
        st.session_state.pop(
            "gmail_connected",
            None
        )

        st.session_state.pop(
            "gmail_email",
            None
        )

        st.logout()


# ============================================================
# BACKEND
# ============================================================

from backend import (
    chatbot,
    retrieve,
)


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

    st.warning(
        "📧 Gmail is not connected. "
        "Connect Gmail from the sidebar."
    )


# ============================================================
# CHAT STATE
# ============================================================

if "messages" not in st.session_state:

    st.session_state.messages = []


# ============================================================
# DISPLAY CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    if isinstance(
        message,
        HumanMessage
    ):

        with st.chat_message(
            "user"
        ):

            st.markdown(
                message.content
            )

    elif isinstance(
        message,
        AIMessage
    ):

        with st.chat_message(
            "assistant"
        ):

            st.markdown(
                message.content
            )


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask me anything..."
)


# ============================================================
# PROCESS USER MESSAGE
# ============================================================

if prompt:

    # ========================================================
    # USER MESSAGE
    # ========================================================

    human_message = HumanMessage(
        content=prompt
    )

    st.session_state.messages.append(
        human_message
    )

    with st.chat_message(
        "user"
    ):

        st.markdown(
            prompt
        )

    # ========================================================
    # RUN AGENT
    # ========================================================

    try:

        with st.chat_message(
            "assistant"
        ):

            response = chatbot.invoke(
                {
                    "messages": [
                        human_message
                    ]
                }
            )

            # ------------------------------------------------
            # Extract final response
            # ------------------------------------------------

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

                if response_messages:

                    final_message = (
                        response_messages[-1]
                    )

                    if hasattr(
                        final_message,
                        "content"
                    ):

                        answer = (
                            final_message.content
                        )

                    else:

                        answer = str(
                            final_message
                        )

                else:

                    answer = str(
                        response
                    )

            else:

                answer = str(
                    response
                )

            # ------------------------------------------------
            # Display answer
            # ------------------------------------------------

            st.markdown(
                answer
            )

        # ----------------------------------------------------
        # Save assistant message
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

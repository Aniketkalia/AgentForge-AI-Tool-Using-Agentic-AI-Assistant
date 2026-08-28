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
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AgentForge AI",
    page_icon="🤖",
    layout="wide",
)


# ============================================================
# HANDLE GMAIL CALLBACK FIRST
# ============================================================

if "code" in st.query_params:

    success = handle_gmail_callback()

    if success:

        # Force a clean rerun after saving token
        st.rerun()

    else:

        # If callback failed, stop here
        st.stop()


# ============================================================
# AGENTFORGE GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title("🤖 AgentForge")

    st.subheader(
        "Tool-Using Agentic AI Assistant"
    )

    st.write(
        "Login with Google to continue."
    )

    if st.button(
        "🔐 Login with Google",
        use_container_width=True,
    ):

        st.login()

    st.stop()


# ============================================================
# CURRENT USER
# ============================================================

user_email = st.user.email

user_id = st.user.get("sub")


# ============================================================
# LOAD GMAIL FROM SQLITE
# ============================================================

try:

    gmail_connected = is_gmail_connected()

    gmail_email = (
        get_connected_gmail_email()
    )

except Exception as e:

    gmail_connected = False

    gmail_email = None

    st.sidebar.error(
        "Unable to load Gmail connection."
    )

    with st.sidebar.expander(
        "Database error"
    ):

        st.code(str(e))


# ============================================================
# SYNCHRONIZE SESSION CACHE
# ============================================================

st.session_state["gmail_connected"] = (
    gmail_connected
)

st.session_state["gmail_email"] = (
    gmail_email
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "🤖 AgentForge"
)

st.sidebar.success(
    f"👤 {user_email}"
)


# ============================================================
# GMAIL SECTION
# ============================================================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "📧 Gmail"
)


if gmail_connected:

    st.sidebar.success(
        "✅ Gmail Connected"
    )

    if gmail_email:

        st.sidebar.caption(
            gmail_email
        )

    # --------------------------------------------------------
    # DISCONNECT
    # --------------------------------------------------------

    if st.sidebar.button(
        "🔌 Disconnect Gmail",
        use_container_width=True,
    ):

        from gmail_auth import disconnect_gmail

        disconnect_gmail(
            user_id
        )

        st.session_state.pop(
            "gmail_connected",
            None
        )

        st.session_state.pop(
            "gmail_email",
            None
        )

        st.rerun()


else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    if st.sidebar.button(
        "🔗 Connect My Gmail",
        use_container_width=True,
    ):

        try:

            auth_url = connect_gmail()

            if auth_url:

                # ------------------------------------------------
                # Use browser navigation.
                #
                # This avoids iframe/new-tab problems.
                # ------------------------------------------------

                st.markdown(
                    f"""
                    <script>
                        window.top.location.href =
                        {auth_url!r};
                    </script>
                    """,
                    unsafe_allow_html=True,
                )

                st.stop()

            else:

                st.error(
                    "Unable to start Gmail authorization."
                )

        except Exception as e:

            st.error(
                f"Gmail authorization error: {e}"
            )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    st.session_state.clear()

    st.logout()


# ============================================================
# DEBUG
# ============================================================

with st.sidebar.expander(
    "🔧 Debug"
):

    st.write(
        "AgentForge User ID:",
        user_id,
    )

    st.write(
        "AgentForge Email:",
        user_email,
    )

    st.write(
        "Gmail Connected:",
        gmail_connected,
    )

    st.write(
        "Gmail Email:",
        gmail_email,
    )


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
# CHAT HISTORY
# ============================================================

if "messages" not in st.session_state:

    st.session_state.messages = []


for message in st.session_state.messages:

    if isinstance(
        message,
        HumanMessage,
    ):

        with st.chat_message("user"):

            st.markdown(
                message.content
            )

    elif isinstance(
        message,
        AIMessage,
    ):

        with st.chat_message("assistant"):

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
            # Extract response
            # ------------------------------------------------

            if isinstance(
                response,
                dict,
            ):

                response_messages = (
                    response.get(
                        "messages",
                        [],
                    )
                )

                if response_messages:

                    final_message = (
                        response_messages[-1]
                    )

                    if hasattr(
                        final_message,
                        "content",
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

            st.markdown(
                answer
            )

        st.session_state.messages.append(
            AIMessage(
                content=answer
            )
        )

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

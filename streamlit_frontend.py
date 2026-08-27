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
)


# ============================================================
# GMAIL CALLBACK
# ============================================================

if "code" in st.query_params:

    callback_success = (
        handle_gmail_callback()
    )

    if callback_success:

        st.success(
            "✅ Gmail connected successfully!"
        )

        st.rerun()


# ============================================================
# AGENTFORGE LOGIN
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
# LOAD GMAIL FROM DATABASE
# ============================================================

gmail_connected = (
    is_gmail_connected()
)

gmail_email = (
    get_connected_gmail_email()
)


# Keep session state synchronized

st.session_state[
    "gmail_connected"
] = gmail_connected

st.session_state[
    "gmail_email"
] = gmail_email


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
# GMAIL
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

        disconnect_gmail()

        st.rerun()


else:

    st.sidebar.info(
        "Gmail is not connected."
    )


    # ========================================================
    # CONNECT BUTTON
    # ========================================================

    if st.sidebar.button(
        "🔗 Connect My Gmail",
        use_container_width=True,
    ):

        try:

            auth_url = connect_gmail()


            if auth_url:

                # Store URL in session
                st.session_state[
                    "gmail_auth_url"
                ] = auth_url

                st.rerun()


            else:

                st.error(
                    "Unable to start Gmail authorization."
                )


        except Exception as e:

            st.error(
                f"Gmail authorization error: {e}"
            )


# ============================================================
# OPEN GOOGLE AUTHORIZATION
# ============================================================

auth_url = st.session_state.get(
    "gmail_auth_url"
)


if auth_url and not gmail_connected:

    st.markdown(
        "### 🔐 Gmail Authorization"
    )

    st.info(
        "Click the button below. "
        "Google will open in a new browser tab."
    )


    # IMPORTANT:
    # Normal HTML link with target="_blank".
    #
    # Do NOT use meta refresh.
    # Do NOT use st.components.v1.html.
    #

    st.markdown(
        f"""
        <a href="{auth_url}"
           target="_blank"
           rel="noopener noreferrer">
            <button style="
                padding: 12px 22px;
                font-size: 16px;
                border-radius: 8px;
                border: none;
                cursor: pointer;
            ">
                🔐 Open Google Gmail Authorization
            </button>
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.warning(
        "After you authorize Gmail, "
        "Google will return to AgentForge. "
        "Then refresh this page once if the "
        "connection status does not update automatically."
    )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown("---")


if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    st.session_state.pop(
        "gmail_auth_url",
        None
    )

    st.session_state.pop(
        "gmail_oauth_state",
        None
    )

    st.logout()


# ============================================================
# DEBUG
# ============================================================

with st.sidebar.expander(
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
        "📧 Gmail is not connected."
    )


# ============================================================
# CHAT HISTORY
# ============================================================

if "messages" not in st.session_state:

    st.session_state.messages = []


# ============================================================
# DISPLAY CHAT
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


            # =================================================
            # EXTRACT ANSWER
            # =================================================

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


            st.markdown(
                answer
            )


        # ====================================================
        # SAVE ANSWER
        # ====================================================

        st.session_state.messages.append(
            AIMessage(
                content=answer
            )
        )


    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

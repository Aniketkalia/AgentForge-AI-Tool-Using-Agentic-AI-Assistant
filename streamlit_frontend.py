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
# HANDLE GMAIL CALLBACK FIRST
# ============================================================

if "code" in st.query_params:

    success = handle_gmail_callback()

    if success:

        st.success(
            "✅ Gmail connected successfully!"
        )

        # Small delay is unnecessary.
        # Rerun after callback has been processed.
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
# USER
# ============================================================

user_email = st.user.email
user_id = st.user.get("sub")


# ============================================================
# GET PERSISTENT GMAIL STATUS
# ============================================================

gmail_connected = is_gmail_connected()

gmail_email = get_connected_gmail_email()


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

    st.sidebar.caption(
        gmail_email
    )

    if st.sidebar.button(
        "Disconnect Gmail",
        use_container_width=True,
    ):

        disconnect_gmail()

        st.rerun()


else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    # --------------------------------------------------------
    # CREATE OAUTH URL
    # --------------------------------------------------------

    try:

        auth_url = connect_gmail()

    except Exception as e:

        auth_url = None

        st.sidebar.error(
            f"OAuth error: {e}"
        )


    # --------------------------------------------------------
    # NORMAL HTML LINK
    # --------------------------------------------------------

    if auth_url:

        st.sidebar.markdown(
            f"""
            <a href="{auth_url}"
               target="_blank"
               style="
                    display:block;
                    width:100%;
                    padding:10px;
                    background:#ff4b4b;
                    color:white;
                    text-align:center;
                    text-decoration:none;
                    border-radius:8px;
                    font-weight:600;
               ">
               🔗 Connect My Gmail
            </a>
            """,
            unsafe_allow_html=True,
        )

        st.sidebar.caption(
            "Google will open in a new tab."
        )

    else:

        st.sidebar.error(
            "Unable to create Gmail authorization URL."
        )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

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


# ============================================================
# DISPLAY HISTORY
# ============================================================

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
# CHAT
# ============================================================

prompt = st.chat_input(
    "Ask me anything..."
)


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
    # AGENT
    # ========================================================

    try:

        with st.chat_message("assistant"):

            response = chatbot.invoke(
                {
                    "messages": [
                        human_message
                    ]
                }
            )


            # ------------------------------------------------
            # EXTRACT ANSWER
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


        # ----------------------------------------------------
        # SAVE ANSWER
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

# streamlit_frontend.py

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
# GOOGLE OAUTH CALLBACK
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            st.session_state[
                "gmail_connected"
            ] = True

            st.rerun()

    except Exception as e:

        st.error(
            f"Gmail connection failed: {e}"
        )


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
# GMAIL STATUS
# ============================================================

try:

    gmail_email = (
        get_connected_gmail_email()
    )

    gmail_connected = (
        gmail_email is not None
        and is_gmail_connected()
    )

except Exception as e:

    gmail_email = None

    gmail_connected = False

    st.warning(
        f"Gmail storage check failed: {e}"
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
        "🔌 Disconnect Gmail",
        use_container_width=True,
    ):

        disconnect_gmail(
            user_id
        )

        st.session_state[
            "gmail_connected"
        ] = False

        st.session_state[
            "gmail_email"
        ] = None

        st.rerun()

else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    if st.sidebar.button(
        "🔗 Connect My Gmail",
        use_container_width=True,
    ):

        try:

            auth_url = connect_gmail()

            if auth_url:

                # IMPORTANT:
                # Use Streamlit's browser navigation.
                #
                # Do not create a meta-refresh page.
                # Do not open a popup.
                #
                # This prevents the blank Chrome page problem.

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

    st.session_state.pop(
        "gmail_connected",
        None,
    )

    st.session_state.pop(
        "gmail_email",
        None,
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

try:

    from backend import chatbot

except Exception as e:

    st.error(
        f"Backend import error: {e}"
    )

    st.stop()


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

            # IMPORTANT:
            # Your LangGraph chatbot has a checkpointer.
            #
            # Therefore we MUST provide thread_id.

            response = chatbot.invoke(

                {
                    "messages": [
                        human_message
                    ]
                },

                config={
                    "configurable": {
                        "thread_id": user_id
                    }
                },
            )

            # =================================================
            # EXTRACT RESPONSE
            # =================================================

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

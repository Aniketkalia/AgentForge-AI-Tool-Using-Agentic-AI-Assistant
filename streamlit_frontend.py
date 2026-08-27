import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
    get_connected_gmail_email,
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
# GOOGLE LOGIN
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
# LANGGRAPH THREAD
# ============================================================

thread_id = (
    f"agentforge-{user_id}"
)


config = {

    "configurable": {

        "thread_id":
            thread_id
    }
}


# ============================================================
# GMAIL CALLBACK
# ============================================================

if "code" in st.query_params:

    try:

        success = (
            handle_gmail_callback()
        )

        if success:

            # Remove OAuth query parameters
            st.query_params.clear()

            st.session_state[
                "gmail_auth_url"
            ] = None

            st.rerun()

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        # Remove bad OAuth parameters
        st.query_params.clear()


# ============================================================
# GMAIL STATUS
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
    )

except Exception as e:

    gmail_error = str(e)


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
# LOAD LANGGRAPH HISTORY
# ============================================================

if (
    "messages_loaded"
    not in st.session_state
):

    st.session_state[
        "messages_loaded"
    ] = True

    try:

        state = chatbot.get_state(
            config
        )

        if (
            state
            and state.values
        ):

            saved_messages = (
                state.values.get(
                    "messages",
                    [],
                )
            )

            st.session_state[
                "messages"
            ] = saved_messages.copy()

        else:

            st.session_state[
                "messages"
            ] = []

    except Exception:

        st.session_state[
            "messages"
        ] = []


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

                st.session_state[
                    "gmail_auth_url"
                ] = auth_url

                st.rerun()

            else:

                st.sidebar.error(
                    "Unable to create Gmail authorization URL."
                )

        except Exception as e:

            st.sidebar.error(
                f"Gmail authorization error: {e}"
            )


# ============================================================
# AUTHORIZATION LINK
# ============================================================

if (
    st.session_state.get(
        "gmail_auth_url"
    )
):

    auth_url = (
        st.session_state[
            "gmail_auth_url"
        ]
    )

    st.sidebar.markdown(
        "### 🔐 Gmail Authorization"
    )

    st.sidebar.markdown(
        f"""
        <a
            href="{auth_url}"
            target="_self"
            style="
                display:block;
                width:100%;
                padding:0.7rem;
                background:#FF4B4B;
                color:white;
                text-align:center;
                text-decoration:none;
                border-radius:8px;
                font-weight:600;
            "
        >
            Continue with Google
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.caption(
        "Google authorization will open in this tab."
    )


# ============================================================
# STORAGE ERROR
# ============================================================

if gmail_error:

    st.sidebar.warning(
        f"Gmail storage check failed: {gmail_error}"
    )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    for key in [
        "messages",
        "messages_loaded",
        "gmail_connected",
        "gmail_email",
        "gmail_auth_url",
        "gmail_oauth_state",
        "gmail_oauth_redirect_uri",
    ]:

        st.session_state.pop(
            key,
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
        "User ID:",
        user_id,
    )

    st.write(
        "User Email:",
        user_email,
    )

    st.write(
        "Thread ID:",
        thread_id,
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

messages = st.session_state.get(
    "messages",
    []
)


for message in messages:

    if isinstance(
        message,
        HumanMessage,
    ):

        with st.chat_message(
            "user"
        ):

            st.markdown(
                message.content
            )

    elif isinstance(
        message,
        AIMessage,
    ):

        if message.content:

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
# PROCESS MESSAGE
# ============================================================

if prompt:

    human_message = (
        HumanMessage(
            content=prompt
        )
    )

    with st.chat_message(
        "user"
    ):

        st.markdown(
            prompt
        )

    try:

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "Agent is thinking..."
            ):

                response = (
                    chatbot.invoke(
                        {
                            "messages": [
                                human_message
                            ]
                        },
                        config=config,
                    )
                )

            answer = None

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

                for msg in reversed(
                    response_messages
                ):

                    if isinstance(
                        msg,
                        AIMessage,
                    ):

                        if msg.content:

                            answer = (
                                msg.content
                            )

                            break

                if answer is None:

                    if response_messages:

                        last_message = (
                            response_messages[-1]
                        )

                        if hasattr(
                            last_message,
                            "content",
                        ):

                            answer = (
                                last_message.content
                            )

                        else:

                            answer = str(
                                last_message
                            )

            else:

                answer = str(
                    response
                )

            if not answer:

                answer = (
                    "I couldn't generate a response."
                )

            st.markdown(
                answer
            )

        # ----------------------------------------------------
        # Reload saved state
        # ----------------------------------------------------

        try:

            latest_state = (
                chatbot.get_state(
                    config
                )
            )

            if (
                latest_state
                and latest_state.values
            ):

                saved_messages = (
                    latest_state.values.get(
                        "messages",
                        [],
                    )
                )

                st.session_state[
                    "messages"
                ] = (
                    saved_messages.copy()
                )

            else:

                st.session_state[
                    "messages"
                ].append(
                    human_message
                )

                st.session_state[
                    "messages"
                ].append(
                    AIMessage(
                        content=answer
                    )
                )

        except Exception:

            st.session_state[
                "messages"
            ].append(
                human_message
            )

            st.session_state[
                "messages"
            ].append(
                AIMessage(
                    content=answer
                )
            )

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

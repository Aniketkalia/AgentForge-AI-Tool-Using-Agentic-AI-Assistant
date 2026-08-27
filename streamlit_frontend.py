# streamlit_frontend.py

import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
    get_connected_gmail_email,
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
# AGENTFORGE LOGIN
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
    ):

        st.login()

    st.stop()


# ============================================================
# CURRENT USER
# ============================================================

user_email = st.user.email

user_id = st.user.get(
    "sub"
)


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

            st.session_state.pop(
                "gmail_auth_url",
                None
            )

            st.session_state[
                "gmail_connected"
            ] = True

            st.rerun()

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        st.query_params.clear()


# ============================================================
# GMAIL STATUS
# ============================================================

gmail_email = None

gmail_connected = False

try:

    gmail_email = (
        get_connected_gmail_email()
    )

    gmail_connected = (
        gmail_email is not None
    )

except Exception:

    gmail_connected = False


st.session_state[
    "gmail_connected"
] = gmail_connected


st.session_state[
    "gmail_email"
] = gmail_email


# ============================================================
# LOAD CHAT HISTORY
# ============================================================

if "messages_loaded" not in st.session_state:

    st.session_state[
        "messages_loaded"
    ] = True

    try:

        state = (
            chatbot.get_state(
                config
            )
        )

        if state and state.values:

            saved_messages = (
                state.values.get(
                    "messages",
                    []
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

st.sidebar.markdown(
    "---"
)

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

        disconnect_gmail()

        st.session_state.pop(
            "gmail_auth_url",
            None
        )

        st.rerun()

else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    # --------------------------------------------------------
    # CONNECT BUTTON
    # --------------------------------------------------------

    if st.sidebar.button(
        "🔗 Connect My Gmail",
        use_container_width=True,
    ):

        try:

            auth_url = (
                connect_gmail()
            )

            if auth_url:

                st.session_state[
                    "gmail_auth_url"
                ] = auth_url

            else:

                st.sidebar.error(
                    "Unable to create Gmail authorization URL."
                )

        except Exception as e:

            st.sidebar.error(
                f"Gmail OAuth error: {e}"
            )


# ============================================================
# AUTHORIZATION LINK
#
# SAME TAB
# NO POPUP
# ============================================================

if (
    not gmail_connected
    and
    "gmail_auth_url"
    in st.session_state
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
                padding:0.7rem 1rem;
                background:#FF4B4B;
                color:white;
                text-align:center;
                text-decoration:none;
                border-radius:0.5rem;
                font-weight:600;
                margin-bottom:0.5rem;
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
# LOGOUT
# ============================================================

st.sidebar.markdown(
    "---"
)


if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    try:

        disconnect_gmail()

    except Exception:
        pass

    for key in [

        "messages",

        "messages_loaded",

        "gmail_connected",

        "gmail_email",

        "gmail_auth_url",

    ]:

        st.session_state.pop(
            key,
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
        "AgentForge Email:",
        user_email
    )

    st.write(
        "AgentForge User ID:",
        user_id
    )

    st.write(
        "Thread ID:",
        thread_id
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
# MAIN
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

        content = message.content

        if content:

            with st.chat_message(
                "assistant"
            ):

                st.markdown(
                    content
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

    # --------------------------------------------------------
    # DISPLAY USER MESSAGE
    # --------------------------------------------------------

    with st.chat_message(
        "user"
    ):

        st.markdown(
            prompt
        )

    # --------------------------------------------------------
    # RUN AGENT
    # --------------------------------------------------------

    try:

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "Agent is thinking..."
            ):

                response = chatbot.invoke(

                    {
                        "messages": [
                            human_message
                        ]
                    },

                    config=config,
                )

            # ------------------------------------------------
            # FIND FINAL AI RESPONSE
            # ------------------------------------------------

            answer = None

            response_messages = (
                response.get(
                    "messages",
                    []
                )
                if isinstance(
                    response,
                    dict
                )
                else []
            )

            for msg in reversed(
                response_messages
            ):

                if isinstance(
                    msg,
                    AIMessage
                ):

                    if msg.content:

                        answer = (
                            msg.content
                        )

                        break

            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            if not answer:

                answer = (
                    "I couldn't generate "
                    "a response."
                )

            st.markdown(
                answer
            )

        # ----------------------------------------------------
        # REFRESH CHAT FROM CHECKPOINT
        # ----------------------------------------------------

        try:

            latest_state = (
                chatbot.get_state(
                    config
                )
            )

            if (
                latest_state
                and
                latest_state.values
            ):

                saved_messages = (
                    latest_state.values.get(
                        "messages",
                        []
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

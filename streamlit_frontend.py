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
# IMPORTANT:
# LANGGRAPH THREAD ID
#
# Every logged-in user gets one stable conversation thread.
#
# Because this value comes from Google user's `sub`,
# refreshing the browser will use the SAME thread.
# ============================================================

thread_id = f"agentforge-{user_id}"


# ============================================================
# LANGGRAPH CONFIG
# ============================================================

config = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ============================================================
# GMAIL OAUTH CALLBACK
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Remove OAuth parameters from URL
            st.query_params.clear()

            # Refresh application
            st.rerun()

    except Exception as e:

        st.error(
            f"❌ Gmail connection failed: {e}"
        )

        # Remove bad OAuth parameters
        st.query_params.clear()


# ============================================================
# GET GMAIL STATUS
# ============================================================

gmail_email = None
gmail_connected = False
gmail_error = None

try:

    gmail_email = get_connected_gmail_email()

    gmail_connected = (
        gmail_email is not None
    )

except Exception as e:

    gmail_error = str(e)


# ============================================================
# KEEP SESSION CACHE SYNCHRONIZED
# ============================================================

st.session_state["gmail_connected"] = (
    gmail_connected
)

st.session_state["gmail_email"] = (
    gmail_email
)


# ============================================================
# LOAD CHAT FROM LANGGRAPH CHECKPOINTER
#
# This is the important part for browser refresh.
# ============================================================

if "messages_loaded" not in st.session_state:

    st.session_state["messages_loaded"] = True

    try:

        state = chatbot.get_state(config)

        if state and state.values:

            saved_messages = (
                state.values.get(
                    "messages",
                    []
                )
            )

            st.session_state["messages"] = (
                saved_messages.copy()
            )

        else:

            st.session_state["messages"] = []

    except Exception as e:

        # If there is no previous checkpoint,
        # simply start a new conversation.
        st.session_state["messages"] = []

        st.session_state[
            "checkpoint_error"
        ] = str(e)


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

else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    # --------------------------------------------------------
    # CONNECT GMAIL
    # --------------------------------------------------------

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

            else:

                st.sidebar.error(
                    "Unable to create Gmail authorization URL."
                )

        except Exception as e:

            st.sidebar.error(
                f"Gmail authorization error: {e}"
            )


# ============================================================
# GMAIL AUTHORIZATION LINK
#
# Uses SAME TAB.
# No popup.
# No small Chrome window.
# ============================================================

if "gmail_auth_url" in st.session_state:

    auth_url = st.session_state[
        "gmail_auth_url"
    ]

    st.sidebar.markdown(
        "### 🔐 Gmail Authorization"
    )

    st.sidebar.markdown(
        f"""
        <a href="{auth_url}"
           target="_self"
           style="
               display:block;
               width:100%;
               padding:0.6rem 1rem;
               background:#FF4B4B;
               color:white;
               text-align:center;
               text-decoration:none;
               border-radius:0.5rem;
               font-weight:600;
               margin-bottom:0.5rem;
           ">
           Continue with Google
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.caption(
        "Google authorization will open in this tab."
    )


# ============================================================
# GMAIL ERROR
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

    # Clear frontend session values

    keys_to_remove = [
        "messages",
        "messages_loaded",
        "gmail_connected",
        "gmail_email",
        "gmail_auth_url",
        "gmail_oauth_state",
        "checkpoint_error",
    ]

    for key in keys_to_remove:

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
        "AgentForge User ID:",
        user_id
    )

    st.write(
        "AgentForge Email:",
        user_email
    )

    st.write(
        "LangGraph Thread ID:",
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
# CHECKPOINT ERROR
# ============================================================

if "checkpoint_error" in st.session_state:

    # Do not show an error if it is simply
    # because there is no previous checkpoint.

    checkpoint_error = (
        st.session_state[
            "checkpoint_error"
        ]
    )

    if (
        "No checkpoint found"
        not in checkpoint_error
    ):

        # Keep this hidden from normal users.
        # Uncomment while debugging.

        # st.info(
        #     f"Checkpoint info: {checkpoint_error}"
        # )

        pass


# ============================================================
# CHAT HISTORY
# ============================================================

messages = st.session_state.get(
    "messages",
    []
)


# ============================================================
# DISPLAY CHAT HISTORY
# ============================================================

for message in messages:

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

        # Ignore tool-call-only messages
        # that may not have normal text.

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
# PROCESS USER MESSAGE
# ============================================================

if prompt:

    # ========================================================
    # USER MESSAGE
    # ========================================================

    human_message = HumanMessage(
        content=prompt
    )

    # Show immediately

    with st.chat_message("user"):

        st.markdown(
            prompt
        )


    # ========================================================
    # RUN LANGGRAPH AGENT
    # ========================================================

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


            # =================================================
            # EXTRACT RESPONSE
            # =================================================

            answer = None


            if isinstance(
                response,
                dict,
            ):

                response_messages = (
                    response.get(
                        "messages",
                        []
                    )
                )

                if response_messages:

                    # Find the last AI message
                    # containing actual content.

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

                    # Fallback

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

            else:

                answer = str(
                    response
                )


            # =================================================
            # SHOW ANSWER
            # =================================================

            if answer:

                st.markdown(
                    answer
                )

            else:

                answer = (
                    "I couldn't generate a response."
                )

                st.markdown(
                    answer
                )


        # ====================================================
        # IMPORTANT:
        #
        # DO NOT manually append the response here.
        #
        # LangGraph checkpointer already saved
        # the conversation.
        #
        # Reload state from checkpoint.
        # ====================================================

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
                        []
                    )
                )

                st.session_state[
                    "messages"
                ] = saved_messages.copy()

            else:

                # Fallback only

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

            # Fallback if state retrieval fails

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


    # ========================================================
    # ERROR
    # ========================================================

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

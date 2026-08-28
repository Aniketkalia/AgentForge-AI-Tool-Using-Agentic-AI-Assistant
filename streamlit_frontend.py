import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

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
# GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title("🤖 AgentForge AI")
    st.subheader("Tool-Using Agentic AI Assistant")

    st.write("Please login with your Google account to continue.")

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

if not user_id:

    st.error(
        "❌ Unable to identify your Google account."
    )

    st.stop()


# ============================================================
# IMPORT BACKEND AFTER LOGIN
# ============================================================

try:

    from backend import chatbot

except Exception as e:

    st.error(
        f"❌ Backend initialization failed:\n\n{e}"
    )

    st.stop()


# ============================================================
# IMPORT GMAIL
# ============================================================

try:

    from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
    get_connected_gmail_email,
)
except Exception as e:

    st.error(
        f"❌ Gmail module failed:\n\n{e}"
    )

    st.stop()


# ============================================================
# STABLE THREAD ID
# ============================================================

# One stable thread for each AgentForge Google user.

thread_id = f"agentforge-{user_id}"


# ============================================================
# LANGGRAPH CONFIG
# ============================================================

LANGGRAPH_CONFIG = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ============================================================
# GMAIL CALLBACK
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Remove OAuth query parameters
            st.query_params.clear()

            # Clear temporary auth state
            st.session_state.pop(
                "gmail_auth_url",
                None,
            )

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

        try:
            st.query_params.clear()
        except Exception:
            pass

        st.stop()


# ============================================================
# GMAIL STATUS
# ============================================================

gmail_email = None
gmail_connected = False
gmail_error = None

try:

    gmail_email = get_connected_gmail_email()

    gmail_connected = bool(
        gmail_email
    )

except Exception as e:

    gmail_error = str(e)


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:

    st.session_state[
        "messages"
    ] = []


if "messages_loaded" not in st.session_state:

    st.session_state[
        "messages_loaded"
    ] = False


# ============================================================
# LOAD SAVED CHAT
# ============================================================

if not st.session_state["messages_loaded"]:

    st.session_state[
        "messages_loaded"
    ] = True

    try:

        state = chatbot.get_state(
            config=LANGGRAPH_CONFIG
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
            ] = list(saved_messages)

    except Exception as e:

        # A new thread does not have a checkpoint yet.
        # Do not show this as a user-facing error.

        st.session_state[
            "messages"
        ] = []

        st.session_state[
            "checkpoint_error"
        ] = str(e)


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

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        st.caption(
            gmail_email
        )

        if st.button(
            "Disconnect Gmail",
            use_container_width=True,
        ):

            try:

                disconnect_gmail()

                st.session_state[
                    "gmail_connected"
                ] = False

                st.session_state[
                    "gmail_email"
                ] = None

                st.session_state.pop(
                    "gmail_auth_url",
                    None
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"Disconnect failed: {e}"
                )

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        if gmail_error:

            st.caption(
                f"Storage status: {gmail_error}"
            )

        # ----------------------------------------------------
        # CONNECT BUTTON
        # ----------------------------------------------------

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True,
            type="primary",
        ):

            try:

                auth_url = connect_gmail()

                if auth_url:

                    st.session_state[
                        "gmail_auth_url"
                    ] = auth_url

                else:

                    st.error(
                        "❌ Unable to create Gmail authorization URL."
                    )

            except Exception as e:

                st.error(
                    f"❌ Gmail authorization error: {e}"
                )


    # --------------------------------------------------------
    # AUTHORIZATION LINK
    # --------------------------------------------------------

    auth_url = st.session_state.get(
        "gmail_auth_url"
    )

    if auth_url and not gmail_connected:

        st.markdown(
            "### 🔐 Continue Gmail Authorization"
        )

        st.markdown(
            f"""
            <a href="{auth_url}"
               target="_self"
               style="
                    display:block;
                    width:100%;
                    padding:12px;
                    background:#FF4B4B;
                    color:white;
                    text-align:center;
                    text-decoration:none;
                    border-radius:8px;
                    font-weight:600;
               ">
                Continue with Google
            </a>
            """,
            unsafe_allow_html=True,
        )

        st.caption(
            "Google authorization will continue in this tab."
        )


    st.divider()


    # --------------------------------------------------------
    # NEW CHAT
    # --------------------------------------------------------

    if st.button(
        "🆕 New Chat",
        use_container_width=True,
    ):

        # Create a new thread ID.

        new_thread_id = (
            f"agentforge-{user_id}-"
            f"{__import__('uuid').uuid4()}"
        )

        st.session_state[
            "active_thread_id"
        ] = new_thread_id

        st.session_state[
            "messages"
        ] = []

        st.session_state[
            "messages_loaded"
        ] = True

        st.rerun()


    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        for key in [
            "messages",
            "messages_loaded",
            "gmail_connected",
            "gmail_email",
            "gmail_auth_url",
            "checkpoint_error",
        ]:

            st.session_state.pop(
                key,
                None,
            )

        st.logout()


    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    with st.expander("🔧 Debug"):

        st.write(
            "AgentForge Email:",
            user_email,
        )

        st.write(
            "AgentForge User ID:",
            user_id,
        )

        st.write(
            "LangGraph Thread ID:",
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

    st.info(
        "📧 Gmail is not connected. "
        "Connect Gmail from the sidebar "
        "to send emails."
    )


# ============================================================
# CHAT HISTORY
# ============================================================

messages = st.session_state.get(
    "messages",
    []
)


# ============================================================
# DISPLAY HISTORY
# ============================================================

for message in messages:

    if isinstance(
        message,
        HumanMessage,
    ):

        content = message.content

        if isinstance(content, str):

            with st.chat_message("user"):

                st.markdown(content)


    elif isinstance(
        message,
        AIMessage,
    ):

        content = message.content

        if isinstance(content, str) and content.strip():

            with st.chat_message(
                "assistant"
            ):

                st.markdown(content)


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

    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    human_message = HumanMessage(
        content=prompt
    )

    with st.chat_message("user"):

        st.markdown(prompt)


    # --------------------------------------------------------
    # ALWAYS BUILD A VALID CONFIG
    # --------------------------------------------------------

    active_thread_id = st.session_state.get(
        "active_thread_id",
        thread_id,
    )

    run_config = {
        "configurable": {
            "thread_id": active_thread_id
        }
    }


    # --------------------------------------------------------
    # RUN AGENT
    # --------------------------------------------------------

    try:

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "🤖 Agent is thinking..."
            ):

                response = chatbot.invoke(
                    {
                        "messages": [
                            human_message
                        ]
                    },
                    config=run_config,
                )


            # ------------------------------------------------
            # EXTRACT ANSWER
            # ------------------------------------------------

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

                for msg in reversed(
                    response_messages
                ):

                    if isinstance(
                        msg,
                        AIMessage,
                    ):

                        content = msg.content

                        if isinstance(
                            content,
                            str,
                        ) and content.strip():

                            answer = content

                            break

                if answer is None:

                    if response_messages:

                        last_message = (
                            response_messages[-1]
                        )

                        answer = str(
                            getattr(
                                last_message,
                                "content",
                                last_message,
                            )
                        )

            else:

                answer = str(response)


            # ------------------------------------------------
            # DISPLAY ANSWER
            # ------------------------------------------------

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


        # ----------------------------------------------------
        # RELOAD CHECKPOINT
        # ----------------------------------------------------

        try:

            latest_state = chatbot.get_state(
                config=run_config
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
                ] = list(
                    saved_messages
                )

        except Exception:

            # Safe UI fallback.

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


    # --------------------------------------------------------
    # AGENT ERROR
    # --------------------------------------------------------

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

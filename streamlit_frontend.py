import html
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
# INITIAL SESSION STATE
# ============================================================

if "gmail_connected" not in st.session_state:
    st.session_state["gmail_connected"] = False

if "gmail_email" not in st.session_state:
    st.session_state["gmail_email"] = None

if "gmail_auth_url" not in st.session_state:
    st.session_state["gmail_auth_url"] = None

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "messages_loaded" not in st.session_state:
    st.session_state["messages_loaded"] = False

if "checkpoint_error" not in st.session_state:
    st.session_state["checkpoint_error"] = None


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


if not user_id:

    st.error(
        "❌ Unable to identify the logged-in Google user."
    )

    st.stop()


# ============================================================
# LANGGRAPH THREAD ID
# ============================================================

# Every logged-in Google user gets a stable thread.

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

# Google redirects back to the Streamlit application with:
#
# ?code=XXXX
# &state=XXXX
#
# Handle this BEFORE loading normal Gmail status.

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Clear OAuth URL stored in session.
            st.session_state["gmail_auth_url"] = None

            # Clear old connection cache.
            st.session_state["gmail_connected"] = False
            st.session_state["gmail_email"] = None

            # Remove OAuth query parameters.
            st.query_params.clear()

            # Reload application.
            st.rerun()

        else:

            st.error(
                "❌ Gmail authorization failed."
            )

            st.query_params.clear()

            st.stop()

    except Exception as e:

        st.error(
            f"❌ Gmail callback error: {e}"
        )

        st.query_params.clear()

        st.stop()


# ============================================================
# GMAIL STATUS
# ============================================================

gmail_email = None
gmail_connected = False
gmail_error = None


try:

    gmail_email = get_connected_gmail_email()

    if gmail_email:

        gmail_connected = True

except Exception as e:

    gmail_error = str(e)

    gmail_connected = False
    gmail_email = None


# ============================================================
# UPDATE SESSION STATE
# ============================================================

st.session_state["gmail_connected"] = gmail_connected
st.session_state["gmail_email"] = gmail_email


# ============================================================
# LOAD LANGGRAPH CHAT HISTORY
# ============================================================

if not st.session_state["messages_loaded"]:

    st.session_state["messages_loaded"] = True

    try:

        state = chatbot.get_state(
            config
        )

        if state and state.values:

            saved_messages = state.values.get(
                "messages",
                []
            )

            st.session_state["messages"] = (
                saved_messages.copy()
            )

        else:

            st.session_state["messages"] = []

    except Exception as e:

        st.session_state["messages"] = []

        st.session_state["checkpoint_error"] = str(e)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "🤖 AgentForge"
    )

    st.caption(
        "LangGraph • Groq • Gmail • Web Search • Tools"
    )

    st.divider()


    # ========================================================
    # CURRENT USER
    # ========================================================

    st.success(
        f"👤 {user_email}"
    )


    # ========================================================
    # GMAIL
    # ========================================================

    st.divider()

    st.subheader(
        "📧 Gmail"
    )


    # ========================================================
    # GMAIL CONNECTED
    # ========================================================

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        if gmail_email:

            st.markdown(
                f"**Connected account:**  \n"
                f"{gmail_email}"
            )

        st.caption(
            "AgentForge can send emails using this Gmail account."
        )


    # ========================================================
    # GMAIL NOT CONNECTED
    # ========================================================

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        st.caption(
            "Connect your Gmail to allow AgentForge to send emails."
        )


        # ----------------------------------------------------
        # CREATE AUTH URL
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
                        "Unable to create Gmail authorization URL."
                    )

            except Exception as e:

                st.error(
                    f"Gmail authorization error: {e}"
                )


        # ----------------------------------------------------
        # AUTHORIZATION LINK
        # ----------------------------------------------------

        auth_url = st.session_state.get(
            "gmail_auth_url"
        )


        if auth_url:

            # Escape URL before putting it into HTML.
            safe_auth_url = html.escape(
                auth_url,
                quote=True
            )


            st.markdown(
                f"""
                <a
                    href="{safe_auth_url}"
                    target="_blank"
                    rel="noopener noreferrer"
                    style="
                        display:block;
                        width:100%;
                        padding:0.65rem 1rem;
                        background-color:#FF4B4B;
                        color:white;
                        text-align:center;
                        text-decoration:none;
                        border-radius:0.5rem;
                        font-weight:600;
                        margin-top:0.5rem;
                        box-sizing:border-box;
                    "
                >
                    🔐 Continue with Google
                </a>
                """,
                unsafe_allow_html=True,
            )


            st.caption(
                "Google authorization will open in a new tab."
            )


    # ========================================================
    # GMAIL ERROR
    # ========================================================

    if gmail_error:

        st.warning(
            f"Gmail storage check failed: {gmail_error}"
        )


    # ========================================================
    # NEW CHAT
    # ========================================================

    st.divider()

    if st.button(
        "🆕 New Chat",
        use_container_width=True,
    ):

        st.session_state["messages"] = []

        st.session_state["messages_loaded"] = True

        st.rerun()


    # ========================================================
    # LOGOUT
    # ========================================================

    st.divider()

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        keys_to_remove = [
            "messages",
            "messages_loaded",
            "gmail_connected",
            "gmail_email",
            "gmail_auth_url",
            "gmail_oauth_state",
            "gmail_oauth_verifier",
            "checkpoint_error",
        ]

        for key in keys_to_remove:

            st.session_state.pop(
                key,
                None
            )


        st.logout()


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

    st.info(
        "📧 Gmail is not connected. "
        "Connect Gmail from the sidebar to send emails."
    )


# ============================================================
# CHECKPOINT ERROR
# ============================================================

checkpoint_error = st.session_state.get(
    "checkpoint_error"
)


if checkpoint_error:

    # Don't show normal "no checkpoint" errors.
    if (
        "No checkpoint found"
        not in checkpoint_error
        and
        "not found"
        not in checkpoint_error.lower()
    ):

        with st.expander(
            "🔧 Debug: LangGraph checkpoint"
        ):

            st.write(
                checkpoint_error
            )


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

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    if isinstance(
        message,
        HumanMessage
    ):

        content = message.content

        if isinstance(
            content,
            str
        ) and content.strip():

            with st.chat_message(
                "user"
            ):

                st.markdown(
                    content
                )


    # --------------------------------------------------------
    # ASSISTANT
    # --------------------------------------------------------

    elif isinstance(
        message,
        AIMessage
    ):

        content = message.content

        if isinstance(
            content,
            str
        ) and content.strip():

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
            # EXTRACT ANSWER
            # =================================================

            answer = None


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


                # Find last AI message.
                for msg in reversed(
                    response_messages
                ):

                    if isinstance(
                        msg,
                        AIMessage
                    ):

                        content = msg.content


                        if isinstance(
                            content,
                            str
                        ) and content.strip():

                            answer = content

                            break


                # ------------------------------------------------
                # FALLBACK
                # ------------------------------------------------

                if answer is None:

                    if response_messages:

                        last_message = (
                            response_messages[-1]
                        )


                        if hasattr(
                            last_message,
                            "content"
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
        # RELOAD SAVED LANGGRAPH STATE
        # ====================================================

        try:

            latest_state = chatbot.get_state(
                config
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

                # Fallback only.
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

            # Fallback if checkpoint retrieval
            # temporarily fails.

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
    # AGENT ERROR
    # ========================================================

    except Exception as e:

        st.error(
            f"❌ Agent error: {e}"
        )

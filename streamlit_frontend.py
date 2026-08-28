# ============================================================
# streamlit_frontend.py
# AgentForge AI
# Gmail OAuth + LangGraph + Groq
# ============================================================

import html
import uuid

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
# SESSION STATE
# ============================================================

if "gmail_connected" not in st.session_state:
    st.session_state["gmail_connected"] = False

if "gmail_email" not in st.session_state:
    st.session_state["gmail_email"] = None

if "gmail_auth_url" not in st.session_state:
    st.session_state["gmail_auth_url"] = None

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = str(uuid.uuid4())


# ============================================================
# 1. GMAIL OAUTH CALLBACK
# ============================================================
#
# Google redirects back to:
#
# https://your-app.streamlit.app/
#       ?code=XXXX
#       &state=XXXX
#
# This must be handled before normal UI.
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Get the Gmail account saved by gmail_auth.py
            try:

                connected_email = (
                    get_connected_gmail_email()
                )

                st.session_state[
                    "gmail_email"
                ] = connected_email

                st.session_state[
                    "gmail_connected"
                ] = bool(connected_email)

            except Exception:

                st.session_state[
                    "gmail_connected"
                ] = True

            # Remove OAuth parameters
            try:
                st.query_params.clear()
            except Exception:
                pass

            # Reload application
            st.rerun()

        else:

            st.error(
                "❌ Gmail authorization failed."
            )

            try:
                st.query_params.clear()
            except Exception:
                pass

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
# 2. AGENTFORGE GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title("🤖 AgentForge AI")

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
# 3. CURRENT USER
# ============================================================

user_email = st.user.email
user_id = st.user.get("sub")


if not user_id:

    st.error(
        "❌ Unable to identify the logged-in Google user."
    )

    st.stop()


# ============================================================
# 4. USER-SPECIFIC LANGGRAPH THREAD
# ============================================================
#
# IMPORTANT:
# Because backend.py uses SqliteSaver,
# chatbot.invoke() MUST receive:
#
# {
#     "configurable": {
#         "thread_id": "..."
#     }
# }
#
# This fixes:
#
# Checkpointer requires one or more of the following
# 'configurable' keys:
# thread_id, checkpoint_ns, checkpoint_id
# ============================================================

thread_id = (
    f"agentforge-user-{user_id}"
)


config = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ============================================================
# 5. LOAD CONNECTED GMAIL
# ============================================================
#
# Do NOT rely only on Streamlit session state.
# gmail_auth.py stores the Gmail connection in SQLite
# against the logged-in Google user's ID.
# ============================================================

gmail_email = None
gmail_connected = False
gmail_error = None


try:

    gmail_email = (
        get_connected_gmail_email()
    )

    if gmail_email:

        gmail_connected = True

except Exception as e:

    gmail_error = str(e)

    gmail_connected = False

    gmail_email = None


# Keep session state synchronized

st.session_state[
    "gmail_connected"
] = gmail_connected

st.session_state[
    "gmail_email"
] = gmail_email


# ============================================================
# 6. SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 AgentForge")

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

    st.subheader("📧 Gmail")


    # ========================================================
    # GMAIL CONNECTED
    # ========================================================

    if gmail_connected:

        st.success(
            "✅ Gmail Connected"
        )

        st.markdown(
            f"**Connected account:**  \n"
            f"{gmail_email}"
        )

        st.caption(
            "AgentForge can send emails using this Gmail account."
        )


        # ----------------------------------------------------
        # REFRESH GMAIL STATUS
        # ----------------------------------------------------

        if st.button(
            "🔄 Refresh Gmail",
            use_container_width=True,
        ):

            st.rerun()


    # ========================================================
    # GMAIL NOT CONNECTED
    # ========================================================

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        st.caption(
            "Connect your Gmail to allow AgentForge "
            "to send emails."
        )


        # ----------------------------------------------------
        # CREATE GOOGLE AUTH URL
        # ----------------------------------------------------

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True,
            type="primary",
        ):

            try:

                auth_url = connect_gmail()

                if not auth_url:

                    st.error(
                        "❌ Unable to create Gmail authorization URL."
                    )

                else:

                    st.session_state[
                        "gmail_auth_url"
                    ] = auth_url

                    st.rerun()

            except Exception as e:

                st.error(
                    f"❌ Gmail authorization error: {e}"
                )


        # ----------------------------------------------------
        # OPEN GOOGLE IN NEW TAB
        # ----------------------------------------------------
        #
        # IMPORTANT:
        #
        # Do NOT use window.open().
        #
        # Browser popup blockers can block it.
        #
        # Instead, use a normal HTML link with:
        #
        # target="_blank"
        #
        # This opens Google OAuth in a NEW TAB.
        # ----------------------------------------------------

        auth_url = st.session_state.get(
            "gmail_auth_url"
        )


        if auth_url:

            safe_url = html.escape(
                auth_url,
                quote=True,
            )

            st.markdown(
                f"""
                <a
                    href="{safe_url}"
                    target="_blank"
                    rel="noopener noreferrer"
                    style="
                        display:block;
                        width:100%;
                        padding:0.75rem 1rem;
                        background:#FF4B4B;
                        color:white;
                        text-align:center;
                        text-decoration:none;
                        border-radius:0.5rem;
                        font-weight:600;
                        margin-top:0.75rem;
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

            st.info(
                """
                **Gmail connection steps**

                1. Click **Continue with Google**
                2. A new tab will open.
                3. Select your Gmail account.
                4. Click **Allow**.
                5. Google redirects the new tab back to AgentForge.
                6. Return to this tab.
                7. Click **🔄 Refresh Gmail** if needed.
                """
            )


    # ========================================================
    # GMAIL ERROR
    # ========================================================

    if gmail_error:

        st.error(
            f"Gmail status error: {gmail_error}"
        )


    # ========================================================
    # CLEAR OLD AUTH URL
    # ========================================================

    if st.session_state.get(
        "gmail_auth_url"
    ):

        if st.button(
            "❌ Cancel Gmail Connection",
            use_container_width=True,
        ):

            st.session_state[
                "gmail_auth_url"
            ] = None

            st.rerun()


    # ========================================================
    # NEW CHAT
    # ========================================================

    st.divider()

    if st.button(
        "🆕 New Chat",
        use_container_width=True,
    ):

        st.session_state[
            "messages"
        ] = []

        st.session_state[
            "thread_id"
        ] = str(uuid.uuid4())

        st.rerun()


    # ========================================================
    # DEBUG
    # ========================================================

    with st.expander(
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
            "Connected Gmail:",
            gmail_email,
        )

        st.write(
            "LangGraph Thread ID:",
            thread_id,
        )


    # ========================================================
    # LOGOUT
    # ========================================================

    st.divider()

    if st.button(
        "🚪 Logout",
        use_container_width=True,
    ):

        # Do NOT delete Gmail token here.
        #
        # Gmail connection remains in persistent
        # SQLite storage.

        st.session_state[
            "messages"
        ] = []

        st.session_state[
            "gmail_auth_url"
        ] = None

        st.logout()


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
# CHAT HISTORY
# ============================================================

for message in st.session_state["messages"]:

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

        # Don't display empty AI messages

        if (
            isinstance(
                message.content,
                str,
            )
            and message.content.strip()
        ):

            with st.chat_message(
                "assistant"
            ):

                st.markdown(
                    message.content
                )


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state["messages"]:

    st.info(
        "👋 Welcome to AgentForge AI!"
    )

    col1, col2, col3 = st.columns(3)


    with col1:

        st.markdown(
            """
            **🧮 Calculator**

            `Calculate 125 * 48`
            """
        )


    with col2:

        st.markdown(
            """
            **📧 Gmail**

            `Send an email to someone@example.com`
            """
        )


    with col3:

        st.markdown(
            """
            **🌐 Web Search**

            `Search the latest AI news`
            """
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

    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    human_message = HumanMessage(
        content=prompt
    )


    st.session_state[
        "messages"
    ].append(
        human_message
    )


    with st.chat_message("user"):

        st.markdown(
            prompt
        )


    # --------------------------------------------------------
    # RUN LANGGRAPH AGENT
    # --------------------------------------------------------

    try:

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "🤖 AgentForge is thinking..."
            ):

                # IMPORTANT:
                #
                # config is required because
                # backend.py uses SqliteSaver.
                #
                response = chatbot.invoke(
                    {
                        "messages": [
                            human_message
                        ]
                    },
                    config=config,
                )


            # ------------------------------------------------
            # EXTRACT RESPONSE
            # ------------------------------------------------

            answer = ""


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

                    # Find the last useful AI message

                    for msg in reversed(
                        response_messages
                    ):

                        if isinstance(
                            msg,
                            AIMessage,
                        ):

                            content = (
                                msg.content
                            )

                            if isinstance(
                                content,
                                str,
                            ) and content.strip():

                                answer = content

                                break


                        elif hasattr(
                            msg,
                            "content",
                        ):

                            content = (
                                msg.content
                            )

                            if isinstance(
                                content,
                                str,
                            ) and content.strip():

                                answer = content

                                break


            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            if not answer:

                answer = str(
                    response
                )


            # ------------------------------------------------
            # DISPLAY
            # ------------------------------------------------

            st.markdown(
                answer
            )


        # ----------------------------------------------------
        # SAVE ASSISTANT RESPONSE
        # ----------------------------------------------------

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

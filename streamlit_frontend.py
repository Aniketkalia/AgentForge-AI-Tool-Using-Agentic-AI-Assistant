import html
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
# 1. HANDLE GMAIL OAUTH CALLBACK FIRST
# ============================================================
#
# Google redirects to:
#
# https://your-app.streamlit.app/
#       ?code=XXXX
#       &state=XXXX
#
# This MUST be handled before the normal UI.
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Callback already saved the Gmail account/token
            # in persistent storage.

            st.session_state["gmail_connected"] = True

            # Force fresh page state
            st.rerun()

        else:

            # Do not rerun on failure.
            # The callback function should display the error.

            st.stop()

    except Exception as e:

        st.error(
            f"❌ Gmail callback error: {e}"
        )

        st.query_params.clear()

        st.stop()


# ============================================================
# 2. AGENTFORGE GOOGLE LOGIN
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
# 3. CURRENT AGENTFORGE USER
# ============================================================

user_email = st.user.email
user_id = st.user.get("sub")


if not user_id:

    st.error(
        "❌ Unable to identify the logged-in Google user."
    )

    st.stop()


# ============================================================
# 4. LOAD GMAIL CONNECTION FROM PERSISTENT STORAGE
# ============================================================
#
# DO NOT depend on:
#
# st.session_state["gmail_connected"]
#
# because Streamlit session state can disappear after refresh.
#
# Instead, ask gmail_auth.py every time.
# ============================================================

try:

    gmail_email = get_connected_gmail_email()

    gmail_connected = (
        gmail_email is not None
        and gmail_email != ""
    )

except Exception as e:

    gmail_connected = False
    gmail_email = None

    st.sidebar.error(
        f"Gmail status error: {e}"
    )


# ============================================================
# 5. SYNCHRONIZE SESSION CACHE
# ============================================================

st.session_state["gmail_connected"] = gmail_connected
st.session_state["gmail_email"] = gmail_email


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "🤖 AgentForge"
)


# ============================================================
# CURRENT USER
# ============================================================

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


# ============================================================
# CONNECTED
# ============================================================

if gmail_connected:

    st.sidebar.success(
        "✅ Gmail Connected"
    )

    st.sidebar.caption(
        gmail_email
    )

    st.sidebar.info(
        "Your agent can send email using this Gmail account."
    )


# ============================================================
# NOT CONNECTED
# ============================================================

else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    if st.sidebar.button(
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

                st.stop()


            # =================================================
            # SAME-TAB REDIRECT
            # =================================================
            #
            # No popup.
            # No new Chrome tab.
            #
            # The browser navigates the current page to Google.
            # =================================================

            safe_url = html.escape(
                auth_url,
                quote=True,
            )

            st.markdown(
                f"""
                <meta
                    http-equiv="refresh"
                    content="0;url={safe_url}"
                >
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <p>
                    Redirecting to Google Gmail authorization...
                </p>

                <p>
                    If you are not redirected automatically,
                    <a href="{safe_url}" target="_self">
                        click here to connect Gmail
                    </a>.
                </p>
                """,
                unsafe_allow_html=True,
            )

            st.stop()

        except Exception as e:

            st.error(
                f"❌ Gmail authorization error: {e}"
            )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown("---")


if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    # Clear only temporary UI state.
    #
    # DO NOT delete the persistent Gmail token here.
    # That allows the Gmail connection to survive
    # browser refresh/login sessions.

    st.session_state.pop(
        "gmail_connected",
        None,
    )

    st.session_state.pop(
        "gmail_email",
        None,
    )

    st.session_state.pop(
        "gmail_oauth_state",
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
        "Connect Gmail from the sidebar to allow "
        "the agent to send emails."
    )


# ============================================================
# CHAT HISTORY
# ============================================================

if "messages" not in st.session_state:

    st.session_state.messages = []


# ============================================================
# DISPLAY CHAT HISTORY
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

        with st.chat_message("assistant"):

            response = chatbot.invoke(
                {
                    "messages": [
                        human_message
                    ]
                }
            )


            # =================================================
            # EXTRACT FINAL RESPONSE
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


            # =================================================
            # DISPLAY RESPONSE
            # =================================================

            st.markdown(
                answer
            )


        # ====================================================
        # SAVE RESPONSE
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

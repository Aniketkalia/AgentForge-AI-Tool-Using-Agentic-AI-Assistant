# ============================================================
# streamlit_frontend.py
# ============================================================

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
#
# Google returns:
#
# ?code=XXXXX&state=XXXXX
#
# We process this BEFORE rendering the normal application.
#
# ============================================================

if (
    "code" in st.query_params
    or "error" in st.query_params
):

    callback_success = (
        handle_gmail_callback()
    )

    if callback_success:

        st.rerun()


# ============================================================
# AGENTFORGE GOOGLE LOGIN
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
        width="stretch",
    ):

        st.login()

    st.stop()


# ============================================================
# CURRENT USER
# ============================================================

user_email = st.user.email

user_id = st.user.get("sub")


# ============================================================
# LOAD GMAIL STATUS FROM SQLITE
# ============================================================
#
# DO NOT rely only on st.session_state.
#
# Streamlit session_state can disappear after refresh/new tab.
#
# Gmail token is loaded from SQLite instead.
#
# ============================================================

try:

    gmail_email = (
        get_connected_gmail_email()
    )

    gmail_connected = (
        gmail_email is not None
    )

except Exception as e:

    gmail_email = None

    gmail_connected = False

    st.warning(
        f"Gmail storage check failed: {e}"
    )


# ============================================================
# KEEP SESSION CACHE IN SYNC
# ============================================================

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
# GMAIL SECTION
# ============================================================

st.sidebar.markdown(
    "---"
)

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

    if gmail_email:

        st.sidebar.caption(
            gmail_email
        )

    # --------------------------------------------------------
    # Disconnect button
    # --------------------------------------------------------

    if st.sidebar.button(
        "🔌 Disconnect Gmail",
        width="stretch",
    ):

        disconnect_gmail()

        st.rerun()


# ============================================================
# NOT CONNECTED
# ============================================================

else:

    st.sidebar.info(
        "Gmail is not connected."
    )

    # --------------------------------------------------------
    # Generate OAuth URL
    #
    # IMPORTANT:
    #
    # st.link_button opens a NEW TAB.
    #
    # Therefore gmail_auth.py stores:
    #
    # - OAuth state
    # - user ID
    # - email
    # - PKCE code verifier
    #
    # in SQLite rather than session_state.
    #
    # --------------------------------------------------------

    try:

        auth_url = connect_gmail()

    except Exception as e:

        auth_url = None

        st.sidebar.error(
            f"OAuth setup error: {e}"
        )

    if auth_url:

        st.sidebar.link_button(
            "🔗 Connect My Gmail",
            auth_url,
            width="stretch",
            type="primary",
        )

        st.sidebar.caption(
            "Google will open in a new browser tab."
        )

    else:

        st.sidebar.error(
            "Unable to create Gmail authorization URL."
        )


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.markdown(
    "---"
)

if st.sidebar.button(
    "🚪 Logout",
    width="stretch",
):

    # Do NOT delete Gmail token here.
    #
    # Gmail connection belongs to the Google user
    # and is stored persistently in SQLite.
    #
    # If you want logout to also disconnect Gmail,
    # use the Disconnect Gmail button above.

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
# DISPLAY CHAT HISTORY
# ============================================================

for message in (
    st.session_state.messages
):

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

    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    human_message = HumanMessage(
        content=prompt
    )

    st.session_state.messages.append(
        human_message
    )

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

            response = chatbot.invoke(
                {
                    "messages": [
                        human_message
                    ]
                }
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


            # =================================================
            # SHOW RESPONSE
            # =================================================

            st.markdown(
                answer
            )


        # ----------------------------------------------------
        # SAVE ASSISTANT MESSAGE
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

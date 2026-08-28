import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback,
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
# GMAIL OAUTH CALLBACK
# ============================================================
#
# Gmail redirects back to:
#
# https://your-app.streamlit.app/
#     ?code=XXXX
#     &state=XXXX
#
# This MUST be processed before normal UI.
# ============================================================

if "code" in st.query_params:

    try:

        success = handle_gmail_callback()

        if success:

            # Save connection status
            st.session_state["gmail_connected"] = True

            # Get connected Gmail email
            try:

                email = get_connected_gmail_email()

                if email:

                    st.session_state["gmail_email"] = email

            except Exception:

                pass

            # Remove OAuth parameters
            st.query_params.clear()

            # Refresh app
            st.rerun()

    except Exception as e:

        st.error(
            f"❌ Gmail callback error: {e}"
        )

        st.query_params.clear()


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
# INITIALIZE SESSION VARIABLES
# ============================================================

if "gmail_connected" not in st.session_state:

    st.session_state["gmail_connected"] = False


if "gmail_email" not in st.session_state:

    st.session_state["gmail_email"] = None


if "messages" not in st.session_state:

    st.session_state["messages"] = []


# ============================================================
# CHECK GMAIL CONNECTION
# ============================================================

try:

    connected = is_gmail_connected()

    if connected:

        st.session_state["gmail_connected"] = True

        try:

            email = get_connected_gmail_email()

            if email:

                st.session_state["gmail_email"] = email

        except Exception:

            pass

except Exception:

    # Do NOT crash the whole application
    connected = st.session_state.get(
        "gmail_connected",
        False
    )


gmail_connected = st.session_state.get(
    "gmail_connected",
    False
)

gmail_email = st.session_state.get(
    "gmail_email",
    None
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

    if gmail_email:

        st.sidebar.caption(
            gmail_email
        )


# ============================================================
# NOT CONNECTED
# ============================================================

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

            # Create Google OAuth URL
            auth_url = connect_gmail()


            if not auth_url:

                st.sidebar.error(
                    "Unable to create Gmail authorization URL."
                )

            else:

                # ====================================================
                # OPEN GOOGLE IN NEW TAB
                # ====================================================

                st.components.v1.html(
                    f"""
                    <script>

                        // Gmail Google OAuth URL
                        const authUrl = {auth_url!r};

                        // Open Google authorization in new tab
                        const newWindow = window.open(
                            authUrl,
                            "_blank"
                        );

                        // Check popup blocking
                        if (!newWindow) {{

                            alert(
                                "Chrome blocked the new tab. " +
                                "Please allow popups for this Streamlit site."
                            );

                        }}

                    </script>
                    """,
                    height=0,
                )


                st.sidebar.success(
                    "✅ Google opened in a new tab."
                )


                st.info(
                    """
                    ### 📧 Connect Gmail

                    1. Google authorization has opened in a new tab.
                    2. Select your Google account.
                    3. Click **Allow**.
                    4. Google will redirect that tab back to AgentForge.
                    5. Gmail will then show as connected.

                    **Keep this AgentForge tab open.**
                    """
                )


        except Exception as e:

            st.sidebar.error(
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

    # Clear temporary Gmail session data

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

    st.session_state.pop(
        "gmail_oauth_in_progress",
        None,
    )

    st.session_state.pop(
        "messages",
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
        "Connect Gmail from the sidebar."
    )


# ============================================================
# CHAT HISTORY
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
            # DISPLAY ANSWER
            # =================================================

            st.markdown(
                answer
            )


        # ====================================================
        # SAVE ANSWER
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

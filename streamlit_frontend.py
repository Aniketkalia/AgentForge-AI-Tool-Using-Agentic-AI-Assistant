# ============================================================
# streamlit_frontend.py
# AgentForge AI
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
    is_gmail_connected,
    disconnect_gmail,
    get_gmail_service,
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
# We process login first so we have the user email ready for the callback

if not st.user.is_logged_in:
    st.title("🤖 AgentForge AI")
    st.subheader("Tool-Using Agentic AI Assistant")
    st.write("Login with Google to continue.")

    if st.button("🔐 Login with Google", use_container_width=True, type="primary"):
        st.login()
    st.stop()

user_email = st.user.email
user_id = st.user.get("sub")

if not user_id:
    st.error("❌ Unable to identify logged-in Google user.")
    st.stop()

# ============================================================
# SESSION STATE
# ============================================================

if "gmail_auth_url" not in st.session_state:
    st.session_state.gmail_auth_url = None

if "gmail_connected" not in st.session_state:
    st.session_state.gmail_connected = False

if "gmail_email" not in st.session_state:
    st.session_state.gmail_email = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# ============================================================
# GMAIL CALLBACK
# ============================================================

if "code" in st.query_params:
    try:
        success = handle_gmail_callback(user_email)
        if success:
            email = get_connected_gmail_email()
            st.session_state.gmail_email = email
            st.session_state.gmail_connected = bool(email)
            st.query_params.clear()
            st.rerun()
    except Exception as e:
        st.error(f"❌ Gmail callback error: {e}")
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.stop()


# ============================================================
# LANGGRAPH THREAD
# ============================================================

thread_id = f"agentforge-user-{user_id}"
config = {"configurable": {"thread_id": thread_id}}

gmail_email = None
gmail_connected = False
gmail_error = None

try:
    gmail_email = get_connected_gmail_email()
    gmail_connected = (gmail_email is not None and gmail_email != "")
except Exception as e:
    gmail_error = str(e)

st.session_state.gmail_connected = gmail_connected
st.session_state.gmail_email = gmail_email


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🤖 AgentForge")
    st.caption("LangGraph • Groq • Gmail • Web Search • Tools")
    st.divider()

    st.success(f"👤 {user_email}")
    st.divider()

    st.subheader("📧 Gmail")

    if gmail_connected:
        st.success("✅ Gmail Connected")
        st.markdown(f"**Connected account:**  \n{gmail_email}")
        st.caption("AgentForge can send emails using this Gmail account.")
        st.divider()

        if st.button("🔄 Refresh Gmail", use_container_width=True):
            st.rerun()

        if st.button("🔌 Disconnect Gmail", use_container_width=True):
            try:
                disconnect_gmail(user_id)
                st.session_state.gmail_connected = False
                st.session_state.gmail_email = None
                st.session_state.gmail_auth_url = None
                st.success("Gmail disconnected.")
                st.rerun()
            except Exception as e:
                st.error(f"Disconnect failed: {e}")
    else:
        st.warning("📧 Gmail Not Connected")
        st.caption("Connect your Gmail to allow AgentForge to send emails.")

        if st.button("🔗 Connect My Gmail", use_container_width=True, type="primary"):
            try:
                auth_url = connect_gmail(user_email)
                if auth_url:
                    st.session_state.gmail_auth_url = auth_url
                    st.rerun()
                else:
                    st.error("Unable to create Gmail authorization URL.")
            except Exception as e:
                st.error(f"❌ Gmail authorization error: {e}")

        auth_url = st.session_state.gmail_auth_url

        if auth_url:
            safe_url = html.escape(auth_url, quote=True)

            st.markdown(
                f"""
                <a href="{safe_url}" target="_blank" style="display:block; width:100%; padding:0.75rem 1rem; background:#FF4B4B; color:white; text-align:center; text-decoration:none; border-radius:0.5rem; font-weight:600; margin-top:0.75rem; box-sizing:border-box;">
                    🔐 Continue with Google
                </a>
                """,
                unsafe_allow_html=True,
            )

            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.gmail_auth_url = None
                st.rerun()

    if gmail_error:
        st.error(f"Gmail status error: {gmail_error}")

    st.divider()
    if st.button("🆕 New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

    with st.expander("🔧 Debug"):
        st.write("AgentForge User ID:", user_id)
        st.write("AgentForge Email:", user_email)
        st.write("Gmail Connected:", gmail_connected)
        st.write("Gmail Account:", gmail_email)
        st.write("LangGraph Thread:", thread_id)

    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.messages = []
        st.session_state.gmail_auth_url = None
        st.logout()

# ============================================================
# MAIN PAGE
# ============================================================

st.title("🤖 AgentForge AI")
st.caption(f"Logged in as: {user_email}")

if gmail_connected:
    st.success(f"📧 Gmail connected: {gmail_email}")
else:
    st.info("📧 Gmail is not connected. Connect Gmail from the sidebar to send emails.")

for message in st.session_state.messages:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.markdown(message.content)
    elif isinstance(message, AIMessage):
        content = message.content
        if isinstance(content, str) and content.strip():
            with st.chat_message("assistant"):
                st.markdown(content)

if not st.session_state.messages:
    st.info("👋 Welcome to AgentForge AI!")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🧮 Calculator**\n`Calculate 125 * 48`")
    with col2:
        st.markdown("**📧 Gmail**\n`Send an email to someone@example.com`")
    with col3:
        st.markdown("**🌐 Web Search**\n`Search the latest AI news`")


prompt = st.chat_input("Ask me anything...")

if prompt:
    human_message = HumanMessage(content=prompt)
    st.session_state.messages.append(human_message)

    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            with st.spinner("🤖 AgentForge is thinking..."):
                response = chatbot.invoke(
                    {"messages": st.session_state.messages},
                    config=config
                )

            answer = ""
            if isinstance(response, dict):
                response_messages = response.get("messages", [])
                for msg in reversed(response_messages):
                    content = getattr(msg, "content", None)
                    if isinstance(content, str) and content.strip():
                        answer = content
                        break

            if not answer:
                answer = str(response)

            st.markdown(answer)

        st.session_state.messages.append(AIMessage(content=answer))

    except Exception as e:
        st.error(f"❌ Agent error: {e}")

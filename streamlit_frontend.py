import uuid
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

st.set_page_config(
    page_title="AgentForge AI",
    page_icon="🤖",
    layout="wide"
)

# ============================================================
# GOOGLE LOGIN
# ============================================================

import streamlit as st

if not st.user.is_logged_in:
    st.title("🤖 AgentForge")
    st.subheader("Tool-Using Agentic AI Assistant")

    if st.button("🔐 Login with Google"):
        st.login()

    st.stop()

current_user = st.user.email

st.success(f"Logged in as {current_user}")


# ============================================================
# BACKEND — LOAD ONLY AFTER LOGIN
# ============================================================

from backend import chatbot, retrieve

# ============================================================
# LOGGED-IN USER
# ============================================================

st.sidebar.success(f"Logged in as {st.user.email}")

if st.sidebar.button("Logout"):
    st.logout()
# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="LangGraph AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# SESSION STATE
# ============================================================

def generate_thread_id() -> str:
    """Generate a unique conversation/thread ID."""
    return str(uuid.uuid4())


def initialize_session_state():
    """Initialize Streamlit session state."""

    if "message_history" not in st.session_state:
        st.session_state["message_history"] = []

    if "thread_id" not in st.session_state:
        st.session_state["thread_id"] = generate_thread_id()

    if "chat_threads" not in st.session_state:
        st.session_state["chat_threads"] = retrieve()

    add_thread(st.session_state["thread_id"])


def add_thread(thread_id: str):
    """Add a thread to the session thread list if it doesn't exist."""

    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)


# ============================================================
# CHAT MANAGEMENT
# ============================================================

def reset_chat():
    """Create a new conversation."""

    thread_id = generate_thread_id()

    st.session_state["thread_id"] = thread_id
    st.session_state["message_history"] = []

    add_thread(thread_id)


def load_conversation(thread_id: str):
    """Load messages from LangGraph checkpoint."""

    try:

        state = chatbot.get_state(
            config={
                "configurable": {
                    "thread_id": thread_id
                }
            }
        )

        return state.values.get("messages", [])

    except Exception as e:

        st.error(
            f"Unable to load conversation: {e}"
        )

        return []


def switch_conversation(thread_id: str):
    """Switch to an existing conversation."""

    st.session_state["thread_id"] = thread_id

    messages = load_conversation(thread_id)

    history = []

    for message in messages:

        if isinstance(message, HumanMessage):

            role = "user"

        elif isinstance(message, AIMessage):

            role = "assistant"

        else:

            # Ignore tool/system messages in UI
            continue

        # AI messages can sometimes contain non-string content
        content = message.content

        if isinstance(content, str) and content.strip():

            history.append(
                {
                    "role": role,
                    "content": content
                }
            )

    st.session_state["message_history"] = history


# ============================================================
# INITIALIZE
# ============================================================

initialize_session_state()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 AI Assistant")

    st.caption(
        "LangGraph • Groq • Gmail • Web Search • Tools"
    )

    st.divider()

    # New chat button
    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        reset_chat()
        st.rerun()

    st.divider()

    st.subheader("💬 Conversations")

    threads = st.session_state["chat_threads"]

    if not threads:

        st.caption(
            "No previous conversations."
        )

    else:

        for thread_id in reversed(threads):

            # Shorter ID for cleaner UI
            display_id = str(thread_id)[:8]

            is_current = (
                str(thread_id)
                == str(st.session_state["thread_id"])
            )

            button_label = (
                f"🟢 {display_id}"
                if is_current
                else f"💬 {display_id}"
            )

            if st.button(
                button_label,
                key=f"thread_{thread_id}",
                use_container_width=True
            ):

                switch_conversation(thread_id)
                st.rerun()

    st.divider()

    st.caption(
        "Powered by LangGraph + Groq"
    )


# ============================================================
# MAIN HEADER
# ============================================================

st.title("🤖 LangGraph AI Assistant")

st.markdown(
    """
Ask questions, perform calculations, search the web,
check stock prices, or send emails using natural language.
"""
)


# ============================================================
# CURRENT THREAD
# ============================================================

with st.expander(
    "Conversation Details",
    expanded=False
):

    st.write(
        f"**Thread ID:** `{st.session_state['thread_id']}`"
    )

    st.write(
        f"**Messages:** "
        f"{len(st.session_state['message_history'])}"
    )


# ============================================================
# DISPLAY CHAT HISTORY
# ============================================================

for message in st.session_state["message_history"]:

    role = message["role"]
    content = message["content"]

    with st.chat_message(role):

        st.markdown(content)


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state["message_history"]:

    st.info(
        "👋 Welcome! Ask me anything or try one of these:"
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
            **📈 Stock Price**

            `What is the latest AAPL price?`
            """
        )

    with col3:

        st.markdown(
            """
            **🌐 Web Search**

            `Search the web for the latest AI news`
            """
        )


# ============================================================
# CHAT INPUT
# ============================================================

user_input = st.chat_input(
    "Ask me anything..."
)


# ============================================================
# PROCESS USER MESSAGE
# ============================================================

if user_input:

    # --------------------------------------------------------
    # Add user message to UI history
    # --------------------------------------------------------

    st.session_state["message_history"].append(
        {
            "role": "user",
            "content": user_input
        }
    )

    # --------------------------------------------------------
    # Display user message
    # --------------------------------------------------------

    with st.chat_message("user"):

        st.markdown(user_input)

    # --------------------------------------------------------
    # LangGraph configuration
    # --------------------------------------------------------

    config = {
        "configurable": {
            "thread_id": st.session_state["thread_id"]
        }
    }

    # --------------------------------------------------------
    # Stream assistant response
    # --------------------------------------------------------

    with st.chat_message("assistant"):

        response_container = st.empty()

        full_response = ""

        try:

            for message_chunk, metadata in chatbot.stream(
                {
                    "messages": [
                        HumanMessage(
                            content=user_input
                        )
                    ]
                },
                config=config,
                stream_mode="messages"
            ):

                # Only display AI messages
                if isinstance(
                    message_chunk,
                    AIMessage
                ):

                    content = message_chunk.content

                    # Make sure content is text
                    if isinstance(
                        content,
                        str
                    ):

                        full_response += content

                        response_container.markdown(
                            full_response
                        )

        except Exception as e:

            full_response = (
                f"⚠️ Sorry, something went wrong: {e}"
            )

            response_container.error(
                full_response
            )

    # --------------------------------------------------------
    # Save assistant response
    # --------------------------------------------------------

    if full_response:

        st.session_state["message_history"].append(
            {
                "role": "assistant",
                "content": full_response
            }
        )

    st.rerun()

import uuid
import streamlit as st

from langchain_core.messages import (
    HumanMessage,
    AIMessage
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AgentForge AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# GOOGLE LOGIN
# ============================================================

if not st.user.is_logged_in:

    st.title("🤖 AgentForge")

    st.subheader(
        "Tool-Using Agentic AI Assistant"
    )

    st.write(
        "Login with Google to use AgentForge."
    )

    if st.button(
        "🔐 Login with Google",
        type="primary"
    ):

        st.login()

    st.stop()


# ============================================================
# CURRENT USER
# ============================================================

current_user = st.user.email

user_id = st.user.get("sub")

if not user_id:

    st.error(
        "Unable to identify the logged-in Google user."
    )

    st.stop()


# ============================================================
# GMAIL OAUTH
# ============================================================

from gmail_auth import (
    connect_gmail,
    handle_gmail_callback
)


# ------------------------------------------------------------
# IMPORTANT:
# Gmail callback comes back to "/" instead of "/oauth2callback"
# so Streamlit's own OAuth callback does not conflict with it.
# ------------------------------------------------------------

if "code" in st.query_params:

    gmail_success = handle_gmail_callback()

    if gmail_success:

        st.success(
            "✅ Gmail connected successfully!"
        )

        st.rerun()

    st.stop()


# ============================================================
# GMAIL TOKEN STORAGE
# ============================================================

if "gmail_tokens" not in st.session_state:

    st.session_state[
        "gmail_tokens"
    ] = {}


gmail_tokens = st.session_state[
    "gmail_tokens"
]


gmail_connected = (
    user_id
    in gmail_tokens
)


# ============================================================
# BACKEND
# ============================================================

from backend import (
    chatbot,
    retrieve
)


# ============================================================
# SESSION STATE
# ============================================================

def generate_thread_id():

    return str(uuid.uuid4())


def add_thread(thread_id):

    if (
        thread_id
        not in st.session_state[
            "chat_threads"
        ]
    ):

        st.session_state[
            "chat_threads"
        ].append(
            thread_id
        )


def initialize_session_state():

    if "message_history" not in st.session_state:

        st.session_state[
            "message_history"
        ] = []


    if "thread_id" not in st.session_state:

        st.session_state[
            "thread_id"
        ] = generate_thread_id()


    if "chat_threads" not in st.session_state:

        try:

            st.session_state[
                "chat_threads"
            ] = retrieve()

        except Exception:

            st.session_state[
                "chat_threads"
            ] = []


    add_thread(
        st.session_state[
            "thread_id"
        ]
    )


def reset_chat():

    thread_id = generate_thread_id()

    st.session_state[
        "thread_id"
    ] = thread_id

    st.session_state[
        "message_history"
    ] = []

    add_thread(thread_id)


def load_conversation(thread_id):

    try:

        state = chatbot.get_state(
            config={
                "configurable": {
                    "thread_id": thread_id
                }
            }
        )

        return state.values.get(
            "messages",
            []
        )

    except Exception as e:

        st.error(
            f"Unable to load conversation: {e}"
        )

        return []


def switch_conversation(thread_id):

    st.session_state[
        "thread_id"
    ] = thread_id

    messages = load_conversation(
        thread_id
    )

    history = []

    for message in messages:

        if isinstance(
            message,
            HumanMessage
        ):

            role = "user"

        elif isinstance(
            message,
            AIMessage
        ):

            role = "assistant"

        else:

            continue

        content = message.content

        if (
            isinstance(content, str)
            and content.strip()
        ):

            history.append(
                {
                    "role": role,
                    "content": content
                }
            )

    st.session_state[
        "message_history"
    ] = history


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

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    st.success(
        f"👤 {current_user}"
    )

    st.divider()

    # --------------------------------------------------------
    # GMAIL
    # --------------------------------------------------------

    if gmail_connected:

        st.success(
            "📧 Gmail Connected"
        )

        gmail_email = st.session_state.get(
            "gmail_email",
            current_user
        )

        st.caption(
            f"Sending as: {gmail_email}"
        )

    else:

        st.warning(
            "📧 Gmail Not Connected"
        )

        st.caption(
            "Connect your Gmail before "
            "sending emails."
        )

        if st.button(
            "🔗 Connect My Gmail",
            use_container_width=True
        ):

            gmail_url = connect_gmail()

            st.markdown(
                f"""
                <meta
                    http-equiv="refresh"
                    content="0;url={gmail_url}"
                />
                """,
                unsafe_allow_html=True
            )

            st.stop()

    st.divider()

    # --------------------------------------------------------
    # NEW CHAT
    # --------------------------------------------------------

    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        reset_chat()

        st.rerun()

    st.divider()

    # --------------------------------------------------------
    # CONVERSATIONS
    # --------------------------------------------------------

    st.subheader(
        "💬 Conversations"
    )

    threads = st.session_state[
        "chat_threads"
    ]

    if not threads:

        st.caption(
            "No previous conversations."
        )

    else:

        for thread_id in reversed(
            threads
        ):

            display_id = str(
                thread_id
            )[:8]

            is_current = (
                str(thread_id)
                ==
                str(
                    st.session_state[
                        "thread_id"
                    ]
                )
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

                switch_conversation(
                    thread_id
                )

                st.rerun()

    st.divider()

    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    if st.button(
        "🚪 Logout",
        use_container_width=True
    ):

        st.logout()

    st.caption(
        "Powered by LangGraph + Groq"
    )


# ============================================================
# MAIN HEADER
# ============================================================

st.title(
    "🤖 LangGraph AI Assistant"
)

st.markdown(
    """
Ask questions, perform calculations,
search the web, check stock prices,
or send emails using natural language.
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
        f"**Thread ID:** "
        f"`{st.session_state['thread_id']}`"
    )

    st.write(
        f"**Messages:** "
        f"{len(st.session_state['message_history'])}"
    )


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state[
    "message_history"
]:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state[
    "message_history"
]:

    st.info(
        "👋 Welcome! Ask me anything or "
        "try one of these:"
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

    st.session_state[
        "message_history"
    ].append(
        {
            "role": "user",
            "content": user_input
        }
    )

    with st.chat_message("user"):

        st.markdown(
            user_input
        )


    config = {
        "configurable": {
            "thread_id":
                st.session_state[
                    "thread_id"
                ]
        }
    }


    with st.chat_message("assistant"):

        response_container = st.empty()

        full_response = ""

        try:

            for (
                message_chunk,
                metadata
            ) in chatbot.stream(

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

                if isinstance(
                    message_chunk,
                    AIMessage
                ):

                    content = (
                        message_chunk.content
                    )

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


    if full_response:

        st.session_state[
            "message_history"
        ].append(
            {
                "role": "assistant",
                "content": full_response
            }
        )

    st.rerun()

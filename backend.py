# ============================================================
# AgentForge AI - backend.py
# ============================================================

import os
import base64
import requests

from email.message import EmailMessage
from typing import TypedDict, Annotated

import streamlit as st
from dotenv import load_dotenv

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
)

from langchain_core.tools import tool
from langchain_groq import ChatGroq

from langchain_community.tools import DuckDuckGoSearchRun

from langgraph.graph import (
    StateGraph,
    START,
)

from langgraph.graph.message import add_messages

from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
)

# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# STREAMLIT SECRETS
# ============================================================

try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except Exception:
    pass


# ============================================================
# ALPHA VANTAGE
# ============================================================

try:
    ALPHA_VANTAGE_API_KEY = st.secrets.get(
        "ALPHA_VANTAGE_API_KEY",
        os.getenv("ALPHA_VANTAGE_API_KEY"),
    )
except Exception:
    ALPHA_VANTAGE_API_KEY = os.getenv(
        "ALPHA_VANTAGE_API_KEY"
    )


# ============================================================
# GMAIL
#
# IMPORTANT:
# Gmail authentication is handled ONLY by gmail_auth.py
# ============================================================

try:
    from gmail_auth import get_gmail_service
except ImportError as e:
    raise ImportError(
        "Could not import get_gmail_service from gmail_auth.py. "
        "Make sure gmail_auth.py is in the same project directory."
    ) from e


# ============================================================
# LLM
# ============================================================

model = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.3,
)


# ============================================================
# SEND EMAIL TOOL
# ============================================================

@tool
def send_email(
    to: str,
    subject: str,
    body: str,
) -> str:
    """
    Send an email using the user's connected Gmail account.
    """

    try:
        # ----------------------------------------------------
        # GET GMAIL SERVICE FROM gmail_auth.py
        # ----------------------------------------------------

        service = get_gmail_service()

        if service is None:
            return (
                "EMAIL_FAILED: Gmail is not connected. "
                "Please connect Gmail first."
            )

        # ----------------------------------------------------
        # CREATE EMAIL
        # ----------------------------------------------------

        message = EmailMessage()

        message["To"] = to
        message["Subject"] = subject

        message.set_content(body)

        # ----------------------------------------------------
        # ENCODE EMAIL
        # ----------------------------------------------------

        encoded_message = (
            base64.urlsafe_b64encode(
                message.as_bytes()
            )
            .decode("utf-8")
        )

        request_body = {
            "raw": encoded_message
        }

        # ----------------------------------------------------
        # SEND THROUGH GMAIL API
        # ----------------------------------------------------

        response = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=request_body,
            )
            .execute()
        )

        message_id = response.get(
            "id",
            "unknown",
        )

        # ----------------------------------------------------
        # GET CONNECTED USER
        # ----------------------------------------------------

        try:
            if st.user.is_logged_in:
                sender = st.user.email
            else:
                sender = "connected Gmail account"
        except Exception:
            sender = "connected Gmail account"

        return (
            "EMAIL_SENT: "
            f"Email successfully sent from {sender} "
            f"to {to}. "
            f"Message ID: {message_id}"
        )

    except Exception as e:

        return (
            "EMAIL_FAILED: "
            f"{str(e)}"
        )


# ============================================================
# WEB SEARCH
# ============================================================

search_tool = DuckDuckGoSearchRun(
    region="us-en"
)


# ============================================================
# CALCULATOR
# ============================================================

@tool
def calculator(
    first_num: float,
    second_num: float,
    operation: str,
) -> dict:
    """
    Perform basic arithmetic.

    Supported operations:
    add
    sub
    mul
    div
    """

    try:

        operation = (
            operation
            .lower()
            .strip()
        )

        if operation == "add":

            result = (
                first_num +
                second_num
            )

        elif operation == "sub":

            result = (
                first_num -
                second_num
            )

        elif operation == "mul":

            result = (
                first_num *
                second_num
            )

        elif operation == "div":

            if second_num == 0:

                return {
                    "error":
                    "Division by zero is not allowed."
                }

            result = (
                first_num /
                second_num
            )

        else:

            return {
                "error":
                "Use add, sub, mul, or div."
            }

        return {
            "first_num": first_num,
            "second_num": second_num,
            "operation": operation,
            "result": result,
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# STOCK PRICE
# ============================================================

@tool
def get_stock_price(
    symbol: str,
) -> dict:
    """
    Get the latest stock price using Alpha Vantage.
    """

    try:

        if not ALPHA_VANTAGE_API_KEY:

            return {
                "error":
                "Alpha Vantage API key is not configured."
            }

        symbol = (
            symbol
            .upper()
            .strip()
        )

        url = (
            "https://www.alphavantage.co/query"
            "?function=GLOBAL_QUOTE"
            f"&symbol={symbol}"
            f"&apikey={ALPHA_VANTAGE_API_KEY}"
        )

        response = requests.get(
            url,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        return data

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# TOOLS
# ============================================================

tools = [
    get_stock_price,
    search_tool,
    calculator,
    send_email,
]


# ============================================================
# LLM WITH TOOLS
# ============================================================

llm_with_tools = model.bind_tools(
    tools
)


# ============================================================
# LANGGRAPH STATE
# ============================================================

class ChatState(TypedDict):

    messages: Annotated[
        list[BaseMessage],
        add_messages,
    ]


# ============================================================
# CHAT NODE
# ============================================================

def chat_node(
    state: ChatState,
):

    system_instruction = """
You are AgentForge AI, a tool-using AI assistant.

You can use the following tools:

1. send_email
   Sends an email through the user's connected Gmail.

2. calculator
   Performs arithmetic calculations.

3. get_stock_price
   Gets current stock prices.

4. duckduckgo_search
   Searches the web.

============================================================
EMAIL RULES
============================================================

1. If the user explicitly asks you to send an email,
   ALWAYS call send_email.

2. NEVER claim that an email was sent unless
   send_email returns EMAIL_SENT.

3. If the user gives:
   - recipient
   - subject
   - body

   call send_email.

4. If recipient is missing,
   ask for the recipient.

5. If subject is missing,
   ask for the subject.

6. If body is missing,
   ask for the body.

7. If send_email returns EMAIL_FAILED,
   clearly tell the user that sending failed.

8. NEVER fabricate successful email delivery.

9. If the user confirms a recipient and then provides
   subject/body, use the confirmed recipient.

10. Do not ask again for information that the user
    already provided in the conversation.

============================================================
CALCULATOR
============================================================

Use calculator for arithmetic when appropriate.

============================================================
STOCK
============================================================

Use get_stock_price for current stock prices.

============================================================
WEB SEARCH
============================================================

Use DuckDuckGo search for current information.

============================================================
GENERAL
============================================================

Always explain tool results clearly.

Be concise and helpful.
"""

    messages = state["messages"]

    messages_with_system = [
        SystemMessage(
            content=system_instruction
        ),
        *messages,
    ]

    response = llm_with_tools.invoke(
        messages_with_system
    )

    return {
        "messages": [response]
    }


# ============================================================
# TOOL NODE
# ============================================================

tool_node = ToolNode(
    tools
)


# ============================================================
# GRAPH
# ============================================================

graph = StateGraph(
    ChatState
)


# ============================================================
# ADD NODES
# ============================================================

graph.add_node(
    "chat_node",
    chat_node
)

graph.add_node(
    "tools",
    tool_node
)


# ============================================================
# EDGES
# ============================================================

graph.add_edge(
    START,
    "chat_node"
)

graph.add_conditional_edges(
    "chat_node",
    tools_condition
)

graph.add_edge(
    "tools",
    "chat_node"
)


# ============================================================
# COMPILE GRAPH
#
# IMPORTANT:
# NO SQLITE CHECKPOINTER HERE.
#
# This prevents:
# "Checkpointer requires one or more of the following
# configurable keys: thread_id..."
# ============================================================

chatbot = graph.compile()


# ============================================================
# RETRIEVE
#
# Kept for frontend compatibility if your frontend imports
# retrieve().
# ============================================================

def retrieve():

    """
    Compatibility function.

    The current backend does not use a persistent
    LangGraph SQLite checkpointer.
    """

    return []


# ============================================================
# HELPER FUNCTION
# ============================================================

def invoke_agent(
    messages,
):
    """
    Simple helper for Streamlit frontend.

    No thread_id/config is required because the graph
    does not use a checkpointer.
    """

    return chatbot.invoke(
        {
            "messages": messages
        }
    )


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "chatbot",
    "invoke_agent",
    "send_email",
    "calculator",
    "get_stock_price",
    "search_tool",
    "retrieve",
]

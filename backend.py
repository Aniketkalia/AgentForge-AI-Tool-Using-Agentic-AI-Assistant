# backend.py

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

from langchain_community.tools import (
    DuckDuckGoSearchRun
)

from langgraph.graph import (
    StateGraph,
    START,
)

from langgraph.graph.message import add_messages

from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
)

from langgraph.checkpoint.sqlite import (
    SqliteSaver
)

import sqlite3


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# STREAMLIT SECRETS
# ============================================================

if "GROQ_API_KEY" in st.secrets:

    os.environ["GROQ_API_KEY"] = (
        st.secrets["GROQ_API_KEY"]
    )


ALPHA_VANTAGE_API_KEY = st.secrets.get(
    "ALPHA_VANTAGE_API_KEY",
    os.getenv("ALPHA_VANTAGE_API_KEY")
)


# ============================================================
# GMAIL SERVICE
#
# IMPORTANT:
# Use gmail_auth.py.
#
# DO NOT create another Gmail authentication system here.
# ============================================================

from gmail_auth import (
    get_gmail_service,
)


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
    Send an email using the currently
    connected Gmail account.
    """

    try:

        # ----------------------------------------------------
        # GET CURRENT USER'S GMAIL SERVICE
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
        # ENCODE
        # ----------------------------------------------------

        encoded_message = (
            base64.urlsafe_b64encode(
                message.as_bytes()
            )
            .decode()
        )

        request_body = {
            "raw": encoded_message
        }

        # ----------------------------------------------------
        # SEND
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
            "unknown"
        )

        sender = (
            st.user.email
            if st.user.is_logged_in
            else "Gmail account"
        )

        return (
            "EMAIL_SENT: "
            f"Email successfully sent from "
            f"{sender} to {to}. "
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

    Supported:
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
                first_num
                +
                second_num
            )

        elif operation == "sub":

            result = (
                first_num
                -
                second_num
            )

        elif operation == "mul":

            result = (
                first_num
                *
                second_num
            )

        elif operation == "div":

            if second_num == 0:

                return {
                    "error":
                    "Division by zero is not allowed."
                }

            result = (
                first_num
                /
                second_num
            )

        else:

            return {
                "error":
                "Use add, sub, mul, or div."
            }

        return {

            "first_num":
                first_num,

            "second_num":
                second_num,

            "operation":
                operation,

            "result":
                result,
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
    Get latest stock price.
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

        return response.json()

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
    state: ChatState
):

    system_instruction = """
You are AgentForge AI, a tool-using AI assistant.

Available tools:

1. send_email
   Sends an email through the user's connected Gmail.

2. calculator
   Performs arithmetic.

3. get_stock_price
   Gets current stock prices.

4. duckduckgo_search
   Searches the web.

IMPORTANT EMAIL RULES:

1. If the user explicitly asks you to send an email,
   ALWAYS call send_email.

2. NEVER say an email was sent unless
   send_email returns EMAIL_SENT.

3. If the user gives a recipient, subject,
   and body, call send_email.

4. If the recipient is missing,
   ask for the recipient.

5. If subject is missing,
   ask for the subject.

6. If body is missing,
   ask for the body.

7. If the send_email tool returns EMAIL_FAILED,
   clearly tell the user that sending failed.

8. Never fabricate successful email delivery.

CALCULATOR:

Use calculator for arithmetic when appropriate.

STOCK:

Use get_stock_price for current stock prices.

WEB:

Use web search for current information.

Always explain tool results clearly.
"""

    messages = state["messages"]

    messages_with_system = [

        SystemMessage(
            content=system_instruction
        ),

        *messages,
    ]

    response = (
        llm_with_tools.invoke(
            messages_with_system
        )
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


graph.add_node(
    "chat_node",
    chat_node
)


graph.add_node(
    "tools",
    tool_node
)


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
# SQLITE CHECKPOINTER
# ============================================================

conn = sqlite3.connect(

    "chatbot.db",

    check_same_thread=False,
)


checkpointer = SqliteSaver(
    conn=conn
)


# ============================================================
# COMPILE
# ============================================================

chatbot = graph.compile(
    checkpointer=checkpointer
)


# ============================================================
# RETRIEVE THREADS
# ============================================================

def retrieve():

    all_threads = set()

    try:

        for checkpoint in checkpointer.list(None):

            config = checkpoint.config

            configurable = config.get(
                "configurable",
                {}
            )

            thread_id = configurable.get(
                "thread_id"
            )

            if thread_id:

                all_threads.add(
                    thread_id
                )

    except Exception as e:

        print(
            f"Thread retrieval error: {e}"
        )

    return list(
        all_threads
    )

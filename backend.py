import os
import json
import base64
import sqlite3
import requests
from email.message import EmailMessage
from typing import TypedDict, Annotated

import streamlit as st
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_community.tools import DuckDuckGoSearchRun

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


# ============================================================
# STREAMLIT SECRETS
# ============================================================

# Groq API key
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]


# Alpha Vantage API key
ALPHA_VANTAGE_API_KEY = st.secrets.get(
    "ALPHA_VANTAGE_API_KEY",
    os.getenv("ALPHA_VANTAGE_API_KEY")
)


# ============================================================
# LLM
# ============================================================

model = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.3
)


# ============================================================
# GMAIL SERVICE
# ============================================================

# ============================================================
# GMAIL SERVICE — CURRENT LOGGED-IN USER
# ============================================================

def get_gmail_service():

    try:
        # Make sure user is logged in
        if not st.user.is_logged_in:
            raise Exception("Please login with Google first.")

        # Unique Google user ID
        user_id = st.user.get("sub")

        if not user_id:
            raise Exception("Unable to identify the logged-in user.")

        # Get Gmail token for THIS user
        gmail_tokens = st.session_state.get("gmail_tokens", {})

        token_data = gmail_tokens.get(user_id)

        if not token_data:
            raise Exception(
                "Gmail is not connected for this account. "
                "Please connect your Gmail first."
            )

        creds = Credentials.from_authorized_user_info(
            token_data,
            SCOPES
        )

        # Refresh expired token
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

            # Save updated token
            gmail_tokens[user_id] = json.loads(
                creds.to_json()
            )

            st.session_state["gmail_tokens"] = gmail_tokens

        if not creds.valid:
            raise Exception(
                "Gmail credentials are invalid or expired. "
                "Please reconnect Gmail."
            )

        service = build(
            "gmail",
            "v1",
            credentials=creds,
            cache_discovery=False
        )

        return service

    except Exception as e:
        raise Exception(
            f"Gmail authentication error: {str(e)}"
        )


# ============================================================
# SEND EMAIL TOOL
# ============================================================

@tool
def send_email(
    to: str,
    subject: str,
    body: str
) -> str:
    """
    Send an email using the currently logged-in user's Gmail.
    """

    try:

        service = get_gmail_service()

        message = EmailMessage()

        message["To"] = to
        message["Subject"] = subject

        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        request_body = {
            "raw": encoded_message
        }

        response = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=request_body
            )
            .execute()
        )

        return (
            f"Email sent successfully from "
            f"{st.user.email}. "
            f"Message ID: {response['id']}"
        )

    except Exception as e:

        return f"Failed to send email: {str(e)}"


# ============================================================
# WEB SEARCH TOOL
# ============================================================

search_tool = DuckDuckGoSearchRun(
    region="us-en"
)


# ============================================================
# CALCULATOR TOOL
# ============================================================

@tool
def calculator(
    first_num: float,
    second_num: float,
    operation: str
) -> dict:
    """
    Perform basic arithmetic operations.

    Supported operations:
    add
    sub
    mul
    div
    """

    try:

        operation = operation.lower().strip()

        if operation == "add":

            result = first_num + second_num

        elif operation == "sub":

            result = first_num - second_num

        elif operation == "mul":

            result = first_num * second_num

        elif operation == "div":

            if second_num == 0:

                return {
                    "error": "Division by zero is not allowed"
                }

            result = first_num / second_num

        else:

            return {
                "error": (
                    f"Unsupported operation '{operation}'. "
                    "Use add, sub, mul, or div."
                )
            }

        return {
            "first_num": first_num,
            "second_num": second_num,
            "operation": operation,
            "result": result
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# STOCK PRICE TOOL
# ============================================================

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch the latest stock price for a given symbol.

    Examples:
    AAPL
    TSLA
    MSFT
    """

    try:

        if not ALPHA_VANTAGE_API_KEY:

            return {
                "error": "Alpha Vantage API key is not configured."
            }

        symbol = symbol.upper().strip()

        url = (
            "https://www.alphavantage.co/query"
            f"?function=GLOBAL_QUOTE"
            f"&symbol={symbol}"
            f"&apikey={ALPHA_VANTAGE_API_KEY}"
        )

        response = requests.get(
            url,
            timeout=15
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
    send_email
]


# ============================================================
# LLM WITH TOOLS
# ============================================================

llm_with_tools = model.bind_tools(tools)


# ============================================================
# LANGGRAPH STATE
# ============================================================

class ChatState(TypedDict):

    messages: Annotated[
        list[BaseMessage],
        add_messages
    ]


# ============================================================
# CHAT NODE
# ============================================================

def chat_node(state: ChatState):

    system_instruction = """
You are an AI assistant with access to tools.

Available tools:

1. send_email
   Send an email using Gmail.

2. calculator
   Perform arithmetic calculations.

3. get_stock_price
   Get the latest stock price.

4. duckduckgo_search
   Search the web.

IMPORTANT RULES:

1. If the user explicitly asks you to send an email,
   ALWAYS call the send_email tool.

2. Do not claim that an email was sent unless
   the send_email tool actually returns a successful result.

3. If the user provides a recipient, subject, and body,
   use the send_email tool.

4. For calculations, use the calculator tool when
   accurate arithmetic is required.

5. For current stock prices, use get_stock_price.

6. For current web information, use the search tool.

7. Do not fabricate tool results.

8. Explain tool results clearly to the user.
"""

    messages = state["messages"]

    # Add system instruction only for this LLM call
    from langchain_core.messages import SystemMessage

    messages_with_system = [
        SystemMessage(content=system_instruction),
        *messages
    ]

    response = llm_with_tools.invoke(
        messages_with_system
    )

    return {
        "messages": [response]
    }


# ============================================================
# LANGGRAPH TOOL NODE
# ============================================================

tool_node = ToolNode(tools)


# ============================================================
# LANGGRAPH GRAPH
# ============================================================

graph = StateGraph(ChatState)


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
    check_same_thread=False
)

checkpointer = SqliteSaver(
    conn=conn
)


# ============================================================
# COMPILE GRAPH
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

                all_threads.add(thread_id)

    except Exception as e:

        print(
            f"Error retrieving threads: {e}"
        )

    return list(all_threads)

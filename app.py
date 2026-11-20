import os
import time
import streamlit as st
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

# 1. AZURE LLM & EMBEDDINGS SETUP
llm = AzureChatOpenAI(azure_deployment="gpt-4.1-mini", temperature=0)
embeddings = AzureOpenAIEmbeddings(azure_deployment="text-embedding-3-small")

# 2. RAG KNOWLEDGE BASE (Banking Policies in Memory)
@st.cache_resource
def setup_rag():
    policies = [
        "RULE 101 (Fee Refund): Overdraft fees under 50 EUR can be refunded automatically if the client has a balance > 500 EUR and tenure > 1 year.",
        "RULE 102 (Loan Eligibility): Personal loans up to 10,000 EUR require a minimum balance of 1,000 EUR and no missed payments.",
        "RULE 103 (Escalation): Any request exceeding 10,000 EUR or involving fraud must be escalated to a human advisor."
    ]
    vectorstore = FAISS.from_texts(policies, embeddings)
    return vectorstore.as_retriever(search_kwargs={"k": 2})

retriever = setup_rag()

# 3. AGENT TOOLS (RAG Search + Mock Banking API)
@tool
def search_bank_policy(query: str) -> str:
    """Search official retail banking rules and policies."""
    docs = retriever.invoke(query)
    return "\n".join([d.page_content for d in docs])

@tool
def get_client_account_api(client_id: str) -> str:
    """Fetch client balance, tenure, and status from core banking API."""
    mock_db = {
        "CLI-01": {"balance": 1200, "tenure_years": 3, "missed_payments": 0},
        "CLI-02": {"balance": 150, "tenure_years": 0.5, "missed_payments": 1},
    }
    return str(mock_db.get(client_id, "Client not found"))

tools = [search_bank_policy, get_client_account_api]

# 4. LANGGRAPH AGENT WITH EXPLAINABILITY PROMPT
system_prompt = """You are a ABC Retail Banking AI Agent.
1. Always check the client's account via API and check official rules via RAG before deciding.
2. Provide a structured response with:
   - DECISION: (Approved / Denied / Escalated)
   - EXPLAINABILITY: Cite the exact Rule ID and client metrics used.
"""
agent = create_react_agent(llm, tools, prompt=system_prompt)

# 5. STREAMLIT UI & COST ESTIMATION
st.title("🏦 ABC Agentic AI - Retail Request Processor")
email_input = st.text_area(
    "Incoming Client Request:",
    "Client ID: CLI-01. Hi, I was charged a 35 EUR overdraft fee yesterday. Can you refund it?"
)

if st.button("Run Agent Workflow"):
    start_time = time.time()
    result = agent.invoke({"messages": [HumanMessage(content=email_input)]})
    latency = round(time.time() - start_time, 2)

    # Extract final answer & token usage
    final_msg = result["messages"][-1]
    tokens = final_msg.response_metadata.get("token_usage", {})
    prompt_tok = tokens.get("prompt_tokens", 0)
    comp_tok = tokens.get("completion_tokens", 0)
    # Approx GPT-4o-mini Azure pricing ($0.15/1M in, $0.60/1M out)
    est_cost = (prompt_tok * 0.00000015) + (comp_tok * 0.00000060)

    # Metrics Row (Cost & Performance requirement)
    col1, col2, col3 = st.columns(3)
    col1.metric("Latency", f"{latency} s")
    col2.metric("Total Tokens", prompt_tok + comp_tok)
    col3.metric("Est. Azure Cost", f"${est_cost:.6f}")

    # Final Decision & Explainability
    st.subheader("Agent Decision & Audit Trail")
    st.write(final_msg.content)

    # Show LangGraph Step-by-Step Execution
    with st.expander("View LangGraph Tool Calls & Reasoning"):
        for msg in result["messages"]:
            st.write(f"**{msg.type.upper()}:** {msg.content or msg.tool_calls}")

import os
import tempfile
import re
from datetime import datetime

import streamlit as st

# ===== LangChain =====
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document

# ===== Agno =====
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.vectordb.chroma import ChromaDb

# ==========================================================
# 🔐 Azure Config
# ==========================================================
AZURE_API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"] = 
EMBEDDING_MODEL = AzureOpenAIEmbeddings(
    azure_deployment=
    api_version="2024-12-01-preview",
)

CHAT_MODEL_ID = "gpt-4.1"
COLLECTION_NAME = "azure_rag"

# ==========================================================
# 🎨 Streamlit UI
# ==========================================================
st.set_page_config(page_title="Azure RAG Agent", layout="wide")
st.title("🤖 Azure OpenAI RAG Reasoning Agent")

# ==========================================================
# 🧠 Session State
# ==========================================================
if "vector_store" not in st.session_state:
    st.session_state.vector_store = None
if "history" not in st.session_state:
    st.session_state.history = []
if "processed_docs" not in st.session_state:
    st.session_state.processed_docs = []
if "use_web" not in st.session_state:
    st.session_state.use_web = False
if "force_web" not in st.session_state:
    st.session_state.force_web = False

# ==========================================================
# 🗄️ Vector DB
# ==========================================================
def init_chroma():
    chroma = ChromaDb(
        collection=COLLECTION_NAME,
        path="./chroma_db",
        embedder=EMBEDDING_MODEL,
        persistent_client=True,
    )
    try:
        chroma.client.get_collection(COLLECTION_NAME)
    except Exception:
        chroma.create()
    return chroma

# ==========================================================
# 📚 Document Processing
# ==========================================================
def split_docs(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return splitter.split_documents(docs)

def process_pdf(file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.read())
        loader = PyPDFLoader(tmp.name)
        docs = loader.load()

    for d in docs:
        d.metadata.update({
            "source": file.name,
            "type": "pdf",
            "timestamp": datetime.now().isoformat()
        })
    return split_docs(docs)

def process_web(url):
    loader = WebBaseLoader(url)
    docs = loader.load()
    for d in docs:
        d.metadata.update({
            "source": url,
            "type": "web",
            "timestamp": datetime.now().isoformat()
        })
    return split_docs(docs)

# ==========================================================
# 🤖 Agents
# ==========================================================
def rag_agent():
    return Agent(
        name="Azure RAG Agent",
        model=OpenAIChat(id=CHAT_MODEL_ID, azure=True),
        instructions="""
        Use provided context to answer clearly.
        Explain step by step and give examples.
        """,
        markdown=True,
    )

def web_agent():
    return Agent(
        name="Azure Web Agent",
        model=OpenAIChat(id=CHAT_MODEL_ID, azure=True),
        tools=[DuckDuckGoTools()],
        instructions="Search the web and return factual answers."
    )

def followup_agent():
    return Agent(
        name="Followup Generator",
        model=OpenAIChat(id=CHAT_MODEL_ID, azure=True),
        instructions="Output exactly 5 numbered questions only.",
        markdown=True,
    )

# ==========================================================
# 🧠 Helpers
# ==========================================================
def strip_think(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

def retrieve_context(query, chroma):
    col = chroma.client.get_collection(COLLECTION_NAME)
    res = col.query(query_texts=[query], n_results=5)
    docs = res.get("documents", [])
    if not docs:
        return ""
    return "\n\n".join([p for d in docs for p in d])

# ==========================================================
# 📎 Sidebar
# ==========================================================
st.sidebar.header("📁 Knowledge Base")

pdf = st.sidebar.file_uploader("Upload PDF", type=["pdf"])
url = st.sidebar.text_input("Or enter a URL")

st.sidebar.header("🌐 Web Search")
st.session_state.use_web = st.sidebar.checkbox("Enable Web Fallback")

if st.sidebar.button("🧹 Clear Chat"):
    st.session_state.history = []
    st.rerun()

# ==========================================================
# 📥 Ingest
# ==========================================================
chroma = init_chroma()

if pdf and pdf.name not in st.session_state.processed_docs:
    docs = process_pdf(pdf)
    col = chroma.client.get_collection(COLLECTION_NAME)
    col.add(
        ids=[f"{pdf.name}_{i}" for i in range(len(docs))],
        documents=[d.page_content for d in docs],
        metadatas=[d.metadata for d in docs],
    )
    st.session_state.processed_docs.append(pdf.name)

    q = followup_agent().run(
        "Generate questions from:\n" + " ".join(d.page_content for d in docs)
    ).content
    st.sidebar.success("PDF added")
    st.sidebar.markdown("### Follow-up Questions")
    st.sidebar.write(q)

if url and url not in st.session_state.processed_docs:
    docs = process_web(url)
    col = chroma.client.get_collection(COLLECTION_NAME)
    col.add(
        ids=[f"{url}_{i}" for i in range(len(docs))],
        documents=[d.page_content for d in docs],
        metadatas=[d.metadata for d in docs],
    )
    st.session_state.processed_docs.append(url)
    st.sidebar.success("Web page added")

# ==========================================================
# 💬 Chat
# ==========================================================
prompt = st.chat_input("Ask a question...")

if prompt:
    st.chat_message("user").write(prompt)

    context = retrieve_context(prompt, chroma)

    if not context and st.session_state.use_web:
        context = web_agent().run(prompt).content

    answer = rag_agent().run(
        f"Context:\n{context}\n\nQuestion:\n{prompt}"
    ).content

    st.chat_message("assistant").write(strip_think(answer))

"""The basic repository Q&A RAG chain, built with LCEL."""

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnablePassthrough

from app.ai.prompts.repository_qa_prompt import REPOSITORY_QA_PROMPT


def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def build_rag_chain(retriever: BaseRetriever, llm: BaseChatModel) -> Runnable:
    """Assemble the retriever -> prompt -> llm -> string chain."""
    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | REPOSITORY_QA_PROMPT
        | llm
        | StrOutputParser()
    )

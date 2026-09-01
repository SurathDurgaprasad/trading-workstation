from langchain_chroma import Chroma

from core.config import get_settings
from core.events import log_event
from llm.provider import get_embeddings
from rag.errors import RagStoreNotFoundError


def get_context(question):

    settings = get_settings()

    if not (settings.vectorstore_dir / "chroma.sqlite3").exists():
        raise RagStoreNotFoundError(settings.vectorstore_dir)

    vector_store = Chroma(
        persist_directory=str(settings.vectorstore_dir),
        embedding_function=get_embeddings(),
    )

    results = vector_store.similarity_search(
        question,
        k=settings.retrieval_top_k,
    )

    context = "\n\n".join(
        [doc.page_content for doc in results]
    )

    log_event("rag_retrieved", chunks=len(results))

    return context

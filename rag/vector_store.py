import hashlib

from langchain_chroma import Chroma

from core.config import get_settings
from llm.provider import get_embeddings


def _chunk_id(chunk) -> str:
    # Content-derived, so re-running the build against the same source PDF
    # upserts the same chunks instead of appending duplicate embeddings.
    return hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()


def create_vector_store(chunks):

    settings = get_settings()

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(settings.vectorstore_dir),
        ids=[_chunk_id(chunk) for chunk in chunks],
    )

    return vector_store

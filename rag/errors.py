from pathlib import Path


class RagStoreNotFoundError(RuntimeError):
    """The Chroma persistence directory has not been built yet."""

    def __init__(self, vectorstore_dir: Path):
        self.vectorstore_dir = vectorstore_dir
        super().__init__(
            f"No vector store found at {vectorstore_dir}. "
            f"Run `python build_vector_db.py` first."
        )

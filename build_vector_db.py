from core.config import get_settings
from rag.loader import load_and_split
from rag.vector_store import create_vector_store

settings = get_settings()

chunks = load_and_split(str(settings.strategy_document))

create_vector_store(chunks)

print("Vector database created successfully")

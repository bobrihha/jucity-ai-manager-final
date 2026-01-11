
print("Starting reindex...")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.rag import RAGSystem
from db import init_db, SessionLocal, Document

init_db()
rag = RAGSystem("nn")
rag.clear()

# Index DB
db = SessionLocal()
docs = db.query(Document).all()
print(f"Docs in DB: {len(docs)}")
for doc in docs:
    rag.add_document(f"db_{doc.id}", doc.content, doc.category, doc.title)
db.close()

# Index Files
print("Indexing files...")
count = rag.index_knowledge_files()
print(f"Files indexed: {count}")
print("Done.")

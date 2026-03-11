#!/usr/bin/env python3
"""Check what HomeController chunks exist in database."""

import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv(".env", override=True)

async def check_database():
    """Check database for HomeController."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    
    print("=" * 70)
    print("Checking for HomeController in database...")
    print("=" * 70)
    
    # Check documents
    docs = await conn.fetch(
        """
        SELECT id, title, source 
        FROM documents 
        WHERE title ILIKE '%HomeController%' OR source ILIKE '%HomeController%'
        """
    )
    
    print(f"\nFound {len(docs)} documents matching 'HomeController':")
    for doc in docs:
        print(f"  - {doc['title']} ({doc['source']})")
    
    # Check chunks
    chunks = await conn.fetch(
        """
        SELECT c.id, c.content, d.title, d.source 
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.content ILIKE '%HomeController%' OR d.title ILIKE '%HomeController%'
        LIMIT 5
        """
    )
    
    print(f"\nFound {len(chunks)} chunks mentioning 'HomeController':")
    for chunk in chunks:
        print(f"\n  Document: {chunk['title']}")
        print(f"  Source: {chunk['source']}")
        print(f"  Content preview: {chunk['content'][:200]}...")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_database())

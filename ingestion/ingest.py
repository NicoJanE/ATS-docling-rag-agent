"""
Main ingestion script for processing markdown documents into vector DB and knowledge graph.
"""

import os
import sys
import asyncio
import logging
import json
import glob
import warnings
from pathlib import Path

# Suppress multiprocess cleanup error (known issue with Python 3.12+)
# Set environment variable before multiprocess imports
os.environ['PYTHONWARNINGS'] = 'ignore:.*_thread.RLock.*'
warnings.filterwarnings('ignore', message='.*_thread.RLock.*')

from typing import List, Dict, Any, Optional
from datetime import datetime
import argparse

import asyncpg
from dotenv import load_dotenv

from .chunker import ChunkingConfig, create_chunker, DocumentChunk
from .embedder import create_embedder
from .code_indexer import CodeIndexer, CodeChunk

# Import utilities
try:
    from ..utils.db_utils import initialize_database, close_database, db_pool
    from ..utils.models import IngestionConfig, IngestionResult
except ImportError:
    # For direct execution or testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.db_utils import initialize_database, close_database, db_pool
    from utils.models import IngestionConfig, IngestionResult

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    """Pipeline for ingesting documents into vector DB and knowledge graph."""
    
    def __init__(
        self,
        config: IngestionConfig,
        documents_folder: str = "RAG_documents",
        clean_before_ingest: bool = True
    ):
        """
        Initialize ingestion pipeline.

        Args:
            config: Ingestion configuration
            documents_folder: Folder containing markdown documents
            clean_before_ingest: Whether to clean existing data before ingestion (default: True)
        """
        self.config = config
        self.documents_folder = documents_folder
        self.clean_before_ingest = clean_before_ingest
        
        # Initialize components
        self.chunker_config = ChunkingConfig(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            max_chunk_size=config.max_chunk_size,
            use_semantic_splitting=config.use_semantic_chunking
        )
        
        self.chunker = create_chunker(self.chunker_config)
        self.embedder = create_embedder()
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connections."""
        if self._initialized:
            return
        
        logger.info("Initializing ingestion pipeline...")
        
        # Initialize database connections
        await initialize_database()
        
        self._initialized = True
        logger.info("Ingestion pipeline initialized")
    
    async def close(self):
        """Close database connections."""
        if self._initialized:
            await close_database()
            self._initialized = False
    
    async def ingest_documents(
        self,
        progress_callback: Optional[callable] = None
    ) -> List[IngestionResult]:
        """
        Ingest all documents from the documents folder.
        
        Args:
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of ingestion results
        """
        if not self._initialized:
            await self.initialize()
        
        # Clean existing data if requested
        if self.clean_before_ingest:
            await self._clean_databases()
        
        # Find all supported document files
        document_files = self._find_document_files()

        if not document_files:
            logger.warning(f"No supported document files found in {self.documents_folder}")
            return []

        logger.info(f"Found {len(document_files)} document files to process")

        results = []

        for i, file_path in enumerate(document_files):
            try:
                logger.info(f"Processing file {i+1}/{len(document_files)}: {file_path}")

                result = await self._ingest_single_document(file_path)
                results.append(result)

                if progress_callback:
                    progress_callback(i + 1, len(document_files))
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results.append(IngestionResult(
                    document_id="",
                    title=os.path.basename(file_path),
                    chunks_created=0,
                    entities_extracted=0,
                    relationships_created=0,
                    processing_time_ms=0,
                    errors=[str(e)]
                ))
        
        # Log summary
        total_chunks = sum(r.chunks_created for r in results)
        total_errors = sum(len(r.errors) for r in results)
        
        logger.info(f"Ingestion complete: {len(results)} documents, {total_chunks} chunks, {total_errors} errors")
        
        return results
    
    async def ingest_source_code(
        self,
        source_code_folder: str,
        progress_callback: Optional[callable] = None
    ) -> List[IngestionResult]:
        """
        Ingest source code files from a directory using tree-sitter for semantic parsing.
        
        Args:
            source_code_folder: Path to source code directory
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of ingestion results
        """
        if not self._initialized:
            await self.initialize()
        
        # Note: Do NOT clean databases when ingesting code
        # This allows mixing documents + code in same knowledge base
        
        # Initialize code indexer
        code_indexer = CodeIndexer()
        
        logger.info(f"Indexing source code from {source_code_folder}")
        code_chunks = code_indexer.index_directory(source_code_folder)
        
        if not code_chunks:
            logger.warning(f"No code chunks found in {source_code_folder}")
            return []
        
        logger.info(f"Found {len(code_chunks)} code chunks")
        
        results = []
        
        # Group chunks by file for processing
        chunks_by_file = {}
        for chunk in code_chunks:
            if chunk.file_path not in chunks_by_file:
                chunks_by_file[chunk.file_path] = []
            chunks_by_file[chunk.file_path].append(chunk)
        
        for file_idx, (file_path, file_chunks) in enumerate(chunks_by_file.items()):
            try:
                logger.info(f"Processing code file {file_idx+1}/{len(chunks_by_file)}: {file_path}")
                
                result = await self._ingest_code_file(file_path, file_chunks)
                results.append(result)
                
                if progress_callback:
                    progress_callback(file_idx + 1, len(chunks_by_file))
                
            except Exception as e:
                logger.error(f"Failed to process code file {file_path}: {e}")
                results.append(IngestionResult(
                    document_id="",
                    title=os.path.basename(file_path),
                    chunks_created=0,
                    entities_extracted=0,
                    relationships_created=0,
                    processing_time_ms=0,
                    errors=[str(e)]
                ))
        
        total_chunks = sum(r.chunks_created for r in results)
        logger.info(f"Source code ingestion complete: {len(results)} files, {total_chunks} chunks")
        
        return results
    
    async def _ingest_code_file(
        self,
        file_path: str,
        code_chunks: List[CodeChunk]
    ) -> IngestionResult:
        """
        Ingest a single source code file into the knowledge base.
        
        Args:
            file_path: Path to source code file
            code_chunks: List of CodeChunk objects from tree-sitter parsing
            
        Returns:
            Ingestion result
        """
        start_time = datetime.now()
        
        file_title = f"{Path(file_path).stem} ({Path(file_path).suffix})"
        document_source = os.path.relpath(file_path, "RAG_source_code")
        
        # Check if code file already exists (duplicate prevention)
        async with db_pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, title FROM documents WHERE source = $1",
                document_source
            )
            
            if existing:
                logger.info(f"⏭️  Skipping {file_title} - already indexed (existing ID: {existing['id']})")
                return IngestionResult(
                    document_id=str(existing['id']),
                    title=file_title,
                    chunks_created=0,
                    entities_extracted=0,
                    relationships_created=0,
                    processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    errors=["Already indexed (skipped)"]
                )
        
        logger.info(f"Ingesting code file: {file_title}")
        
        # Convert CodeChunks to DocumentChunks for embedding
        document_chunks = []
        
        for i, code_chunk in enumerate(code_chunks):
            # Create metadata for source code
            metadata = {
                **(code_chunk.metadata or {}),
                'type': 'source_code',
                'code_kind': code_chunk.kind,
                'language': code_chunk.language,
                'file_path': code_chunk.file_path,
                'start_line': code_chunk.start_line,
                'end_line': code_chunk.end_line,
            }
            
            # Create content that includes context
            content = f"[{code_chunk.kind.upper()}] {code_chunk.name}\n{code_chunk.content}"
            
            doc_chunk = DocumentChunk(
                content=content,
                index=i,
                start_char=0,
                end_char=len(content),
                metadata=metadata
            )
            document_chunks.append(doc_chunk)
        
        # Generate embeddings
        embedded_chunks = await self.embedder.embed_chunks(document_chunks)
        logger.info(f"Generated embeddings for {len(embedded_chunks)} code chunks")
        
        # Save full file content as document
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                full_content = f.read()
        except:
            full_content = ""
        
        # Save to PostgreSQL
        document_id = await self._save_to_postgres(
            file_title,
            document_source,
            full_content,
            embedded_chunks,
            metadata={'type': 'source_code', 'language': code_chunks[0].language if code_chunks else 'unknown'}
        )
        
        logger.info(f"Saved source code file to PostgreSQL with ID: {document_id}")
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return IngestionResult(
            document_id=document_id,
            title=file_title,
            chunks_created=len(embedded_chunks),
            entities_extracted=0,
            relationships_created=0,
            processing_time_ms=processing_time,
            errors=[]
        )
    
    async def _ingest_single_document(self, file_path: str) -> IngestionResult:
        """
        Ingest a single document.

        Args:
            file_path: Path to the document file

        Returns:
            Ingestion result
        """
        start_time = datetime.now()

        # Read document (returns tuple: content, docling_doc)
        document_content, docling_doc = self._read_document(file_path)
        document_title = self._extract_title(document_content, file_path)
        document_source = os.path.relpath(file_path, self.documents_folder)
        
        # Check if document already exists (duplicate prevention)
        async with db_pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, title FROM documents WHERE source = $1",
                document_source
            )
            
            if existing:
                logger.info(f"⏭️  Skipping {document_title} - already indexed (existing ID: {existing['id']})")
                return IngestionResult(
                    document_id=str(existing['id']),
                    title=document_title,
                    chunks_created=0,
                    entities_extracted=0,
                    relationships_created=0,
                    processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    errors=["Already indexed (skipped)"]
                )

        # Extract metadata from content
        document_metadata = self._extract_document_metadata(document_content, file_path)

        logger.info(f"Processing document: {document_title}")

        # Chunk the document - pass DoclingDocument for HybridChunker
        chunks = await self.chunker.chunk_document(
            content=document_content,
            title=document_title,
            source=document_source,
            metadata=document_metadata,
            docling_doc=docling_doc  # Pass DoclingDocument for HybridChunker
        )
        
        if not chunks:
            logger.warning(f"No chunks created for {document_title}")
            return IngestionResult(
                document_id="",
                title=document_title,
                chunks_created=0,
                entities_extracted=0,
                relationships_created=0,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                errors=["No chunks created"]
            )
        
        logger.info(f"Created {len(chunks)} chunks")
        
        # Entity extraction removed (graph-related functionality)
        entities_extracted = 0
        
        # Generate embeddings
        embedded_chunks = await self.embedder.embed_chunks(chunks)
        logger.info(f"Generated embeddings for {len(embedded_chunks)} chunks")
        
        # Save to PostgreSQL
        document_id = await self._save_to_postgres(
            document_title,
            document_source,
            document_content,
            embedded_chunks,
            document_metadata
        )
        
        logger.info(f"Saved document to PostgreSQL with ID: {document_id}")
        
        # Knowledge graph functionality removed
        relationships_created = 0
        graph_errors = []
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return IngestionResult(
            document_id=document_id,
            title=document_title,
            chunks_created=len(chunks),
            entities_extracted=entities_extracted,
            relationships_created=relationships_created,
            processing_time_ms=processing_time,
            errors=graph_errors
        )
    
    def _find_document_files(self) -> List[str]:
        """Find all supported document files in the documents folder."""
        if not os.path.exists(self.documents_folder):
            logger.error(f"Documents folder not found: {self.documents_folder}")
            return []

        # Supported file patterns - Docling + text formats + audio
        patterns = [
            "*.md", "*.markdown", "*.txt",  # Text formats
            "*.pdf",  # PDF
            "*.docx", "*.doc",  # Word
            "*.pptx", "*.ppt",  # PowerPoint
            "*.xlsx", "*.xls",  # Excel
            "*.html", "*.htm",  # HTML
            "*.mp3", "*.wav", "*.m4a", "*.flac",  # Audio formats
        ]
        files = []

        for pattern in patterns:
            files.extend(glob.glob(os.path.join(self.documents_folder, "**", pattern), recursive=True))

        return sorted(files)
    
    def _read_document(self, file_path: str) -> tuple[str, Optional[Any]]:
        """
        Read document content from file - supports multiple formats via Docling.

        Returns:
            Tuple of (markdown_content, docling_document)
            docling_document is None for text files and audio files
        """
        file_ext = os.path.splitext(file_path)[1].lower()

        # Audio formats - transcribe with Whisper ASR
        audio_formats = ['.mp3', '.wav', '.m4a', '.flac']
        if file_ext in audio_formats:
            content = self._transcribe_audio(file_path)
            return (content, None)  # No DoclingDocument for audio

        # Docling-supported formats (convert to markdown)
        docling_formats = ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.html', '.htm']

        if file_ext in docling_formats:
            try:
                from docling.document_converter import DocumentConverter

                logger.info(f"Converting {file_ext} file using Docling: {os.path.basename(file_path)}")

                converter = DocumentConverter()
                result = converter.convert(file_path)

                # Export to markdown for consistent processing
                markdown_content = result.document.export_to_markdown()
                logger.info(f"Successfully converted {os.path.basename(file_path)} to markdown")

                # Return both markdown and DoclingDocument for HybridChunker
                return (markdown_content, result.document)

            except Exception as e:
                logger.error(f"Failed to convert {file_path} with Docling: {e}")
                # Fall back to raw text if Docling fails
                logger.warning(f"Falling back to raw text extraction for {file_path}")
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return (f.read(), None)
                except:
                    return (f"[Error: Could not read file {os.path.basename(file_path)}]", None)

        # Text-based formats (read directly)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return (f.read(), None)
            except UnicodeDecodeError:
                # Try with different encoding
                with open(file_path, 'r', encoding='latin-1') as f:
                    return (f.read(), None)

    def _transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio file using Whisper ASR via Docling."""
        try:
            from pathlib import Path
            from docling.document_converter import DocumentConverter, AudioFormatOption
            from docling.datamodel.pipeline_options import AsrPipelineOptions
            from docling.datamodel import asr_model_specs
            from docling.datamodel.base_models import InputFormat
            from docling.pipeline.asr_pipeline import AsrPipeline

            # Use Path object - Docling expects this
            audio_path = Path(file_path).resolve()
            logger.info(f"Transcribing audio file using Whisper Turbo: {audio_path.name}")
            logger.info(f"Audio file absolute path: {audio_path}")

            # Verify file exists
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            # Configure ASR pipeline with Whisper Turbo model
            pipeline_options = AsrPipelineOptions()
            pipeline_options.asr_options = asr_model_specs.WHISPER_TURBO

            converter = DocumentConverter(
                format_options={
                    InputFormat.AUDIO: AudioFormatOption(
                        pipeline_cls=AsrPipeline,
                        pipeline_options=pipeline_options,
                    )
                }
            )

            # Transcribe the audio file - pass Path object
            result = converter.convert(audio_path)

            # Export to markdown with timestamps
            markdown_content = result.document.export_to_markdown()
            logger.info(f"Successfully transcribed {os.path.basename(file_path)}")
            return markdown_content

        except Exception as e:
            logger.error(f"Failed to transcribe {file_path} with Whisper ASR: {e}")
            return f"[Error: Could not transcribe audio file {os.path.basename(file_path)}]"

    def _extract_title(self, content: str, file_path: str) -> str:
        """Extract title from document content or filename."""
        # Try to find markdown title
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        
        # Fallback to filename
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _extract_document_metadata(self, content: str, file_path: str) -> Dict[str, Any]:
        """Extract metadata from document content."""
        metadata = {
            "file_path": file_path,
            "file_size": len(content),
            "ingestion_date": datetime.now().isoformat()
        }
        
        # Try to extract YAML frontmatter
        if content.startswith('---'):
            try:
                import yaml
                end_marker = content.find('\n---\n', 4)
                if end_marker != -1:
                    frontmatter = content[4:end_marker]
                    yaml_metadata = yaml.safe_load(frontmatter)
                    if isinstance(yaml_metadata, dict):
                        metadata.update(yaml_metadata)
            except ImportError:
                logger.warning("PyYAML not installed, skipping frontmatter extraction")
            except Exception as e:
                logger.warning(f"Failed to parse frontmatter: {e}")
        
        # Extract some basic metadata from content
        lines = content.split('\n')
        metadata['line_count'] = len(lines)
        metadata['word_count'] = len(content.split())
        
        return metadata
    
    async def _save_to_postgres(
        self,
        title: str,
        source: str,
        content: str,
        chunks: List[DocumentChunk],
        metadata: Dict[str, Any]
    ) -> str:
        """Save document and chunks to PostgreSQL."""
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Insert document
                document_result = await conn.fetchrow(
                    """
                    INSERT INTO documents (title, source, content, metadata)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id::text
                    """,
                    title,
                    source,
                    content,
                    json.dumps(metadata)
                )
                
                document_id = document_result["id"]
                
                # Insert chunks
                for chunk in chunks:
                    # Convert embedding to PostgreSQL vector string format
                    embedding_data = None
                    if hasattr(chunk, 'embedding') and chunk.embedding:
                        # PostgreSQL vector format: '[1.0,2.0,3.0]' (no spaces after commas)
                        embedding_data = '[' + ','.join(map(str, chunk.embedding)) + ']'
                    
                    await conn.execute(
                        """
                        INSERT INTO chunks (document_id, content, embedding, chunk_index, metadata, token_count)
                        VALUES ($1::uuid, $2, $3::vector, $4, $5, $6)
                        """,
                        document_id,
                        chunk.content,
                        embedding_data,
                        chunk.index,
                        json.dumps(chunk.metadata),
                        chunk.token_count
                    )
                
                return document_id
    
    async def _clean_databases(self):
        """Clean existing data from databases."""
        logger.warning("Cleaning existing data from databases...")
        
        # Clean PostgreSQL
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM chunks")
                await conn.execute("DELETE FROM documents")
        
        logger.info("Cleaned PostgreSQL database")

async def main():
    """Main function for running ingestion."""
    parser = argparse.ArgumentParser(description="Ingest documents and/or source code into vector DB")
    parser.add_argument("--documents", "-d", default="RAG_documents", help="Documents folder path")
    parser.add_argument("--source-code", "-s", default=None, help="Source code folder path (optional)")
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning existing data before ingestion (default: cleans automatically)")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk size for splitting documents")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap size")
    parser.add_argument("--no-semantic", action="store_true", help="Disable semantic chunking")
    # Graph-related arguments removed
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create ingestion configuration
    config = IngestionConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        use_semantic_chunking=not args.no_semantic
    )

    # Create and run pipeline - clean by default unless --no-clean is specified
    pipeline = DocumentIngestionPipeline(
        config=config,
        documents_folder=args.documents,
        clean_before_ingest=not args.no_clean  # Clean by default
    )
    
    def progress_callback(current: int, total: int):
        print(f"Progress: {current}/{total} documents processed")
    
    try:
        start_time = datetime.now()
        
        # Ingest documents only if folder has files
        doc_results = []
        document_files = glob.glob(os.path.join(args.documents, "**/*"), recursive=True)
        supported_extensions = ('.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', 
                               '.html', '.htm', '.md', '.markdown', '.txt', '.mp3')
        has_documents = any(f.lower().endswith(supported_extensions) for f in document_files if os.path.isfile(f))
        
        if has_documents or (args.documents != "RAG_documents" and os.path.exists(args.documents)):
            logger.info(f"Ingesting documents from {args.documents}")
            doc_results = await pipeline.ingest_documents(progress_callback)
        
        # Ingest source code if specified
        code_results = []
        if args.source_code:
            if os.path.exists(args.source_code):
                logger.info(f"Ingesting source code from {args.source_code}")
                code_results = await pipeline.ingest_source_code(args.source_code, progress_callback)
            else:
                logger.error(f"❌ Source code folder not found: {args.source_code}")
                logger.info(f"   Current working directory: {os.getcwd()}")
                logger.info(f"   Please provide a valid path (relative or absolute)")
        
        # Combine results
        results = doc_results + code_results
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        # Print summary
        print("\n" + "="*50)
        print("INGESTION SUMMARY")
        print("="*50)
        print(f"Documents processed: {len(results)}")
        print(f"Total chunks created: {sum(r.chunks_created for r in results)}")
        # Graph-related stats removed
        print(f"Total errors: {sum(len(r.errors) for r in results)}")
        print(f"Total processing time: {total_time:.2f} seconds")
        print()
        
        # Print individual results
        for result in results:
            status = "[OK]" if not result.errors else "[ERR]"
            print(f"{status} {result.title}: {result.chunks_created} chunks")
            
            if result.errors:
                for error in result.errors:
                    print(f"  Error: {error}")
        
    except KeyboardInterrupt:
        print("\nIngestion interrupted by user")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        await pipeline.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        # Suppress multiprocess cleanup warnings - they don't affect functionality
        if "_thread.RLock" in str(e) or "ignored in:" in str(e):
            pass
        else:
            raise
    except KeyboardInterrupt:
        print("\n👋 Ingestion cancelled by user")
        sys.exit(0)
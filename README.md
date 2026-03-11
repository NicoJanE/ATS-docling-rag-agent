# Docling RAG Agent

An intelligent text-based CLI agent that provides conversational access to a knowledge base stored in PostgreSQL with PGVector. Uses RAG (Retrieval Augmented Generation) to search through embedded documents and provide contextual, accurate responses with source citations. Supports multiple document formats including audio files with Whisper transcription.

## 🎓 New to Docling?

**Start with the tutorials!** Check out the [`docling_basics/`](./docling_basics/) folder for progressive examples that teach Docling fundamentals:

1. **Simple PDF Conversion** - Basic document processing
2. **Multiple Format Support** - PDF, Word, PowerPoint handling
3. **Audio Transcription** - Speech-to-text with Whisper
4. **Hybrid Chunking** - Intelligent chunking for RAG systems


>**❗Orginal Author**
This document is an extension from the great documentation provided by: Cole Medin. His YouTube explanation can be found [**here**](https://www.youtube.com/watch?v=fg0_0M8kZ8g). And the original repository can be found [**here**](https://github.com/coleam00/ottomator-agents/tree/main/docling-rag-agent).  which also contains the  **docling_basics** example 

I just Added support for the items mentioned in the section below 

## 🚀 Recent Improvements (March 2026)

**Enhancements for Developer Workflows:**

1. **📚Support for Local LLM** KoboldCPP (see .env file)
1. **🔍 Hybrid Search (Keyword + Semantic)** - Finds exact code identifiers (classes, methods) that pure semantic search missed
2. **📍 Line Numbers** - Shows precise locations: `HomeController.cs:70` or `:13-72`
3. **↪️ Follow-up Context** - Ask "show it" or "what methods?" after finding a class
4. **📊 20 Result Limit** - Increased from 5 to better show usage across files
5. **🚫 Duplicate Prevention** - Re-running ingest automatically skips existing documents
6. **🎯 Source Type Ranking** - Optional CLI flag to boost code files in results
7. **📚 Added a Quick_Reference.md** document

See [Testing the Improvements](#testing-the-improvements) section for verification tests.

## Features

### Core RAG Features
- 💬 Interactive text-based CLI with streaming responses
- 🔍 **Hybrid search** (keyword + semantic) for code and documentation
- 📚 Context-aware responses using RAG pipeline
- 🎯 Source citation with **line numbers** for all code references
- 🔄 Real-time streaming text output as tokens arrive
- 💾 PostgreSQL/PGVector for scalable knowledge storage
- 🧠 **Conversation history** with follow-up question support
- 🎙️ Audio transcription with Whisper ASR (MP3 files)

### Developer Workflow Features (New!)
- 🔬 **Hybrid search**: Finds exact code identifiers (classes, methods) + semantic concepts
- 📍 **Line numbers**: Shows exact locations (`HomeController.cs:70-72`)
- 🔄 **Follow-up context**: Ask "show it" after finding a class
- 📊 **20 result limit**: See more usage locations (up from 5)
- 🚫 **Duplicate prevention**: Re-running ingest skips existing documents
- 🎯 **Source type ranking**: Optional boost for code files in search results
- 📦 **Complete methods**: No chunk splitting - preserves full code context

## Prerequisites

- Python 3.9 or later
- PostgreSQL with PGVector extension (Supabase, Neon, self-hosted Postgres, etc.)
- API Keys:
  - OpenAI API key (for embeddings and LLM)

## Quick Start

### 1. Install Dependencies

```bash
# Install dependencies using UV
uv sync
```

### 2. Set Up Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `DATABASE_URL` - PostgreSQL connection string with PGVector extension
  - Example: `postgresql://user:password@localhost:5432/dbname`
  - Supabase: `postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres`
  - Neon: `postgresql://[user]:[password]@[endpoint].neon.tech/[dbname]`

- `OPENAI_API_KEY` - OpenAI API key for embeddings and LLM
  - Get from: https://platform.openai.com/api-keys

Optional variables:
- `LLM_CHOICE` - OpenAI model to use (default: `gpt-4o-mini`)
- `EMBEDDING_MODEL` - Embedding model (default: `text-embedding-3-small`)

### 3. Configure Database

You must set up your PostgreSQL database with the PGVector extension and create the required schema:

1. **Enable PGVector extension** in your database (most cloud providers have this pre-installed)
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **Run the schema file** to create tables and functions:
   ```bash
   # In the SQL editor in Supabase/Neon, run:
   sql/schema.sql

   # Or using psql
   psql $DATABASE_URL < sql/schema.sql
   ```

The schema file (`sql/schema.sql`) creates:
- `documents` table for storing original documents with metadata
- `chunks` table for text chunks with 1536-dimensional embeddings
- `match_chunks()` function for vector similarity search

**JUST run the docker container instead :**
`docker-compose up postgres -d`
This will:

1. Pull the pgvector/pgvector:pg15 image (PostgreSQL 15 with PGVector pre-installed)
2. Create a container named rag_postgres
3. Set up the database with:
    - User: raguser
    - Password: ragpass123
    - Database: postgres
    - Port: 5432
    - Automatically run schema.sql to create the required tables

Note: to recreate the database use:
`docker-compose exec postgres psql -U raguser -d postgres -f /docker-entrypoint-initdb.d/01-schema.sql`


### 4. Ingest Documents

Add your documents to the `RAG_documents/` folder. **Multiple formats supported via Docling**:

**Supported Formats:**
- 📄 **PDF** (`.pdf`)
- 📝 **Word** (`.docx`, `.doc`)
- 📊 **PowerPoint** (`.pptx`, `.ppt`)
- 📈 **Excel** (`.xlsx`, `.xls`)
- 🌐 **HTML** (`.html`, `.htm`)
- 📋 **Markdown** (`.md`, `.markdown`)
- 📃 **Text** (`.txt`)
- 🎵 **Audio** (`.mp3`) - transcribed with Whisper

```bash
# Ingest all supported documents in the RAG_documents/ folder
# NOTE: By default, this CLEARS existing data before ingestion
uv run python -m ingestion.ingest --documents RAG_documents/

# Adjust chunk size (default: 1000)
uv run python -m ingestion.ingest --documents RAG_documents/ --chunk-size 800
```

**⚠️ IMPORTANT - Database Cleaning Behavior:**
- By default, the ingestion process **clears all existing data** before adding new documents
- Use `--no-clean` flag to **preserve existing data** and add incrementally:
  ```bash
  # Keep existing chunks and add more documents/code
  uv run python -m ingestion.ingest --source-code RAG_source_code/ --no-clean
  ```
- Only documents found in the folders are processed (empty folders are skipped even without --no-clean)

**✨ NEW: Duplicate Prevention (Automatic)**
- Running ingest multiple times **automatically skips** already-indexed documents
- Checks source path: if document exists, logs "⏭️ Skipping... - already indexed"
- No more 9x duplicates from re-running ingest!
- Example:
  ```bash
  # First run: indexes 232 documents
  uv run python -m ingestion.ingest --documents RAG_documents/
  
  # Second run: skips all 232, processes 0 new
  uv run python -m ingestion.ingest --documents RAG_documents/
  # Output: "⏭️ Skipping company-overview.md - already indexed..."
  ```

The ingestion pipeline will:
1. **Auto-detect file type** and use Docling for PDFs, Office docs, HTML, and audio
2. **Transcribe audio files** using Whisper Turbo ASR with timestamps
3. **Convert to Markdown** for consistent processing
4. **Split into semantic chunks** with configurable size
5. **Generate embeddings** using OpenAI
6. **Store in PostgreSQL** with PGVector for similarity search

### 4b. Ingest Source Code (Optional)

**Add searchable source code to your knowledge base!** Uses **tree-sitter** for semantic code parsing (100+ language support).

```bash
# Create source_code folder with your code
mkdir RAG_source_code
cp -r your_project/* RAG_source_code/

# Ingest both documents AND source code
uv run python -m ingestion.ingest --documents RAG_documents/ --source-code RAG_source_code/

# Or ingest only source code (without cleaning existing data)
uv run python -m ingestion.ingest --source-code RAG_source_code/ --no-clean
```

**Supported Languages:**
- 🐍 Python, 🟨 JavaScript/TypeScript, ☕ Java
- 🔷 C#, ⚙️ C/C++, 🦀 Rust, 🐹 Go

**Features:**
- 🔬 **Semantic parsing** - Extracts functions, classes, methods as chunks
- 🏷️ **Metadata** - Preserves line numbers, signatures, docstrings
- 🔍 **Searchable** - Find code: "Where is `SkiInit` defined?"
- 📚 **Mixed search** - Search documents + code in one query

See [SOURCE_CODE_SETUP.md](./SOURCE_CODE_SETUP.md) for detailed setup.

### 5. Run the Agent

```bash
# Run the Docling RAG Agent CLI
uv run python cli.py

# Run with code source ranking (boosts .cs, .py, .ts files for code queries)
uv run python cli.py --rank-code-sources

# Enable verbose logging (shows all debug info)
uv run python cli.py --verbose
```

**Features:**
- 🎨 **Colored output** for better readability
- 📊 **Session statistics** (`stats` command)
- 🔄 **Clear history** (`clear` command)
- 💡 **Built-in help** (`help` command)
- ✅ **Database health check** on startup
- 🔍 **Real-time streaming** responses
- 📍 **Line numbers** in code search results
- 🔄 **Follow-up questions** with context memory
- 🎯 **Hybrid search** (keyword + semantic)

**CLI Options:**
- `--verbose`, `-v` - Enable verbose logging
- `--model MODEL` - Override LLM model (e.g., gpt-4o)
- `--rank-code-sources` - Boost code files in search results (10% relevance boost)

**Available commands:**
- `help` - Show help information
- `clear` - Clear conversation history
- `stats` - Show session statistics
- `exit` or `quit` - Exit the CLI

**Example interaction:**
```
============================================================
🤖 Docling RAG Knowledge Assistant
============================================================
AI-powered document search with streaming responses
Type 'exit', 'quit', or Ctrl+C to exit
Type 'help' for commands
============================================================

✓ Database connection successful
✓ Knowledge base ready: 232 documents, 2832 chunks
Ready to chat! Ask me anything about the knowledge base.

You: Where is ErrorViewModel used?
🤖 Assistant: The word "ErrorViewModel" is used in the following places:

1. Source 1: ErrorViewModel (.cs) - Models\ErrorViewModel.cs:3-8
   - This is where the ErrorViewModel class is defined.

2. Source 2: ApplicationDbContext (.cs) - Data\ApplicationDbContext.cs:10-18
   - ErrorViewModel is used as a DbSet in the ApplicationDbContext class.

3. Source 3: HomeController (.cs) - Controllers\HomeController.cs:70
   - ErrorViewModel is used in the Error() method...

────────────────────────────────────────────────────────────
You: show the Index method in HomeController
🤖 Assistant: The Index method in HomeController is located at line 51-54...

────────────────────────────────────────────────────────────
You: quit
👋 Thank you for using the knowledge assistant. Goodbye!
```

**Code Search Examples:**
```bash
# Find class definitions
You: Do I have HomeController in my code?
Assistant: Yes, found in Controllers\HomeController.cs:13-72

# Find method usage across files
You: Where is ILogger used?
Assistant: Found in 10+ locations across HomeController, DiagnosticService...

# Follow-up questions (context remembered)
You: Do I have DiagnosticService?
Assistant: Yes, found in Helpers\Debug\DiagnosticService.cs:10-150

You: what methods does it have?
Assistant: DiagnosticService has the following methods:
- PrintServiceHierarchy() - line 45
- GetRegisteredServices() - line 89
...
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   CLI User  │────▶│  RAG Agent   │────▶│ PostgreSQL  │
│   (Input)   │     │ (PydanticAI) │     │  PGVector   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼────┐  ┌────▼─────┐
              │  OpenAI  │  │  OpenAI  │
              │   LLM    │  │Embeddings│
              └──────────┘  └──────────┘
```

## Enhanced Search Capabilities

### Hybrid Search (Keyword + Semantic)

The system now uses **intelligent hybrid search** that combines keyword matching with semantic vector search:

**How it works:**
1. **Pattern extraction**: Detects code identifiers (CamelCase, PascalCase)
   - Query: "Where is HomeController used?"
   - Extracted: `["HomeController"]`

2. **Keyword search first**: PostgreSQL `ILIKE` for exact matches
   - Searches in: chunk content + document titles
   - Assigns 95% relevance to keyword matches

3. **Semantic fallback**: Vector similarity if no keyword matches
   - Uses cosine similarity for conceptual queries
   - Ideal for "What does error handling look like?"

**Benefits:**
- ✅ **Finds exact code**: "Do I have HomeController?" → YES with code
- ✅ **Cross-references**: "Where is ILogger used?" → All locations
- ✅ **No false negatives**: Pure semantic search missed exact names
- ✅ **Best of both worlds**: Keyword precision + semantic understanding

### Line Number Tracking

Code search results now include **exact line numbers**:

**Format:**
- Single line: `HomeController.cs:70`
- Line range: `HomeController.cs:13-72`
- Shows in results: `[Source 1: HomeController.cs:13-72 (relevance: 95%)]`

**How it works:**
- tree-sitter parsing captures `start_line` and `end_line` during indexing
- Metadata stored in chunks table
- CLI extracts and displays in results

**Benefits:**
- 🎯 Jump directly to code in IDE
- 📍 Know exact location of classes/methods
- 🔍 Better than "somewhere in this file"

### Follow-up Question Support

The CLI now **remembers context** from previous queries:

**Detection logic:**
- Tracks `last_query` in conversation
- Detects vague references: "it", "show me", "what methods", "tell me more"
- Enhances follow-up with context from previous query

**Examples:**
```bash
# First query (explicit)
You: Do I have HomeController?
Assistant: Yes, found in Controllers\HomeController.cs

# Follow-up (vague reference)
You: show it
# System enhances: "Previous context: HomeController. Follow-up: show it"
Assistant: Here's the HomeController code...

# Another follow-up
You: what methods does it have?
# System adds context automatically
Assistant: HomeController has Index(), Privacy(), Error()...
```

**Limitations:**
- Works best when follow-up includes some context
- "show first 10 lines" without identifier may fail
- Explicit mentions always work: "show the Index method in HomeController"

### Increased Result Limit (20 Results)

**Changed from 5 to 20** to better support developer workflows:

**Why 20?**
- Finding method/class usage often spans 10+ files
- "Where is ILogger used?" needs comprehensive results
- Previous limit=5 missed important locations

**Features:**
- Shows "(Showing X of Y results)" if more available
- All 20 displayed by default
- Can be adjusted in code if needed

**Example:**
```bash
You: Where is ErrorViewModel used?
Result: 7 sources shown (previously only 5, missing HomeController at position 7)
```

### Source Type Ranking (Optional)

CLI option to **boost code files** in search results:

**Usage:**
```bash
# Enable code source ranking
uv run python cli.py --rank-code-sources
```

**How it works:**
- Detects code queries: contains "class", "method", "function", "used", "where is"
- Boosts code files (.cs, .py, .ts, .js, .java, .cpp, .c, .go, .rs, .rb)
- Increases relevance by 10%: 95% → 99% (capped at 99%)
- Re-sorts results by boosted similarity

**When to use:**
- ✅ Primarily working with source code
- ✅ Want code files prioritized over documentation
- ❌ Mixed queries (docs + code equally important)

**Example:**
```bash
# Without ranking
Query: "Where is ErrorViewModel?"
Result: [1] ErrorViewModel.cs (95%), [2] Documentation.md (94%), [3] HomeController.cs (93%)

# With --rank-code-sources
Query: "Where is ErrorViewModel?"  
Result: [1] ErrorViewModel.cs (99%), [2] HomeController.cs (99%), [3] Documentation.md (94%)
```

### Complete Method Preservation

Code chunks now **preserve complete methods** without splitting:

**Configuration** (in `ingestion/code_indexer.py`):
```python
# Set to None for complete methods (recommended)
MAX_LINES_PER_CHUNK = None

# Or set to integer to limit (e.g., 100 lines)
# MAX_LINES_PER_CHUNK = 100
```

**Benefits:**
- ✅ No truncated code in search results
- ✅ Full method context for understanding
- ✅ Embedding models handle large chunks well (1500+ tokens)
- ❌ Very large classes (2000+ lines) may be skipped

**Alternative approach:**
Store both full method + chunked version for best of both worlds (not yet implemented).

## Audio Transcription Feature

Audio files are automatically transcribed using **OpenAI Whisper Turbo** model:

**How it works:**
1. When ingesting audio files (MP3 supported currently), Docling uses Whisper ASR
2. Whisper generates accurate transcriptions with timestamps
3. Transcripts are formatted as markdown with time markers
4. Audio content becomes fully searchable through the RAG system

**Benefits:**
- 🎙️ **Speech-to-text**: Convert podcasts, interviews, lectures into searchable text
- ⏱️ **Timestamps**: Track when specific content was mentioned
- 🔍 **Semantic search**: Find audio content by topic or keywords
- 🤖 **Fully automatic**: Drop audio files in `documents/` folder and run ingestion

**Model details:**
- Model: `openai/whisper-large-v3-turbo`
- Optimized for: Speed and accuracy balance
- Languages: Multilingual support (90+ languages)
- Output format: Markdown with timestamps like `[time: 0.0-4.0] Transcribed text here`

**Example transcript format:**
```markdown
[time: 0.0-4.0] Welcome to our podcast on AI and machine learning.
[time: 5.28-9.96] Today we'll discuss retrieval augmented generation systems.
```

## Key Components

### RAG Agent

The main agent (`rag_agent.py`) that:
- Manages database connections with connection pooling
- Handles interactive CLI with streaming responses
- Performs knowledge base searches via RAG
- Tracks conversation history for context

### search_knowledge_base Tool

Function tool registered with the agent that:
- Generates query embeddings using OpenAI
- Searches using PGVector cosine similarity
- Returns top-k most relevant chunks
- Formats results with source citations

Example tool definition:
```python
async def search_knowledge_base(
    ctx: RunContext[None],
    query: str,
    limit: int = 5
) -> str:
    """Search the knowledge base using semantic similarity."""
    # Generate embedding for query
    # Search PostgreSQL with PGVector
    # Format and return results
```

### Database Schema

- `documents`: Stores original documents with metadata
  - `id`, `title`, `source`, `content`, `metadata`, `created_at`, `updated_at`

- `chunks`: Stores text chunks with vector embeddings
  - `id`, `document_id`, `content`, `embedding` (vector(1536)), `chunk_index`, `metadata`, `token_count`

- `match_chunks()`: PostgreSQL function for vector similarity search
  - Uses cosine similarity (`1 - (embedding <=> query_embedding)`)
  - Returns chunks with similarity scores above threshold

## Performance Optimization

### GPU Memory Management (Local Mode)

The system is configured for **hybrid performance** to match your KoboldCpp setup:
- **Embeddings**: Use GPU if available (CUDA), automatically falls back to CPU
- **LLM Inference**: Uses GPU via KoboldCpp (5-15 tokens/sec)
- **Result**: Optimized performance with automatic device detection

**Current Configuration:**
- ✅ **Embeddings**: CUDA if available, CPU fallback (all-MiniLM-L6-v2)
- ✅ **LLM Inference**: Uses GPU via KoboldCpp
- ✅ **Result**: Hybrid performance matching your KoboldCpp ReWiz-Phi-4-14B setup

**Performance Metrics** (on typical hardware):
- CPU embeddings: ~50-100 texts/sec
- **GPU embeddings: ~200-500 texts/sec** (if CUDA available)
- LLM inference (KoboldCpp): ~5-15 tokens/sec (GPU-bound)
- Hybrid GPU performance provides 3-5x faster embeddings than CPU

**Installing CUDA for GPU Embeddings:**
If you don't have CUDA-enabled PyTorch and want GPU embeddings:
```bash
# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Or for latest CUDA 12.4
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Reinstall environment
uv sync
```

**If you prefer CPU embeddings (to avoid GPU sharing):**
```bash
# Edit utils/providers.py line 136:
# Change: return LocalEmbeddingAsyncClient(device="cuda")
# To:     return LocalEmbeddingAsyncClient(device="cpu")

# Reinstall dependencies
uv sync
```

**Streaming Performance:**
If you notice `[BATCH]` mode in KoboldCpp instead of token-by-token streaming:
- This is normal for large prompts with long context
- The system performs automatic RAG search before generating responses
- Knowledge base context is prepended to your query (can be 2000+ tokens)
- KoboldCpp processes this as a batch, then streams the response
- Result is still streaming text output to you (see `Assistant: ...` with real-time tokens)

## Troubleshooting

### Multiprocess Cleanup Error After Ingestion
**Error**: `AttributeError: '_thread.RLock' object has no attribute '_recursion_count'`

**Cause**: Python 3.12+ multiprocess cleanup on Windows (harmless)

**Solution**: This error is cosmetic and doesn't affect functionality. The ingestion completes successfully despite the message. If you want to suppress it:
```bash
# Redirect stderr to null (Windows PowerShell)
uv run python -m ingestion.ingest 2>$null

# Or (Windows CMD)
uv run python -m ingestion.ingest 2>NUL

# Or (Linux/Mac)
uv run python -m ingestion.ingest 2>/dev/null
```

### `--no-clean` Flag Not Working
**Symptom**: Database gets cleared even when using `--no-clean`

**Status**: ✅ **FIXED!** The system now:
- Only processes folders that contain supported file types
- Preserves existing chunks when no new documents found
- Works correctly with `--no-clean` flag
- **Automatically skips duplicate documents** (checks by source path)

**Verify it's working**:
```bash
# First ingestion
uv run python -m ingestion.ingest --documents documents/

# Second ingestion - should skip all existing documents
uv run python -m ingestion.ingest --documents documents/
# Output: "⏭️  Skipping company-overview.md - already indexed..."

# Check stats to verify no duplicates
uv run python cli.py
You: stats
# Should show same chunk count as first ingestion
```

### Code Identifiers Not Found in Search
**Symptom**: "Do I have HomeController?" returns NO despite class existing

**Status**: ✅ **FIXED!** System now uses hybrid search (keyword + semantic)

**Previous behavior:**
- Pure semantic search: "HomeController" embedded as vector
- Low cosine similarity with "Do I have HomeController?" query
- Result: False negative

**Current behavior:**
- Extracts code pattern: `HomeController`
- Keyword search: `ILIKE '%HomeController%'`
- Returns 95% relevance match
- Result: ✅ Found with actual code

**Test it:**
```bash
uv run python test_all_fixes.py
# Tests all 6 improvements including hybrid search
```

### GPU 100% During Search/Inference
**Symptom**: GPU is maxed out when generating embeddings and inference

**Cause**: This is expected with hybrid GPU setup - both embeddings and LLM use GPU when available

**This is actually optimal!** Both GPU embeddings (200-500 texts/sec) and GPU LLM (5-15 tokens/sec) working together provide maximum speed, just like your KoboldCpp ReWiz-Phi-4-14B model shares GPU resources.

**Performance comparison:**
- GPU embeddings + GPU LLM = Fastest (your current setup if CUDA installed)
- CPU embeddings + GPU LLM = More GPU available for LLM, but slower search
- GPU embeddings + CPU LLM = CPU-bound, won't work well for GPU-optimized models

**To switch to CPU embeddings** (if you want to reduce GPU pressure):
1. Edit `utils/providers.py` line 136
2. Change: `LocalEmbeddingAsyncClient(device="cuda")` → `LocalEmbeddingAsyncClient(device="cpu")`
3. Run `uv sync`
4. Result: Slower embeddings (50-100 texts/sec) but 100% GPU for KoboldCpp LLM

**To verify GPU is being used**:
```bash
# Check current device being used (check logs during first run)
uv run python -m ingestion.ingest --no-clean 2>&1 | grep "device:"

# Monitor Windows Task Manager during inference:
# - Both "GPU" and "GPU Memory" should show activity
# - Your ReWiz model should be maximizing GPU utilization
```

### Streaming Shows [BATCH] Instead of Token-by-Token
**Symptom**: KoboldCpp logs show `Processing Prompt [BATCH] (1761 / 1761 tokens)` instead of streaming tokens

**This is expected behavior.** Here's why:
1. Your query: "Where is DiagnosticService defined?" (~10 tokens)
2. System performs RAG search automatically: "+1751 tokens of knowledge base context"
3. Total prompt: ~1761 tokens sent to KoboldCpp
4. KoboldCpp processes the large prompt in batch mode first (normal for LLMs)
5. Then streams response tokens back to you in real-time

**Compare with Continue extension**: 
- Continue might show different behavior because it processes shorter prompts or uses different context injection
- Your CLI system performs automatic RAG, which prepends search results making prompts larger
- Both approaches work correctly; the batch label is just KoboldCpp's internal detail

**Response still streams to you**: Even though KoboldCpp batches the prompt, the response tokens still stream one-by-one to your terminal. You'll see text appearing in real-time like:
```
Assistant: DiagnosticService is a backend service defined in DiagnosticService.cs...
```

**If you want smaller prompts to reduce batch size**:
1. Use fewer search results: Edit `cli.py` line 304 change `limit=5` to `limit=2`
   - Result: Smaller context but potentially less accurate answers
2. Or use smaller chunks: Edit `ingestion/chunker.py` reduce `chunk_size`
   - Trade-off: More chunks but smaller context snippets

**Note**: The [BATCH] label is just how KoboldCpp announces it's processing a large prompt. It's not a performance problem.

### Database Connection Issues
**Error**: `asyncpg.exceptions.CannotConnectNowError`

**Cause**: PostgreSQL container not running or network issue

**Solution**:
```bash
# Check if containers are running
docker ps

# Start containers if needed
docker-compose up -d

# Verify PostgreSQL is ready (wait 10-15 seconds for startup)
docker-compose logs postgres
```

### KoboldCpp Connection Failed
**Error**: `ConnectionError: Unable to connect to KoboldCpp at http://localhost:5001`

**Cause**: KoboldCpp server not running

**Solution**:
```bash
# KoboldCpp must be running separately
# Download from: https://github.com/LostRuins/koboldcpp
# Start with GPU: koboldcpp.exe --model your-model.gguf --port 5001

# Verify connection
curl http://localhost:5001/v1/models
```

### Out of Memory During Ingestion
**Error**: `MemoryError` or process killed

**Cause**: Large documents with aggressive chunking

**Solution**:
1. **Check chunk size** in `ingestion/chunker.py`:
   - Default chunk_size: 400-600 tokens
   - Reduce to 256-400 for large document batches

2. **Process in batches**:
   ```bash
   # Ingest documents in smaller batches
   uv run python -m ingestion.ingest --documents documents/batch1/ --no-clean
   uv run python -m ingestion.ingest --documents documents/batch2/ --no-clean
   ```

3. **Monitor RAM usage**:
   - Peak during embedding generation (sentence-transformers)
   - CPU embeddings use ~100-500MB per batch

### Slow Search Results
**Symptom**: Queries take 30+ seconds

**Possible causes**:
1. **Large vector database**: Many chunks can slow similarity search
   - Solution: Add database index on embeddings (already in schema.sql)

2. **CPU embeddings bottleneck**: If processing many queries
   - Solution: Switch to GPU embeddings (see GPU Memory Management above)
   - Trade-off: LLM will share GPU, may reduce inference speed

3. **Network latency**: KoboldCpp on different machine
   - Solution: Co-locate database + embeddings + KoboldCpp on same machine

### Missing Chunks in Search Results
**Symptom**: Documents were ingested but don't appear in search

**Cause**: Usually incorrect source path or chunking failure

**Solution**:
1. **Verify ingestion succeeded**:
   ```bash
   # Run with clean slate
   uv run python -m ingestion.ingest
   
   # Check CLI
   uv run python cli.py
   > stats
   ```

2. **Check document format**: Supported types are `.pdf, .docx, .md, .txt, .mp3` (with Whisper), etc.

3. **Review chunking**:
   - Very small documents might create fewer chunks
   - Very large documents are split across multiple chunks
   - Code files are parsed by language structure (tree-sitter)

### Database Database Schema Issues
**Error**: `relation "chunks" does not exist`

**Cause**: Schema not initialized in PostgreSQL

**Solution**:
```bash
# Apply schema
docker exec docling-postgres psql -U postgres -d docling_rag -f /docker-entrypoint-initdb.d/schema.sql

# Or manually in PostgreSQL:
psql -h localhost -U postgres -d docling_rag -f sql/schema.sql
```

### Database Migrations Failed
**Solution**: The schema auto-initializes via docker-compose volumes. If needed to reset:
```bash
# Stop and remove containers
docker-compose down

# Remove volume to reset database
docker volume rm docling-rag-agent_postgres_data

# Recreate
docker-compose up -d
```

### Performance Tuning

**For faster ingestion**:
- Use `device="cuda"` for embeddings (if GPU large enough)
- Increase chunk batch size in `embedder.py`
- Run embeddings in parallel processes

**For faster search**:
- Keep CPU free for embeddings (current config)
- Ensure GPU dedicated to KoboldCpp
- Use smaller LLM model if inference too slow

**For lower memory usage**:
- Reduce chunk size (256-400 tokens)
- Enable embedding cache (default: on)
- Process documents in smaller batches with `--no-clean`

### Database Connection Pooling

```python
db_pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=2,
    max_size=10,
    command_timeout=60
)
```

### Embedding Cache
The embedder includes built-in caching for frequently searched queries, reducing API calls and latency.

### Streaming Responses
Token-by-token streaming provides immediate feedback to users while the LLM generates responses:
```python
async with agent.run_stream(user_input, message_history=history) as result:
    async for text in result.stream_text(delta=False):
        print(f"\rAssistant: {text}", end="", flush=True)
```

## Testing the Improvements

A comprehensive test suite is included to verify all 6 new features:

### Run All Tests

```bash
# Test all 6 fixes
uv run python test_all_fixes.py
```

**Tests included:**

1. **Test Fix 2 & 3**: Search limit (20 results) + Line numbers
   - Verifies results show `:70` or `:13-72` format
   - Confirms 20 results returned
   - Checks for "more results" message

2. **Test Fix 4**: Follow-up context detection
   - Query: "Do I have HomeController?" → "show it"
   - Verifies vague reference detected
   - Confirms context added to follow-up

3. **Test Fix 6**: Source type ranking
   - Compares with/without `--rank-code-sources`
   - Verifies .cs files boosted to 99% relevance
   - Confirms re-sorting works

4. **Test Fix 1**: Duplicate prevention (informational)
   - Documents the duplicate check logic
   - Instructions to test manually with re-ingestion

5. **Test Fix 5**: Code chunk size (informational)
   - Documents `MAX_LINES_PER_CHUNK = None` config
   - Confirms complete methods preserved

### Expected Output

```bash
============================================================
TESTING ALL 6 FIXES
============================================================

============================================================
TEST: Fix 2 (Limit=20) and Fix 3 (Line Numbers)
============================================================
Query: Where is ErrorViewModel used?
✓ Line numbers ARE included in results
✓ Found 7 sources
✓ PASS: Returns multiple sources (≥3)

============================================================
TEST: Fix 4 (Follow-up Context)
============================================================
Query 1: Do I have HomeController?
Query 2: show it
Is follow-up detected: True
✓ PASS: Follow-up detected

============================================================
TEST: Fix 6 (Source Type Ranking)
============================================================
First source WITHOUT ranking: ErrorViewModel.cs (95%)
First source WITH ranking: ErrorViewModel.cs (99%)
✓ PASS: Code file boosted to top with ranking
```

### Manual Testing

**Test hybrid search:**
```bash
uv run python cli.py

You: Do I have HomeController in my code?
Expected: YES with Controllers\HomeController.cs:13-72

You: Where is ILogger used?
Expected: Multiple locations with line numbers
```

**Test follow-up context:**
```bash
You: Do I have DiagnosticService?
Expected: YES with file location

You: what methods does it have?
Expected: Method list (context remembered)
```

**Test duplicate prevention:**
```bash
# Run twice
uv run python -m ingestion.ingest --documents documents/
uv run python -m ingestion.ingest --documents documents/

# Second run should output:
# "⏭️  Skipping company-overview.md - already indexed"
```

**Test source ranking:**
```bash
# With code ranking enabled
uv run python cli.py --rank-code-sources

You: Where is ErrorViewModel defined?
Expected: Code files (.cs) appear first with 99% relevance
```

## Docker Deployment

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# Ingest documents
docker-compose --profile ingestion up ingestion

# View logs
docker-compose logs -f rag-agent
```

## API Reference

### search_knowledge_base_direct Function

```python
async def search_knowledge_base_direct(
    query: str,
    limit: int = 20,
    rank_code_sources: bool = False
) -> str:
    """
    Search the knowledge base using hybrid search (keyword + semantic).

    Args:
        query: The search query to find relevant information
        limit: Maximum number of results to return (default: 20, up from 5)
        rank_code_sources: Whether to boost code file relevance for code queries
                          (boosts .cs, .py, .ts, etc. by 10%)

    Returns:
        Formatted search results with source citations and line numbers
        
    Features:
        - Hybrid search: Keyword matching + semantic vector search
        - Line numbers: Shows :70 or :13-72 for code results
        - Pattern extraction: Detects PascalCase/CamelCase identifiers
        - Keyword-first: 95% relevance for exact matches
        - Semantic fallback: Cosine similarity for conceptual queries
    """
```

### search_knowledge_base Tool (Legacy)

```python
async def search_knowledge_base(
    ctx: RunContext[None],
    query: str,
    limit: int = 5
) -> str:
    """
    Legacy tool version for backward compatibility.
    Calls search_knowledge_base_direct internally.

    Note: May not work with all LLM backends (KoboldCpp).
    Direct RAG search is performed automatically in CLI.
    """
```

### Database Functions

```sql
-- Vector similarity search
SELECT * FROM match_chunks(
    query_embedding::vector(1536),
    match_count INT,
    similarity_threshold FLOAT DEFAULT 0.7
)
```

Returns chunks with:
- `id`: Chunk UUID
- `content`: Text content
- `embedding`: Vector embedding
- `similarity`: Cosine similarity score (0-1)
- `document_title`: Source document title
- `document_source`: Source document path

## Project Structure

```
docling-rag-agent/
├── cli.py                       # Enhanced CLI with hybrid search, line numbers, follow-up context
├── rag_agent.py                 # Basic CLI agent with PydanticAI (legacy)
├── test_all_fixes.py            # Test suite for 6 new improvements
├── ingestion/
│   ├── ingest.py                # Document ingestion pipeline (with duplicate prevention)
│   ├── embedder.py              # Embedding generation with caching
│   ├── chunker.py               # Document chunking logic (Docling HybridChunker)
│   └── code_indexer.py          # Source code indexing (tree-sitter, complete methods)
├── utils/
│   ├── providers.py             # OpenAI model/client configuration
│   ├── db_utils.py              # Database connection pooling
│   └── models.py                # Pydantic models for config
├── sql/
│   └── schema.sql               # PostgreSQL schema with PGVector
├── RAG_documents/               # Sample documents for ingestion
├── RAG_source_code/             # Source code files (optional, for code search)
├── pyproject.toml               # Project dependencies
├── .env.example                 # Environment variables template
├── docker-compose.yml           # Docker services (PostgreSQL with PGVector)
└── README.md                    # This file
```

**Key Files Updated (March 2026):**
- `cli.py` - Hybrid search, line numbers, follow-up context, ranking
- `ingestion/ingest.py` - Duplicate prevention (checks existing source paths)
- `ingestion/code_indexer.py` - Complete method preservation (MAX_LINES_PER_CHUNK = None)
- `test_all_fixes.py` - Comprehensive test suite for all improvements
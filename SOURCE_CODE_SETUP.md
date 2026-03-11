# Source Code Indexing with Tree-Sitter

## Overview

This guide explains how to add **searchable source code** to your RAG knowledge base using **tree-sitter**, a language-agnostic parsing library that understands 100+ programming languages.

### What is Tree-Sitter?

Tree-sitter is a fast, incremental parser that builds a concrete syntax tree for code. Unlike simple text splitting, it understands code structure and can extract:

- ✅ Functions and methods by name
- ✅ Classes and their members
- ✅ Signatures and docstrings
- ✅ Line numbers and file paths
- ✅ Language-specific syntax

**Result:** Your code becomes semantically searchable, not just text-searchable!

## Quick Start

### 1. Install Dependencies

First, install tree-sitter and language grammars:

```bash
# Update dependencies
uv sync
```

This automatically installs:
- `tree-sitter` - Core library
- `tree-sitter-python` - Python support
- `tree-sitter-javascript` - JavaScript/Node.js
- `tree-sitter-typescript` - TypeScript
- `tree-sitter-c-sharp` - C#/.NET
- `tree-sitter-java` - Java
- `tree-sitter-cpp` - C/C++
- `tree-sitter-go` - Go
- `tree-sitter-rust` - Rust

### 2. Create Source Code Folder

```bash
# Create a dedicated source_code folder
mkdir source_code

# Copy your source files (or link them)
# Example: Copy your Python project
cp -r ../my_project/*.py source_code/

# Or create a symbolic link (for large repos)
# ln -s /path/to/your/project source_code
```

### 3. Index Source Code

**Option A: Index code + documents together**

```bash
# Ingest both documents and source code
uv run python -m ingestion.ingest --documents documents/ --source-code source_code/
```

**Option B: Index only source code (add to existing knowledge base)**

```bash
# Add code without clearing existing documents
uv run python -m ingestion.ingest --source-code source_code/ --no-clean
```

**Option C: Index with custom chunk size**

```bash
uv run python -m ingestion.ingest --source-code source_code/ --no-clean --chunk-size 800
```

### 4. Test It!

Start the CLI and search for code:

```bash
uv run python cli.py
```

Then ask questions like:

```
You: Where is the upload_file function defined?
🤖 Assistant: The upload_file function is defined in src/api.py at line 145:

[FUNCTION_DEFINITION] upload_file
def upload_file(file_path: str, bucket: str) -> dict:
    """Upload a file to cloud storage."""
    ...

[Found in source_code/api.py:145-178]

You: Show me the Authentication class
🤖 Assistant: The Authentication class is defined in src/auth.py:

[CLASS_DEFINITION] Authentication
class Authentication:
    """Handles user authentication and token management."""
    
    def __init__(self, provider: str):
        ...
```

## How It Works

### 1. **File Discovery**
The indexer automatically finds all supported source files in `source_code/` folder:

```
source_code/
├── src/
│   ├── main.py          ✅ Indexed
│   ├── utils.py         ✅ Indexed
│   └── __pycache__/     ❌ Skipped
├── tests/
│   └── test_main.py     ✅ Indexed
└── node_modules/        ❌ Skipped
```

### 2. **Language Detection**
Files are recognized by extension:

| Extension | Language | Parser |
|-----------|----------|--------|
| `.py` | Python | tree-sitter-python |
| `.js`, `.jsx` | JavaScript | tree-sitter-javascript |
| `.ts`, `.tsx` | TypeScript | tree-sitter-typescript |
| `.cs` | C# | tree-sitter-c-sharp |
| `.java` | Java | tree-sitter-java |
| `.cpp`, `.cc` | C++ | tree-sitter-cpp |
| `.c` | C | tree-sitter-c |
| `.go` | Go | tree-sitter-go |
| `.rs` | Rust | tree-sitter-rust |

### 3. **Semantic Parsing**
Each file is parsed into a syntax tree, and semantic units are extracted:

```python
# Example Python file: src/api.py

def authenticate(username: str) -> bool:
    """Authenticate user."""
    ...

class APIHandler:
    """Main API handler class."""
    
    def __init__(self):
        ...
    
    def handle_request(self, req):
        ...
```

**Becomes 3 searchable chunks:**

1. `[FUNCTION] authenticate` → Line 1-5
2. `[CLASS] APIHandler` → Line 7-15  
3. `[METHOD] handle_request` → Line 10-14

### 4. **Embedding & Storage**
Each chunk is:
- ✅ Converted to text: `[FUNCTION] authenticate\ndef authenticate(username: str) -> bool:\n...`
- ✅ Embedded using sentence-transformers (local, fast, free)
- ✅ Stored in PostgreSQL with vector metadata
- ✅ Searchable via semantic similarity

## Examples

### Example 1: Search Python Functions

```bash
You: Find the add_user function

🤖 Assistant: Found add_user function in src/users.py (line 42):

[FUNCTION] add_user
async def add_user(username: str, email: str) -> User:
    """Create a new user account.
    
    Args:
        username: User login name
        email: User email address
    
    Returns:
        New User object
    """
    # Implementation...
```

### Example 2: Find C# Classes

```bash
You: Show me the DatabaseConnector class

🤖 Assistant: Found DatabaseConnector in src/Database.cs:

[CLASS] DatabaseConnector
public class DatabaseConnector
{
    private string connectionString;
    
    public DatabaseConnector(string connStr)
    {
        connectionString = connStr;
    }
    
    public void Connect()
    {
        // Implementation...
    }
}

[Located in source_code/Database.cs:12-45]
```

### Example 3: Mixed Document + Code Search

```bash
You: What authentication methods are available?

🤖 Assistant: The knowledge base includes:

From documentation (handbook.pdf):
- OAuth 2.0 integration
- JWT token support
- API key authentication

From source code:
- Authentication class in src/auth.py (line 89)
- authenticate() function in src/api.py (line 145)  
- verify_token() method in src/middleware.py (line 203)

[Shows relevant code snippets and documentation]
```

## Configuration

### Excluding Folders

By default, these folders are excluded:

```python
exclude_patterns = [
    '__pycache__',
    'node_modules',
    '.git',
    '.venv',
    'venv',
    'dist',
    'build',
]
```

To exclude more, edit `source_code/` folder structure to avoid unwanted files.

### File Extensions

Only these extensions are indexed by default:

```python
extensions = [
    '.py',        # Python
    '.js', '.jsx', # JavaScript
    '.ts', '.tsx', # TypeScript
    '.cs',         # C#
    '.java',       # Java
    '.cpp', '.cc', '.h',  # C++
    '.c',          # C
    '.go',         # Go
    '.rs',         # Rust
]
```

## Troubleshooting

### "tree-sitter not found" Error

```bash
# Reinstall dependencies
uv sync --refresh
```

### Language not supported

Tree-sitter supports 100+ languages. If your language isn't listed:

1. **Check tree-sitter-awesome** for available grammars: https://github.com/tree-sitter/tree-sitter/wiki/List-of-parsers
2. **Install manually** (advanced): See `code_indexer.py` for how to add new languages
3. **Fallback to text chunking** - Files without a grammar are chunked as plain text

### "No code chunks found"

Check:

```bash
# 1. Verify source_code folder exists
ls -la source_code/

# 2. Verify files are supported extensions
find source_code/ -type f

# 3. Check ingestion logs
uv run python -m ingestion.ingest --source-code source_code/ -v 2>&1 | grep -i error
```

## Advanced: Adding New Languages

To add support for a new language:

1. **Find the grammar package** on PyPI (e.g., `tree-sitter-java`)
2. **Update pyproject.toml**:
   ```toml
   dependencies = [
       ...
       "tree-sitter-java>=0.21.1",  # New language
   ]
   ```
3. **Update code_indexer.py** - Add to `SUPPORTED_LANGUAGES` dict:
   ```python
   SUPPORTED_LANGUAGES = {
       ...
       'java': ('java', ['method_declaration', 'class_declaration']),
   }
   ```
4. **Run `uv sync` and test**:
   ```bash
   uv sync
   uv run python -m ingestion.ingest --source-code source_code/ --no-clean
   ```

## Performance Tips

### Large Codebases

If indexing a large project (1000+ files):

1. **Use symbolic links** instead of copying:
   ```bash
   rm -rf source_code
   ln -s /path/to/huge/project source_code
   ```

2. **Index once, use many times** - Once indexed, searches are instant

3. **Run with verbose logging** to monitor progress:
   ```bash
   uv run python -m ingestion.ingest --source-code source_code/ -v
   ```

### Memory Usage

Tree-sitter is very efficient. For reference:
- 10,000 chunks → ~500MB RAM
- 100,000 chunks → ~2GB RAM

If memory is tight, index incrementally:
```bash
# Index one subdirectory at a time
uv run python -m ingestion.ingest --source-code source_code/src/ --no-clean
uv run python -m ingestion.ingest --source-code source_code/lib/ --no-clean
```

## Architecture

```
source_code/                         # Your source files
    ├── main.py
    ├── utils/auth.py
    └── models/user.py
         ↓
    [CodeIndexer]                    # tree-sitter parsing
         ↓
    [CodeChunk objects]              # Functions, classes, methods
    ├── content (source code)
    ├── kind (function/class/method)
    ├── name (function/class name)
    ├── language (Python/JS/etc)
    └── metadata (line numbers, signatures)
         ↓
    [EmbeddingGenerator]             # sentence-transformers
         ↓
    [PostgreSQL + PGVector]          # Vector database
         ↓
    [CLI RAG Search]                 # Semantic similarity search
```

## Summary

| Feature | Document RAG | Code RAG | Combined |
|---------|-------------|----------|----------|
| **Formats** | PDF, Word, Markdown, Audio | Python, JS, C#, Java, C++, Rust, Go | All! |
| **Chunking** | Content-based | Semantic (functions, classes) | Smart |
| **Search** | "Tell me about SKI" | "Where is SkiInit defined?" | Both! |
| **Sources** | `documents/` folder | `source_code/` folder | Unified DB |
| **Use Case** | Company docs, handbooks | Codebases, repositories | **Everything!** |

---

**Next:** Run `uv run python cli.py` and start asking questions about your code! 🚀

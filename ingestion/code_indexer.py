"""
Source code indexing using tree-sitter for semantic code chunking.

Supports 100+ programming languages including Python, C#, C, C++, JavaScript, etc.
Chunks code by semantic units (functions, classes, methods) rather than line counts.

Chunking Strategy:
- Extracts COMPLETE methods/functions/classes (no splitting by size)
- Preserves entire code structure for better context
- For very large classes (>2000 lines), only individual methods are extracted
- No artificial token limits - embedding model handles large chunks
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import re

logger = logging.getLogger(__name__)


# Configuration: Code chunk size strategy
# Set to None to extract complete methods/functions (recommended)
# Set to an integer to limit max lines per chunk (will split large methods)
MAX_LINES_PER_CHUNK = None  # None = complete methods, or set to e.g., 100 for splitting


class CodeChunk:
    """Represents a semantic chunk of source code."""
    
    def __init__(
        self,
        content: str,
        kind: str,  # 'function', 'class', 'method', etc.
        name: str,
        language: str,
        file_path: str,
        start_line: int,
        end_line: int,
        metadata: Dict[str, Any] = None
    ):
        """
        Initialize a code chunk.
        
        Args:
            content: The source code content
            kind: Type of code block (function, class, method, etc.)
            name: Name of the function/class
            language: Programming language
            file_path: Path to source file
            start_line: Starting line number
            end_line: Ending line number
            metadata: Additional metadata (signatures, docstrings, etc.)
        """
        self.content = content
        self.kind = kind
        self.name = name
        self.language = language
        self.file_path = file_path
        self.start_line = start_line
        self.end_line = end_line
        self.metadata = metadata or {}
    
    def __repr__(self) -> str:
        return f"CodeChunk({self.kind} {self.name} @ {self.file_path}:{self.start_line})"


class CodeIndexer:
    """
    Semantic code indexer using tree-sitter for language-aware parsing.
    
    Features:
    - Language-aware parsing using tree-sitter (100+ languages supported)
    - Extracts functions, classes, methods as semantic chunks
    - Preserves code structure and context
    - Includes metadata like signatures and docstrings
    """
    
    # Supported languages with their tree-sitter grammar names
    SUPPORTED_LANGUAGES = {
        'py': ('python', ['function_definition', 'class_definition']),
        'js': ('javascript', ['function_declaration', 'class_declaration']),
        'ts': ('typescript', ['function_declaration', 'class_declaration']),
        'cs': ('c_sharp', ['method_declaration', 'class_declaration']),
        'java': ('java', ['method_declaration', 'class_declaration']),
        'cpp': ('cpp', ['function_definition', 'class_specification']),
        'c': ('c', ['function_definition', 'struct_specifier']),
        'go': ('go', ['function_declaration']),
        'rs': ('rust', ['function_item', 'struct_item']),
        'rb': ('ruby', ['method']),
    }
    
    def __init__(self):
        """Initialize the code indexer."""
        self._init_tree_sitter()
        logger.info("CodeIndexer initialized")
    
    def _init_tree_sitter(self) -> None:
        """Initialize tree-sitter library."""
        try:
            import tree_sitter
            self.ts = tree_sitter
            self.Language = tree_sitter.Language
            self.Parser = tree_sitter.Parser
            logger.info("tree-sitter initialized successfully")
        except ImportError:
            raise ImportError(
                "tree-sitter is required for code indexing. Install with:\n"
                "pip install tree-sitter\n"
                "Then install language grammars: pip install tree-sitter-python tree-sitter-javascript etc."
            )
    
    def get_language_parser(self, language: str) -> Optional[object]:
        """
        Get parser for a specific programming language.
        
        Args:
            language: Language name (e.g., 'python', 'javascript')
            
        Returns:
            Parser object or None if language not supported
        """
        try:
            # Import language-specific grammar and wrap in Language class
            module_name = f"tree_sitter_{language.lower()}"
            module = __import__(module_name, fromlist=['language'])
            lang_func = module.language
            
            # Call the language function to get capsule, then wrap in Language class
            if callable(lang_func):
                lang = self.Language(lang_func())
            else:
                # Fallback if it's already a Language object
                lang = self.Language(lang_func)
            
            parser = self.Parser()
            parser.language = lang
            return parser
        except ImportError:
            logger.warning(f"Language grammar not found: {language}")
            return None
        except Exception as e:
            logger.warning(f"Failed to load language {language}: {e}")
            return None
    
    def index_file(
        self,
        file_path: str,
        language: Optional[str] = None
    ) -> List[CodeChunk]:
        """
        Index a source code file into semantic chunks.
        
        Args:
            file_path: Path to source file
            language: Optional language override (auto-detect from extension if not provided)
            
        Returns:
            List of CodeChunk objects
        """
        path = Path(file_path)
        
        # Auto-detect language from extension
        if not language:
            ext = path.suffix.lstrip('.').lower()
            if ext not in self.SUPPORTED_LANGUAGES:
                logger.warning(f"Unsupported file extension: .{ext}")
                return []
            language = self.SUPPORTED_LANGUAGES[ext][0]
        
        # Read file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source_code = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return []
        
        # Get parser
        parser = self.get_language_parser(language)
        if not parser:
            logger.warning(f"No parser for language: {language}. Treating as plain text.")
            return self._create_text_chunks(source_code, file_path, language)
        
        # Parse and extract chunks
        try:
            tree = parser.parse(source_code.encode('utf-8'))
            chunks = self._extract_chunks(
                tree,
                source_code,
                file_path,
                language
            )
            logger.info(f"Indexed {file_path}: {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return []
    
    def _extract_chunks(
        self,
        tree: Any,
        source_code: str,
        file_path: str,
        language: str
    ) -> List[CodeChunk]:
        """
        Extract semantic chunks from parsed code tree.
        
        Args:
            tree: Parsed tree-sitter syntax tree
            source_code: Original source code
            file_path: Path to source file
            language: Programming language
            
        Returns:
            List of CodeChunk objects
        """
        chunks = []
        lines = source_code.split('\n')
        
        # Define node types to extract based on language
        extract_types = self._get_extract_types(language)
        
        def traverse(node: Any) -> None:
            """Recursively traverse tree and extract chunks."""
            if node.type in extract_types:
                chunk = self._create_chunk_from_node(
                    node,
                    source_code,
                    file_path,
                    language,
                    lines
                )
                if chunk:
                    chunks.append(chunk)
            
            for child in node.children:
                traverse(child)
        
        traverse(tree.root_node)
        return chunks
    
    def _get_extract_types(self, language: str) -> set:
        """Get node types to extract for a language."""
        type_map = {
            'python': {
                'function_definition',
                'class_definition',
                'async_function_definition',
            },
            'javascript': {
                'function_declaration',
                'class_declaration',
                'method_definition',
            },
            'typescript': {
                'function_declaration',
                'class_declaration',
                'method_definition',
            },
            'c_sharp': {
                'method_declaration',
                'class_declaration',
                'interface_declaration',
            },
            'java': {
                'method_declaration',
                'class_declaration',
            },
            'cpp': {
                'function_definition',
                'class_specifier',
                'struct_specifier',
            },
            'c': {
                'function_definition',
                'struct_specifier',
            },
            'go': {
                'function_declaration',
                'method_declaration',
            },
            'rust': {
                'function_item',
                'struct_item',
                'impl_item',
            },
        }
        return type_map.get(language, set())
    
    def _create_chunk_from_node(
        self,
        node: Any,
        source_code: str,
        file_path: str,
        language: str,
        lines: List[str]
    ) -> Optional[CodeChunk]:
        """
        Create a CodeChunk from a tree-sitter node.
        
        Args:
            node: tree-sitter node
            source_code: Original source code
            file_path: Path to file
            language: Programming language
            lines: Source code split by lines
            
        Returns:
            CodeChunk object or None if extraction fails
        """
        try:
            # Extract content
            start_byte = node.start_byte
            end_byte = node.end_byte
            content = source_code[start_byte:end_byte]
            
            # Get line numbers (0-indexed from tree-sitter, convert to 1-indexed)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            
            # Check if chunk exceeds max lines (if limit is set)
            if MAX_LINES_PER_CHUNK is not None:
                chunk_lines = end_line - start_line + 1
                if chunk_lines > MAX_LINES_PER_CHUNK:
                    logger.debug(f"Skipping large chunk {name} ({chunk_lines} lines) - exceeds MAX_LINES_PER_CHUNK={MAX_LINES_PER_CHUNK}")
                    # Note: Could split here if needed, but for now we skip very large chunks
                    # Most methods/functions should be reasonably sized
                    return None
            
            # Extract name
            kind = node.type
            name = self._extract_name_from_node(node, source_code, language)
            
            if not name:
                return None
            
            # Extract metadata
            metadata = self._extract_metadata(node, content, language)
            
            return CodeChunk(
                content=content,
                kind=kind,
                name=name,
                language=language,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                metadata=metadata
            )
        except Exception as e:
            logger.debug(f"Failed to create chunk from node: {e}")
            return None
    
    def _extract_name_from_node(
        self,
        node: Any,
        source_code: str,
        language: str
    ) -> Optional[str]:
        """
        Extract function/class name from node.
        
        Args:
            node: tree-sitter node
            source_code: Original source code
            language: Programming language
            
        Returns:
            Name string or None
        """
        # Find the name child node (usually an 'identifier' node)
        for child in node.children:
            if child.type in ('identifier', 'type_identifier', 'property_identifier'):
                start = child.start_byte
                end = child.end_byte
                return source_code[start:end].strip()
        
        return None
    
    def _extract_metadata(
        self,
        node: Any,
        content: str,
        language: str
    ) -> Dict[str, Any]:
        """
        Extract metadata from code node (docstrings, signatures, etc.).
        
        Args:
            node: tree-sitter node
            content: Node content
            language: Programming language
            
        Returns:
            Metadata dictionary
        """
        metadata = {'language': language}
        
        # Extract docstring/comment
        docstring = self._extract_docstring(content, language)
        if docstring:
            metadata['docstring'] = docstring
        
        # Extract signature (first line typically)
        lines = content.split('\n')
        if lines:
            metadata['signature'] = lines[0].strip()
        
        return metadata
    
    def _extract_docstring(self, content: str, language: str) -> Optional[str]:
        """
        Extract docstring/documentation from code content.
        
        Args:
            content: Code content
            language: Programming language
            
        Returns:
            Docstring or None
        """
        lines = content.split('\n')
        
        docstring_patterns = {
            'python': (r'"""', r"'''"),
            'javascript': (r'/\*\*', r'//'),
            'java': (r'/\*\*', r'//'),
            'c': (r'/\*', r'//'),
            'cpp': (r'/\*', r'//'),
        }
        
        patterns = docstring_patterns.get(language, ())
        
        for i, line in enumerate(lines[1:3]):  # Check first few lines
            for pattern in patterns:
                if re.search(pattern, line):
                    # Found documentation, extract a few lines
                    return '\n'.join(lines[1:min(4, len(lines))])
        
        return None
    
    def _create_text_chunks(
        self,
        content: str,
        file_path: str,
        language: str,
        chunk_size: int = 50
    ) -> List[CodeChunk]:
        """
        Fall back to simple text chunking if language not supported.
        
        Args:
            content: File content
            file_path: Path to file
            language: Programming language
            chunk_size: Lines per chunk
            
        Returns:
            List of CodeChunk objects
        """
        chunks = []
        lines = content.split('\n')
        
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk_content = '\n'.join(chunk_lines)
            
            chunks.append(CodeChunk(
                content=chunk_content,
                kind='text_block',
                name=f"{Path(file_path).stem}_lines_{i+1}",
                language=language,
                file_path=file_path,
                start_line=i + 1,
                end_line=min(i + chunk_size, len(lines)),
                metadata={'type': 'fallback_text_chunking'}
            ))
        
        return chunks
    
    def index_directory(
        self,
        directory: str,
        extensions: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[CodeChunk]:
        """
        Index all source files in a directory.
        
        Args:
            directory: Directory path to index
            extensions: List of file extensions to include (e.g., ['.py', '.js'])
            exclude_patterns: List of patterns to exclude (e.g., ['__pycache__', 'node_modules'])
            
        Returns:
            List of all CodeChunk objects found
        """
        if not extensions:
            extensions = [f'.{ext}' for ext in self.SUPPORTED_LANGUAGES.keys()]
        
        if not exclude_patterns:
            exclude_patterns = ['__pycache__', 'node_modules', '.git', '.venv', 'venv']
        
        chunks = []
        
        for root, dirs, files in os.walk(directory):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if not any(p in d for p in exclude_patterns)]
            
            for file in files:
                file_path = os.path.join(root, file)
                
                # Check if extension matches
                if not any(file.endswith(ext) for ext in extensions):
                    continue
                
                logger.debug(f"Indexing {file_path}")
                file_chunks = self.index_file(file_path)
                chunks.extend(file_chunks)
        
        logger.info(f"Indexed directory {directory}: {len(chunks)} chunks")
        return chunks

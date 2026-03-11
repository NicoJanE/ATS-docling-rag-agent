#!/usr/bin/env python3
"""
Command Line Interface for Docling RAG Agent.

Enhanced CLI with colors, formatting, and improved user experience.
"""

import asyncio
import asyncpg
import argparse
import logging
import os
import sys
from typing import List, Dict, Any
from datetime import datetime

# Fix Unicode encoding on Windows - enable UTF-8 output
if sys.platform == "win32":
    import io
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

# Load environment variables FIRST
load_dotenv(".env", override=True)

logger = logging.getLogger(__name__)

# Configure for KoboldCpp or OpenAI
openai_api_base = os.getenv("OPENAI_API_BASE")
if openai_api_base:
    os.environ["OPENAI_API_BASE"] = openai_api_base

# ANSI color codes for better formatting
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


# Global database pool
db_pool = None


async def initialize_db():
    """Initialize database connection pool."""
    global db_pool
    if not db_pool:
        db_pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL"),
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        # logger.info("Database connection pool initialized")


async def close_db():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        # logger.info("Database connection pool closed")


def _categorize_reference(content: str, source_path: str, metadata: Dict[str, Any]) -> str:
    """Categorize a code reference by its usage type.
    
    Args:
        content: The chunk content
        source_path: File path of the source
        metadata: Metadata dictionary with additional context
        
    Returns:
        Category string (DEFINITION, INSTANTIATION, METHOD_CALL, etc.)
    """
    content_lower = content.lower()
    source_lower = source_path.lower() if source_path else ""
    
    # Detect code file types
    is_code_file = any(source_lower.endswith(ext) for ext in ['.cs', '.py', '.ts', '.js', '.java', '.cpp', '.c', '.go', '.rs', '.rb', '.php'])
    is_test_file = 'test' in source_lower or 'spec' in source_lower
    is_view_file = source_lower.endswith(('.cshtml', '.razor', '.vue', '.jsx', '.tsx', '.html'))
    is_config_file = source_lower.endswith(('.json', '.yml', '.yaml', '.xml', '.config', '.toml'))
    is_doc_file = source_lower.endswith(('.md', '.txt', '.rst', '.adoc'))
    
    # Check for specific patterns in content
    has_class_keyword = any(kw in content_lower for kw in ['public class', 'class ', 'private class', 'internal class', 'abstract class'])
    has_interface_keyword = any(kw in content_lower for kw in ['public interface', 'interface ', 'private interface'])
    has_method_def = any(kw in content for kw in ['public ', 'private ', 'protected ', 'def ', 'function ', 'async def'])
    has_instantiation = any(kw in content for kw in [' new ', 'new(', '()', 'create(', 'Create('])
    has_dbset = 'dbset<' in content_lower or 'dbcontext' in content_lower
    has_model_directive = '@model' in content_lower
    has_import = any(kw in content_lower for kw in ['import ', 'using ', 'require(', 'from ', '#include'])
    has_comment = content.strip().startswith(('//','#', '/*', '<!--', '"""', "'''"))
    
    # Categorization logic (order matters - most specific first)
    
    # Class/Interface Definitions
    if has_class_keyword and '[class_declaration]' in content_lower:
        return 'DEFINITION'
    if has_interface_keyword:
        return 'DEFINITION'
    
    # Database Registration
    if has_dbset and is_code_file:
        return 'DATABASE_REGISTRATION'
    
    # View Models
    if has_model_directive and is_view_file:
        return 'VIEW_MODEL'
    
    # Imports/Using statements
    if has_import and not has_method_def:
        return 'IMPORT'
    
    # Test Usage
    if is_test_file and is_code_file:
        return 'TEST_USAGE'
    
    # Instantiation (new keyword)
    if has_instantiation and not has_class_keyword:
        return 'INSTANTIATION'
    
    # Method definitions
    if has_method_def and '[method_declaration]' in content_lower:
        return 'METHOD_DEFINITION'
    
    # Method calls
    if '(' in content and ')' in content and is_code_file and not has_class_keyword:
        return 'METHOD_CALL'
    
    # Configuration
    if is_config_file:
        return 'CONFIGURATION'
    
    # Documentation
    if is_doc_file:
        return 'DOCUMENTATION'
    
    # Comments/Documentation in code
    if has_comment and len(content) < 500:
        return 'COMMENT'
    
    # Property/Field Access
    if '.' in content and is_code_file:
        return 'PROPERTY_ACCESS'
    
    # Default fallback
    return 'REFERENCE'


def _smart_truncate_code(content: str, query: str, max_lines: int = 10) -> str:
    """Intelligently truncate code to show relevant parts.
    
    Shows:
    - First few lines (class/method signature)
    - "..." 
    - Lines containing search terms
    - Closing braces
    
    Args:
        content: The code content to truncate
        query: Search query to find relevant lines
        max_lines: Maximum lines to show (default: 10)
        
    Returns:
        Truncated content with relevant parts
    """
    lines = content.split('\n')
    
    # Extract search terms for finding relevant lines
    import re
    # Get PascalCase/CamelCase identifiers (actual code terms like ErrorViewModel, HomeController)
    code_identifiers = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
    code_identifiers = list(set([term for term in code_identifiers if len(term) >= 3]))
    
    # If content is short enough, show all lines but still apply highlighting
    if len(lines) <= max_lines:
        highlighted_lines = []
        for line in lines:
            highlighted_line = line
            # Only highlight actual code identifiers (PascalCase/CamelCase names)
            for term in code_identifiers:
                pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
                highlighted_line = pattern.sub(
                    lambda m: f"{Colors.GREEN}{m.group()}{Colors.END}",
                    highlighted_line
                )
            highlighted_lines.append(highlighted_line)
        return '\n'.join(highlighted_lines)
    
    # For finding relevant lines, also include other query words
    all_search_terms = code_identifiers.copy()
    all_search_terms.extend([word for word in query.lower().split() if len(word) >= 4])
    
    # Find lines containing search terms (case-insensitive)
    relevant_lines = set()
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for term in all_search_terms:
            if term.lower() in line_lower:
                # Include this line and 1 line of context before/after
                relevant_lines.add(max(0, i - 1))
                relevant_lines.add(i)
                relevant_lines.add(min(len(lines) - 1, i + 1))
    
    # Always include first few lines (class/method signature)
    header_lines = min(4, len(lines))
    for i in range(header_lines):
        relevant_lines.add(i)
    
    # Find closing braces at the end
    closing_lines = []
    for i in range(len(lines) - 1, max(len(lines) - 3, 0), -1):
        if lines[i].strip() in ['}', '};', '})', '};)']:
            closing_lines.append(i)
    
    # Build truncated output
    relevant_sorted = sorted(relevant_lines)
    output_lines = []
    last_included = -1
    
    for line_num in relevant_sorted:
        # Add ellipsis if there's a gap
        if last_included >= 0 and line_num > last_included + 1:
            output_lines.append('   ...')
        output_lines.append(lines[line_num])
        last_included = line_num
    
    # Add closing braces if we haven't included the end
    if last_included < len(lines) - 1:
        if closing_lines:
            if last_included < closing_lines[-1] - 1:
                output_lines.append('   ...')
            for close_line in reversed(closing_lines):
                if close_line > last_included:
                    output_lines.append(lines[close_line])
        else:
            output_lines.append('   ...')
    
    # Highlight only code identifiers (PascalCase terms) in green, not common words
    highlighted_lines = []
    for line in output_lines:
        highlighted_line = line
        # Don't highlight ellipsis lines
        if line.strip() != '...':
            # Only highlight actual code identifiers (PascalCase/CamelCase names)
            for term in code_identifiers:
                # Use word boundary to avoid partial matches
                pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
                highlighted_line = pattern.sub(
                    lambda m: f"{Colors.GREEN}{m.group()}{Colors.END}",
                    highlighted_line
                )
        highlighted_lines.append(highlighted_line)
    
    return '\n'.join(highlighted_lines)


def _format_categorized_results(results: List[Dict[str, Any]], query: str, full_code: bool = False) -> str:
    """Format search results with categorization and hierarchy.
    
    Args:
        results: List of search result dictionaries
        query: Original search query
        full_code: If False, intelligently truncate code to show relevant parts (default: False)
        
    Returns:
        Formatted string with categorized and hierarchical results
    """
    # Category configuration with icons and display names
    category_config = {
        'DEFINITION': {'icon': '📘', 'name': 'CLASS/INTERFACE DEFINITIONS', 'priority': 1},
        'METHOD_DEFINITION': {'icon': '🔵', 'name': 'METHOD DEFINITIONS', 'priority': 2},
        'DATABASE_REGISTRATION': {'icon': '🗄️', 'name': 'DATABASE REGISTRATION', 'priority': 3},
        'INSTANTIATION': {'icon': '🎯', 'name': 'INSTANTIATION', 'priority': 4},
        'METHOD_CALL': {'icon': '📞', 'name': 'METHOD CALLS', 'priority': 5},
        'PROPERTY_ACCESS': {'icon': '🔗', 'name': 'PROPERTY ACCESS', 'priority': 6},
        'VIEW_MODEL': {'icon': '📄', 'name': 'VIEW MODELS', 'priority': 7},
        'IMPORT': {'icon': '📦', 'name': 'IMPORTS/USING', 'priority': 8},
        'TEST_USAGE': {'icon': '🧪', 'name': 'TEST USAGE', 'priority': 9},
        'CONFIGURATION': {'icon': '⚙️', 'name': 'CONFIGURATION', 'priority': 10},
        'DOCUMENTATION': {'icon': '📚', 'name': 'DOCUMENTATION', 'priority': 11},
        'COMMENT': {'icon': '💬', 'name': 'COMMENTS', 'priority': 12},
        'REFERENCE': {'icon': '🔍', 'name': 'OTHER REFERENCES', 'priority': 13}
    }
    
    # Categorize all results
    categorized = {}
    for result in results:
        content = result.get('content', '')
        source = result.get('document_source', '')
        metadata = result.get('metadata', {})
        
        category = _categorize_reference(content, source, metadata)
        
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(result)
    
    # Build formatted output
    output_parts = []
    
    # Sort categories by priority
    sorted_categories = sorted(
        categorized.items(),
        key=lambda x: category_config.get(x[0], {'priority': 99})['priority']
    )
    
    for category, cat_results in sorted_categories:
        config = category_config.get(category, {'icon': '•', 'name': category})
        icon = config['icon']
        name = config['name']
        count = len(cat_results)
        
        # Category header
        output_parts.append(f"\n{icon} **{name}** ({count} location{'s' if count != 1 else ''})")
        
        # Format each result in this category
        for i, row in enumerate(cat_results):
            # Tree characters
            is_last = (i == len(cat_results) - 1)
            prefix = '└─' if is_last else '├─'
            
            # Source info
            doc_title = row.get('document_title', 'Unknown')
            doc_source = row.get('document_source', '')
            metadata_raw = row.get('metadata', {})
            similarity = row.get('similarity', 0)
            
            # Parse metadata
            import json
            if isinstance(metadata_raw, str):
                try:
                    metadata = json.loads(metadata_raw)
                except:
                    metadata = {}
            else:
                metadata = metadata_raw or {}
            
            # Build source line
            source_str = f"{prefix} "
            if doc_source:
                source_str += doc_source
            else:
                source_str += doc_title
            
            # Add line numbers
            if 'start_line' in metadata and 'end_line' in metadata:
                start_line = metadata['start_line']
                end_line = metadata['end_line']
                if start_line == end_line:
                    source_str += f":{start_line}"
                else:
                    source_str += f":{start_line}-{end_line}"
            
            source_str += f" (relevance: {similarity:.0%})"
            
            output_parts.append(source_str)
            
            # Add content (indented)
            content = row.get('content', '')
            
            # Smart truncation if not full_code mode
            if not full_code:
                content = _smart_truncate_code(content, query, max_lines=10)
            
            # Add proper indentation for continuation lines
            indent = '   ' if is_last else '│  '
            output_parts.append(f"{indent}{content}\n")
    
    # Summary
    total_results = len(results)
    category_summary = ', '.join([f"{len(cats)} {cat.lower().replace('_', ' ')}" for cat, cats in sorted_categories])
    output_parts.append(f"\n**Summary**: {total_results} total results across {len(categorized)} categories")
    output_parts.append(f"**Breakdown**: {category_summary}")
    
    return '\n'.join(output_parts)


async def search_knowledge_base_direct(query: str, limit: int = 20, rank_code_sources: bool = False, full_code: bool = False) -> str:
    """
    Search the knowledge base using hybrid search (keyword + semantic).
    This is called automatically before LLM response.

    Args:
        query: The search query to find relevant information
        limit: Maximum number of results to return (default: 20)
        rank_code_sources: Whether to boost code file relevance for code queries (default: False)
        full_code: If False, intelligently truncate code to show signature + relevant lines (default: False)

    Returns:
        Formatted search results with source citations
    """
    try:
        # Ensure database is initialized
        if not db_pool:
            await initialize_db()

        # Extract potential code identifiers from query (CamelCase, PascalCase, etc.)
        import re
        code_patterns = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)  # Matches: HomeController, MyClass, etc.
        
        # Filter out short/common words (keep only likely class names)
        code_patterns = [p for p in code_patterns if len(p) >= 3 and not p.lower() in ['the', 'this', 'that', 'have', 'with', 'from']]
        # Sort by length (longer = more specific)
        code_patterns = sorted(code_patterns, key=len, reverse=True)
        
        # Try keyword/exact search first for code identifiers
        keyword_results = []
        seen_sources = set()  # Track seen source files to avoid duplicate documents
        
        if code_patterns:
            async with db_pool.acquire() as conn:
                for pattern in code_patterns[:3]:  # Limit to top 3 patterns
                    kw_results = await conn.fetch(
                        """
                        SELECT 
                            c.id AS chunk_id,
                            c.document_id,
                            c.content,
                            0.95 AS similarity,  -- High score for exact matches
                            c.metadata,
                            d.title AS document_title,
                            d.source AS document_source
                        FROM chunks c
                        JOIN documents d ON c.document_id = d.id
                        WHERE c.content ILIKE $1 OR d.title ILIKE $1
                        ORDER BY d.created_at DESC  -- Prefer most recent indexing
                        LIMIT $2
                        """,
                        f'%{pattern}%',
                        limit * 3  # Get more results to account for duplicates
                    )
                    # Deduplicate by source file (keep first occurrence of each file)
                    for result in kw_results:
                        source = result['document_source']
                        if source and source not in seen_sources:
                            seen_sources.add(source)
                            keyword_results.append(result)
                        elif not source:  # Documents without source
                            keyword_results.append(result)
        
        # If keyword search found results, use those (code lookups)
        if keyword_results:
            # Boost code sources if ranking is enabled
            if rank_code_sources:
                for idx, result in enumerate(keyword_results):
                    source = result['document_source']
                    similarity = float(result['similarity'])  # Convert Decimal to float
                    
                    # Boost code files for code queries
                    if source and any(source.endswith(ext) for ext in ['.cs', '.py', '.ts', '.js', '.java', '.cpp', '.c', '.go', '.rs', '.rb']):
                        if any(pattern in query.lower() for pattern in ['class', 'method', 'function', 'used', 'defined', 'where is', 'show']):
                            similarity = min(0.99, similarity * 1.1)  # 10% boost for code files
                            result_dict = dict(result)  # Make mutable copy
                            result_dict['similarity'] = similarity
                            keyword_results[idx] = result_dict
                
                # Re-sort by boosted similarity
                keyword_results = sorted(keyword_results, key=lambda x: x['similarity'], reverse=True)
            
            results = keyword_results[:limit]
        else:
            # Fall back to semantic search for conceptual questions
            from ingestion.embedder import create_embedder
            embedder = create_embedder()
            query_embedding = await embedder.embed_query(query)

            # Convert to PostgreSQL vector format
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

            # Search using match_chunks function
            async with db_pool.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT * FROM match_chunks($1::vector, $2)
                    """,
                    embedding_str,
                    limit
                )

        # Format results for response
        if not results:
            return "No relevant information found in the knowledge base for your query."
        
        # Check if there are more results available
        total_available = len(keyword_results) if keyword_results else len(results)
        more_results_msg = f"\n\n(Showing {len(results)} of {total_available} results. Increase limit for more.)" if total_available > limit else ""

        # Convert results to list of dicts for categorization
        results_list = []
        for row in results:
            similarity = row['similarity']
            content = row['content']
            doc_title = row['document_title']
            doc_source = row['document_source']
            metadata_raw = row.get('metadata', {})
            
            # Parse metadata if it's a JSON string
            import json
            if isinstance(metadata_raw, str):
                try:
                    metadata = json.loads(metadata_raw)
                except:
                    metadata = {}
            else:
                metadata = metadata_raw or {}
            
            results_list.append({
                'similarity': similarity,
                'content': content,
                'document_title': doc_title,
                'document_source': doc_source,
                'metadata': metadata
            })
        
        if not results_list:
            return "Found some results but they may not be directly relevant to your query. Please try rephrasing your question."
        
        # Use categorized formatting for code-related queries
        import re
        code_patterns = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
        is_code_query = bool(code_patterns) or any(kw in query.lower() for kw in ['where is', 'used', 'defined', 'class', 'method', 'function', 'show'])
        
        if is_code_query and len(results_list) >= 3:
            # Use categorized hierarchical format
            formatted_results = _format_categorized_results(results_list, query, full_code)
            return "Based on the knowledge base (organized by usage type):\n" + formatted_results + more_results_msg
        else:
            # Use traditional flat format for simple queries or few results
            response_parts = []
            for i, result_dict in enumerate(results_list, 1):
                metadata = result_dict['metadata']
                
                # Format with clear source attribution and line numbers
                source_str = f"[Source {i}: {result_dict['document_title']}"
                if result_dict['document_source']:
                    source_str += f" - {result_dict['document_source']}"
                
                # Add line numbers if available
                if 'start_line' in metadata and 'end_line' in metadata:
                    start_line = metadata['start_line']
                    end_line = metadata['end_line']
                    if start_line == end_line:
                        source_str += f":{start_line}"
                    else:
                        source_str += f":{start_line}-{end_line}"
                
                source_str += f" (relevance: {result_dict['similarity']:.2%})]"
                
                # Apply smart truncation and highlighting for code queries
                content = result_dict['content']
                if is_code_query:
                    if not full_code:
                        content = _smart_truncate_code(content, query, max_lines=10)
                    else:
                        # Still apply highlighting even with full code
                        import re
                        code_identifiers = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
                        code_identifiers = list(set([term for term in code_identifiers if len(term) >= 3]))
                        
                        highlighted_lines = []
                        for line in content.split('\n'):
                            highlighted_line = line
                            for term in code_identifiers:
                                pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
                                highlighted_line = pattern.sub(
                                    lambda m: f"{Colors.GREEN}{m.group()}{Colors.END}",
                                    highlighted_line
                                )
                            highlighted_lines.append(highlighted_line)
                        content = '\n'.join(highlighted_lines)
                
                response_parts.append(
                    f"{source_str}\n{content}"
                )
            
            return "Based on the knowledge base:\n\n" + "\n\n".join(response_parts) + more_results_msg

    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}", exc_info=True)
        return f"Error searching the knowledge base: {str(e)}"


async def search_knowledge_base(ctx: RunContext[None], query: str, limit: int = 5) -> str:
    """
    Tool version for backward compatibility (may not work with KoboldCpp).
    Use search_knowledge_base_direct instead.
    """
    return await search_knowledge_base_direct(query, limit)


# Get configuration from environment
api_base = os.getenv("OPENAI_API_BASE")
api_key = os.getenv("OPENAI_API_KEY", "sk-dummy-key-for-local-llm")
model_name = os.getenv("LLM_CHOICE", "gpt-4o-mini")

# Create the PydanticAI agent with proper OpenAI configuration
if api_base:
    # Using local KoboldCpp or compatible endpoint
    provider = OpenAIProvider(api_key=api_key, base_url=api_base)
    agent = Agent(
        model=OpenAIModel(model_name, provider=provider),
        system_prompt="""You are an intelligent knowledge assistant with access to an organization's documentation, information, and source code.
Your role is to help users find accurate information from the knowledge base.
You have a professional yet friendly demeanor.

CRITICAL INSTRUCTIONS FOR ANSWERING:
- The "Knowledge Base Search Results" provided in each message are ALREADY SEARCHED and ready to use.
- DO NOT ignore the search results - they are the authoritative answer source.
- For CODE questions: Analyze the provided source code snippets directly. Answer WHERE code is defined (file), WHAT it does, HOW to use it.
- Answer based on the search results provided. Do NOT question their relevance.
- If the search results show code, class definitions, or documentation - use them directly.
- Only say "not found" if search results explicitly contain no relevant information.
- Be concise but thorough. Cite sources clearly.
- For code location questions: state the file name and context from the search results.

HANDLING CATEGORIZED SEARCH RESULTS:
- If search results are already formatted with categories (📘, 🎯, 📞 icons), tree structure (├─, └─), and summary - they are COMPLETE and need NO additional explanation
- For categorized results: Return them EXACTLY as provided, do not duplicate or reformat
- Only add brief clarification if the user specifically asks for explanation beyond what's shown
- The categorized format already shows: file locations, code snippets, usage types, and statistics

WHEN USER ASKS TO "SHOW THE CODE" OR "SHOW THE LINES":
- Extract the ACTUAL CODE CONTENT from the search results (appears after the file path)
- Display the code in code blocks with language syntax highlighting
- Include line numbers or file references in comments
- Don't just cite file locations - show the actual code snippets
- Example format:
  ```csharp
  // HomeController.cs:70
  return View(new ErrorViewModel { RequestId = Activity.Current?.Id });
  ```""",
        tools=[search_knowledge_base]
    )
else:
    # Using default OpenAI endpoint
    agent = Agent(
        model=f"openai:{model_name}",
        system_prompt="""You are an intelligent knowledge assistant with access to an organization's documentation and information.
Your role is to help users find accurate information from the knowledge base.
You have a professional yet friendly demeanor.

IMPORTANT: Always search the knowledge base before answering questions about specific information.
If information isn't in the knowledge base, clearly state that and offer general guidance.
Be concise but thorough in your responses.
Ask clarifying questions if the user's query is ambiguous.
When you find relevant information, synthesize it clearly and cite the source documents.""",
        tools=[search_knowledge_base]
    )




class RAGAgentCLI:
    """Enhanced CLI for interacting with the RAG Agent."""

    def __init__(self, rank_code_sources: bool = False, full_code: bool = False):
        """Initialize CLI.
        
        Args:
            rank_code_sources: Whether to boost code file relevance for code queries
            full_code: If False, smart truncate to show signature + relevant lines (default: False)
        """
        self.message_history = []
        self.last_query = ""  # Track last query for follow-up context
        self.last_search_results = ""  # Track last search results
        self.rank_code_sources = rank_code_sources
        self.full_code = full_code

    def _is_followup_query(self, message: str) -> bool:
        """Detect if message is a follow-up question without explicit context.
        
        Args:
            message: User's message
            
        Returns:
            True if this looks like a follow-up question
        """
        message_lower = message.lower()
        
        # Indicators of follow-up questions
        followup_indicators = [
            'it', 'its', 'that class', 'that method', 'that function',
            'show me', 'show it', 'what about', 'how about',
            'first', 'last', 'more details', 'tell me more',
            'what methods', 'what properties', 'what does it'
        ]
        
        # Check if query has code identifiers
        import re
        has_code_identifier = bool(re.search(r'\b[A-Z][a-zA-Z0-9]+\b', message))
        
        # If it has indicators and no code identifier, it's likely a follow-up
        has_indicator = any(ind in message_lower for ind in followup_indicators)
        
        return has_indicator and not has_code_identifier and len(self.last_query) > 0
    
    def _enhance_followup_query(self, message: str) -> str:
        """Enhance follow-up query with context from last query.
        
        Args:
            message: Current message
            
        Returns:
            Enhanced message with context
        """
        if self._is_followup_query(message):
            # Add context from previous query
            return f"Previous context: {self.last_query}\n\nFollow-up question: {message}"
        return message
    
    def _is_code_display_request(self, message: str) -> bool:
        """Detect if user wants to see actual code content.
        
        Args:
            message: User's message
            
        Returns:
            True if user is asking to display code
        """
        message_lower = message.lower()
        
        code_display_indicators = [
            'show the lines', 'show the source', 'show the code',
            'show me the code', 'display the code', 'print the code',
            'show me the lines', 'display the lines', 'print the lines',
            'show the source lines', 'show source code', 'display source',
            'can you show', 'could you show'
        ]
        
        return any(ind in message_lower for ind in code_display_indicators)
    
    def print_banner(self):
        """Print welcome banner."""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 60}")
        print("🤖 Docling RAG Knowledge Assistant")
        print("=" * 60)
        print(f"{Colors.WHITE}AI-powered document search with streaming responses")
        print(f"Type 'exit', 'quit', or Ctrl+C to exit")
        print(f"Type 'help' for commands")
        print("=" * 60 + f"{Colors.END}\n")

    def print_help(self):
        """Print help information."""
        help_text = f"""
{Colors.BOLD}Available Commands:{Colors.END}
  {Colors.GREEN}help{Colors.END}           - Show this help message
  {Colors.GREEN}clear{Colors.END}          - Clear conversation history
  {Colors.GREEN}stats{Colors.END}          - Show conversation statistics
  {Colors.GREEN}exit/quit{Colors.END}      - Exit the CLI

{Colors.BOLD}Usage:{Colors.END}
  Simply type your question and press Enter to chat with the agent.
  The agent will search the knowledge base and provide answers with source citations.

{Colors.BOLD}Features:{Colors.END}
  • Semantic search through embedded documents
  • Streaming responses in real-time
  • Conversation history maintained across turns
  • Source citations for all information

{Colors.BOLD}Examples:{Colors.END}
  - "What are the main topics in the knowledge base?"
  - "Tell me about [specific topic from your documents]"
  - "Summarize information about [subject]"
"""
        print(help_text)

    def print_stats(self):
        """Print conversation statistics."""
        message_count = len(self.message_history)
        print(f"\n{Colors.MAGENTA}{Colors.BOLD}📊 Session Statistics:{Colors.END}")
        print(f"  Messages in history: {message_count}")
        print(f"  Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Colors.BLUE}{'─' * 60}{Colors.END}\n")

    async def check_database(self) -> bool:
        """Check database connection."""
        try:
            await initialize_db()
            async with db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result == 1:
                    print(f"{Colors.GREEN}✓ Database connection successful{Colors.END}")

                    # Check for documents
                    doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
                    chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks")

                    print(f"{Colors.GREEN}✓ Knowledge base ready: {doc_count} documents, {chunk_count} chunks{Colors.END}")
                    return True
            return False
        except Exception as e:
            print(f"{Colors.RED}✗ Database connection failed: {e}{Colors.END}")
            return False

    def extract_tool_calls(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Extract tool call information from messages."""
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        tools_used = []
        for msg in messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        tools_used.append({
                            'tool_name': part.tool_name,
                            'args': part.args,
                            'tool_call_id': part.tool_call_id
                        })
        return tools_used

    def format_tools_used(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools used for display."""
        if not tools:
            return ""

        formatted = f"\n{Colors.MAGENTA}{Colors.BOLD}🛠 Tools Used:{Colors.END}\n"
        for i, tool in enumerate(tools, 1):
            tool_name = tool.get('tool_name', 'unknown')
            args = tool.get('args', {})

            formatted += f"  {Colors.CYAN}{i}. {tool_name}{Colors.END}"

            # Show key arguments for context (handle both dict and other types)
            if args and isinstance(args, dict):
                key_args = []
                if 'query' in args:
                    query_preview = str(args['query'])[:50] + '...' if len(str(args['query'])) > 50 else str(args['query'])
                    key_args.append(f"query='{query_preview}'")
                if 'limit' in args:
                    key_args.append(f"limit={args['limit']}")

                if key_args:
                    formatted += f" ({', '.join(key_args)})"

            formatted += "\n"

        return formatted

    async def stream_chat(self, message: str) -> None:
        """Send message to agent and display streaming response, with automatic RAG search."""
        try:
            print(f"\n{Colors.BOLD}🤖 Assistant:{Colors.END} ", end="", flush=True)

            # Enhance follow-up queries with context
            enhanced_query = self._enhance_followup_query(message)
            
            # Search knowledge base first (automatic RAG)
            search_context = await search_knowledge_base_direct(
                enhanced_query, 
                limit=20,
                rank_code_sources=self.rank_code_sources,
                full_code=self.full_code
            )
            
            # Store for follow-up context
            self.last_query = message
            self.last_search_results = search_context
            
            # Check if user wants to see actual code
            show_code_instruction = ""
            if self._is_code_display_request(message):
                show_code_instruction = "\n\nIMPORTANT: User wants to see ACTUAL CODE CONTENT, not just file locations. Extract and display the code snippets from the search results above. Use code blocks with syntax highlighting and include line numbers in comments."
            
            # Check if results are categorized (hierarchical format)
            categorized_format_instruction = ""
            if "organized by usage type" in search_context:
                categorized_format_instruction = "\n\nCRITICAL: The search results are already formatted with categories, icons, tree structure, code snippets, and summary. Return them EXACTLY as shown above. DO NOT duplicate, reformat, or add additional explanation unless the user specifically asks for clarification. The formatted results are complete and self-explanatory."
            
            # Enhance the message with search context
            enhanced_message = f"""User Question: {message}

Knowledge Base Search Results (ALREADY SEARCHED - use these directly):
{search_context}

Answer the user's question based ONLY on the Knowledge Base Search Results provided above.{show_code_instruction}{categorized_format_instruction}"""

            # Stream the response using run_stream
            async with agent.run_stream(
                enhanced_message,
                message_history=self.message_history
            ) as result:
                # Stream text as it comes in (delta=True for only new tokens)
                async for text in result.stream_text(delta=True):
                    # Print only the new token
                    print(text, end="", flush=True)

                print()  # New line after streaming completes

                # Update message history for context
                self.message_history = result.all_messages()

                # Extract and display tools used in this turn
                new_messages = result.new_messages()
                tools_used = self.extract_tool_calls(new_messages)
                if tools_used:
                    print(self.format_tools_used(tools_used))

            # Print separator
            print(f"{Colors.BLUE}{'─' * 60}{Colors.END}")

        except Exception as e:
            print(f"\n{Colors.RED}✗ Error: {e}{Colors.END}")
            logger.error(f"Chat error: {e}", exc_info=True)

    async def run(self):
        """Run the CLI main loop."""
        self.print_banner()

        # Check database connection
        if not await self.check_database():
            print(f"{Colors.RED}Cannot connect to database. Please check your DATABASE_URL.{Colors.END}")
            return

        print(f"{Colors.GREEN}Ready to chat! Ask me anything about the knowledge base.{Colors.END}\n")

        try:
            while True:
                try:
                    # Get user input
                    user_input = input(f"{Colors.BOLD}You: {Colors.END}").strip()

                    if not user_input:
                        continue

                    # Handle commands
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        print(f"{Colors.CYAN}👋 Thank you for using the knowledge assistant. Goodbye!{Colors.END}")
                        break
                    elif user_input.lower() == 'help':
                        self.print_help()
                        continue
                    elif user_input.lower() == 'clear':
                        self.message_history = []
                        print(f"{Colors.GREEN}✓ Conversation history cleared{Colors.END}")
                        continue
                    elif user_input.lower() == 'stats':
                        self.print_stats()
                        continue

                    # Send message to agent
                    await self.stream_chat(user_input)

                except KeyboardInterrupt:
                    print(f"\n{Colors.CYAN}👋 Goodbye!{Colors.END}")
                    break
                except EOFError:
                    print(f"\n{Colors.CYAN}👋 Goodbye!{Colors.END}")
                    break

        except Exception as e:
            print(f"{Colors.RED}✗ CLI error: {e}{Colors.END}")
            # logger.error(f"CLI error: {e}", exc_info=True)
        finally:
            await close_db()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhanced CLI for Docling RAG Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging (shows httpx and other debug logs)'
    )

    parser.add_argument(
        '--model',
        default=None,
        help='Override LLM model (e.g., gpt-4o)'
    )

    parser.add_argument(
        '--rank-code-sources',
        action='store_true',
        help='Boost code file relevance for code-related queries (10%% boost for .cs, .py, .ts, etc.)'
    )

    parser.add_argument(
        '--full-code',
        action='store_true',
        help='Show full code blocks in results (default: smart truncate to show signature + relevant matching lines)'
    )

    args = parser.parse_args()

    # Configure logging - suppress all logs by default unless --verbose
    if args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.WARNING  # Only show warnings and errors

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Explicitly suppress httpx logging unless verbose mode
    if not args.verbose:
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)

    # Override model if specified
    if args.model:
        global agent
        agent = Agent(
            f'openai:{args.model}',
            system_prompt=agent.system_prompt,
            tools=[search_knowledge_base]
        )
        # logger.info(f"Using model: {args.model}")

    # Check required environment variables
    if not os.getenv("DATABASE_URL"):
        print(f"{Colors.RED}✗ DATABASE_URL environment variable is required{Colors.END}")
        sys.exit(1)

    # For KoboldCpp, set a dummy API key if not provided
    if not os.getenv("OPENAI_API_KEY"):
        if os.getenv("OPENAI_API_BASE"):
            # Using local endpoint, dummy key is fine
            os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-local-llm"
        else:
            print(f"{Colors.RED}✗ OPENAI_API_KEY environment variable is required{Colors.END}")
            sys.exit(1)

    # Create and run CLI
    cli = RAGAgentCLI(rank_code_sources=args.rank_code_sources, full_code=args.full_code)

    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print(f"\n{Colors.CYAN}👋 Goodbye!{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}✗ CLI startup error: {e}{Colors.END}")
        # logger.error(f"Startup error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

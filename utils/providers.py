"""
Provider configuration supporting both OpenAI and local embeddings (sentence-transformers).
"""

import os
from typing import Optional, Union, List
import asyncio
import logging
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Check if using local KoboldCpp
IS_LOCAL_MODE = bool(os.getenv('OPENAI_API_BASE'))


def get_llm_model() -> OpenAIModel:
    """
    Get LLM model configuration for OpenAI or KoboldCpp.
    
    Returns:
        Configured OpenAI model pointing to either OpenAI or local KoboldCpp
    """
    llm_choice = os.getenv('LLM_CHOICE', 'gpt-4o-mini')
    api_key = os.getenv('OPENAI_API_KEY', 'sk-dummy')
    api_base = os.getenv('OPENAI_API_BASE')
    
    if api_base:
        logger.info(f"Using KoboldCpp at {api_base}")
        return OpenAIModel(llm_choice, provider=OpenAIProvider(api_key=api_key, base_url=api_base))
    else:
        logger.info(f"Using OpenAI with model {llm_choice}")
        return OpenAIModel(llm_choice, provider=OpenAIProvider(api_key=api_key))


class LocalEmbeddingClient:
    """Client for local sentence-transformers embeddings."""
    
    class EmbeddingData:
        """Single embedding data object."""
        def __init__(self, embedding: List[float], index: int):
            self.embedding = embedding
            self.index = index
    
    class EmbeddingResponse:
        """Response object mimicking OpenAI embeddings response."""
        def __init__(self, embeddings_list: List[List[float]], model_name: str):
            self.data = [LocalEmbeddingClient.EmbeddingData(emb, i) for i, emb in enumerate(embeddings_list)]
            self.model = model_name
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cuda"):
        """
        Initialize local embedding model.
        
        Args:
            model_name: Name of the sentence-transformers model to use
            device: Device to run embeddings on ('cuda' or 'cpu', default: 'cuda'). 
                   Use 'cuda' for faster embeddings (hybrid GPU+CPU like KoboldCpp).
                   Use 'cpu' if GPU memory is limited or PyTorch compiled without CUDA.
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            # Try to use requested device, fall back to CPU if not available
            try:
                self.model = SentenceTransformer(model_name, device=device)
                self.device = device
                logger.info(f"Loaded local embedding model: {model_name} on device: {device}")
            except AssertionError as e:
                if "CUDA" in str(e) and device == "cuda":
                    # CUDA not available, fall back to CPU
                    logger.warning(f"⚠️  CUDA not available (PyTorch compiled CPU-only). Falling back to CPU embeddings.")
                    logger.warning(f"📦 For GPU support, install PyTorch with CUDA: https://pytorch.org/get-started/locally/")
                    self.model = SentenceTransformer(model_name, device="cpu")
                    self.device = "cpu"
                else:
                    raise
            
            self.model_name = model_name
        except ImportError:
            raise ImportError("sentence-transformers is required for local embeddings. Install with: pip install sentence-transformers")
    
    async def create(self, model: str = None, input: Union[str, List[str]] = None) -> 'LocalEmbeddingClient.EmbeddingResponse':
        """
        Create embeddings using sentence-transformers (OpenAI-compatible interface).
        
        Args:
            model: Model name (ignored, uses configured model)
            input: Text or list of texts to embed
            
        Returns:
            Response object compatible with OpenAI embeddings API response
        """
        if input is None:
            raise ValueError("input parameter is required")
        
        # Handle single string or list
        if isinstance(input, str):
            texts = [input]
        else:
            texts = input
        
        # Run embedding in threadpool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, self.model.encode, texts)
        
        # Convert embeddings to list of floats for each embedding
        embeddings_list = [embedding.tolist() for embedding in embeddings]
        
        # Return response object
        return self.EmbeddingResponse(embeddings_list, self.model_name)


class LocalEmbeddingAsyncClient:
    """Async wrapper for local embeddings (mimics OpenAI AsyncOpenAI)."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cuda"):
        """
        Initialize async embedding client.
        
        Args:
            model_name: Name of the sentence-transformers model to use
            device: Device to run embeddings on ('cuda' or 'cpu', default: 'cuda' for speed).
                   Use 'cuda' for hybrid GPU performance like KoboldCpp.
                   Use 'cpu' if GPU memory is limited.
        """
        self.embeddings = LocalEmbeddingClient(model_name, device=device)


def get_embedding_client() -> Union[openai.AsyncOpenAI, LocalEmbeddingAsyncClient]:
    """
    Get embedding client for OpenAI or local sentence-transformers.
    
    Returns:
        Embedding client (OpenAI or local)
    """
    if IS_LOCAL_MODE:
        # Use GPU for embeddings for hybrid GPU+CPU performance like KoboldCpp
        # GPU embeddings are much faster (200-500 texts/sec vs 50-100 on CPU)
        # Change to device="cpu" if GPU memory is limited
        logger.info("Using local sentence-transformers for embeddings (device: CUDA)")
        logger.info("Hybrid GPU embeddings + GPU LLM = fast performance")
        return LocalEmbeddingAsyncClient(device="cuda")
    else:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for OpenAI embeddings")
        logger.info("Using OpenAI for embeddings")
        return openai.AsyncOpenAI(api_key=api_key)


def get_embedding_model() -> str:
    """
    Get embedding model name.
    
    Returns:
        Embedding model name
    """
    if IS_LOCAL_MODE:
        return os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
    else:
        return os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')


def get_ingestion_model() -> OpenAIModel:
    """
    Get model for ingestion tasks (uses same model as main LLM).
    
    Returns:
        Configured model for ingestion tasks
    """
    return get_llm_model()


def validate_configuration() -> bool:
    """
    Validate that required environment variables are set.
    
    Returns:
        True if configuration is valid
    """
    required_vars = ['DATABASE_URL']
    
    # OPENAI_API_KEY is only required if not using local mode
    if not IS_LOCAL_MODE:
        required_vars.append('OPENAI_API_KEY')
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    logger.info(f"Configuration valid. Local mode: {IS_LOCAL_MODE}")
    return True


def get_model_info() -> dict:
    """
    Get information about current model configuration.
    
    Returns:
        Dictionary with model configuration info
    """
    return {
        "llm_provider": "koboldcpp" if IS_LOCAL_MODE else "openai",
        "llm_model": os.getenv('LLM_CHOICE', 'local-model' if IS_LOCAL_MODE else 'gpt-4o-mini'),
        "embedding_provider": "sentence-transformers" if IS_LOCAL_MODE else "openai",
        "embedding_model": get_embedding_model(),
        "api_base": os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1'),
    }
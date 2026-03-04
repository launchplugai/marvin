"""
Marvin Conversation Memory Pipeline
Phase 1.5: Capture, compress, synthesize, and hydrate conversation context.

Pipeline:
    capture -> compress (Groq 8B) -> synthesize (two-layer) -> hydrate (inject)
"""

from .capture import ConversationCapture, ConversationBlock
from .compressor import ContextCompressor
from .synthesizer import ContextSynthesizer
from .hydrator import ContextHydrator

__all__ = [
    'ConversationCapture',
    'ConversationBlock',
    'ContextCompressor',
    'ContextSynthesizer',
    'ContextHydrator',
]

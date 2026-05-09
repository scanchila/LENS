"""Concrete agent-framework adapters.

Each module in this package implements one adapter. The orchestrator
imports them only via the FrameworkRegistry — never directly.
"""

from .claude_sdk import ClaudeAgentSDKAdapter
from .direct_anthropic import DirectAnthropicAdapter

__all__ = ["ClaudeAgentSDKAdapter", "DirectAnthropicAdapter"]

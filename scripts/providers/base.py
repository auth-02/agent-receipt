"""Provider interface for Agent Receipt.

The receipt engine only depends on this small contract. Provider-specific
transcript parsing, pricing, display names and resume commands live in the
provider adapter.
"""

from abc import ABC, abstractmethod


class AgentProvider(ABC):
    """Adapter for an AI coding agent/provider."""

    id = "unknown"

    @abstractmethod
    def parse_transcript(self, path):
        raise NotImplementedError

    @abstractmethod
    def price_for(self, model):
        raise NotImplementedError

    @abstractmethod
    def display_name(self, stats):
        raise NotImplementedError

    def brand_line(self):
        return self.id

    @abstractmethod
    def resume_command(self, target):
        raise NotImplementedError

    def derive_title(self, text):
        return text or None

    def status_for_end(self, reason):
        """Map a provider lifecycle reason to a receipt stamp."""
        return "Ended"

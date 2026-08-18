"""Provider registry."""

from .claude_code import ClaudeCodeProvider

_PROVIDERS = {
    "claude": ClaudeCodeProvider,
    "claude_code": ClaudeCodeProvider,
}


def get_provider(name=None):
    key = (name or "claude_code").strip().lower()
    provider_cls = _PROVIDERS.get(key)
    if not provider_cls:
        raise ValueError(f"Unsupported agent provider: {name}")
    return provider_cls()

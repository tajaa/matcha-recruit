"""Network providers. One Meta app serves both networks we publish to today;
`provider_for` is the one place that mapping lives, so a new network is a new
module and one line here."""
from .base import ConnectionDraft, InboundEvent, ProviderError, PublishResult
from . import meta

# platform → provider module. Both current networks are Meta's.
_PROVIDERS = {"instagram": meta, "facebook": meta}


def provider_for(platform: str):
    try:
        return _PROVIDERS[platform]
    except KeyError:
        raise ProviderError(f"No provider for platform {platform!r}", retryable=False) from None


__all__ = ["ConnectionDraft", "InboundEvent", "ProviderError", "PublishResult", "provider_for", "meta"]

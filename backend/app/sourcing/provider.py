"""Where the readers run.

Reading a supplier's documents or a pasted reply into cited fields is work a cheaper
model can do, so it may run at another provider than the explanation. Every value
falls back to what the Case explanation uses.
"""


def provider(settings):
    return {
        "base_url": settings.agent_sourcing_base_url or settings.agent_base_url,
        "key_file": settings.agent_sourcing_api_key_file or settings.agent_api_key_file,
        "model": settings.agent_sourcing_model or settings.agent_case_model,
        "api_mode": settings.agent_sourcing_api_mode or settings.agent_case_api_mode,
    }


def configured(settings):
    where = provider(settings)
    return bool(where["key_file"] and where["model"])

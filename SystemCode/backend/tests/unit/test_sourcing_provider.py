"""Which model reads supplier documents and pasted replies, and at which provider."""


def test_readers_use_their_own_provider_and_fall_back_to_the_case_model(monkeypatch):
    import shopsteward_agent

    from app.core.config import Settings
    from app.execution import assisted
    from app.sourcing.provider import configured, provider
    from app.sourcing.run import reviewers

    made = []
    monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: made.append(kwargs))

    def clients():
        seen = [(call["base_url"], call["model"], call["key_file"]) for call in made]
        made.clear()
        return seen

    assert not configured(Settings(_env_file=None))
    assert assisted.reader(Settings(_env_file=None)) is None and clients() == []

    # Only the Agent is configured: sourcing cannot start, a reply is read by the Agent's model.
    agent = Settings(_env_file=None, agent_api_key_file="agent.key", agent_model="agent-model")
    assert not configured(agent)
    assisted.reader(agent)
    assert clients() == [("https://api.openai.com/v1", "agent-model", "agent.key")]

    # A Case model: reviewers and the reply reader share it.
    shared = agent.model_copy(update={"agent_case_model": "strong"})
    assert provider(shared) == {
        "base_url": "https://api.openai.com/v1",
        "key_file": "agent.key",
        "model": "strong",
        "api_mode": "responses",
    }
    _, profile, roles = reviewers(shared)
    assisted.reader(shared)
    assert (profile.model_id, profile.api_mode, roles) == ("strong", "responses", {})
    assert clients() == [("https://api.openai.com/v1", "strong", "agent.key")] * 2

    # Readers at another provider: the cheaper model reads, with its own key and protocol.
    split = shared.model_copy(
        update={
            "agent_sourcing_base_url": "https://cheap.example/v1",
            "agent_sourcing_api_key_file": "cheap.key",
            "agent_sourcing_api_mode": "chat_completions",
            "agent_sourcing_model": "cheap",
            "agent_sourcing_escalation_model": "cheap-pro",
        }
    )
    _, profile, roles = reviewers(split)
    assisted.reader(split)
    assert (profile.model_id, profile.api_mode) == ("cheap", "chat_completions")
    assert roles["supplier_escalation"][1].model_id == "cheap-pro"
    assert clients() == [
        ("https://cheap.example/v1", "cheap-pro", "cheap.key"),
        ("https://cheap.example/v1", "cheap", "cheap.key"),
        ("https://cheap.example/v1", "cheap", "cheap.key"),
    ]

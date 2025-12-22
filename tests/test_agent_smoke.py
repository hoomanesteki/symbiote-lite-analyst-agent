def test_agent_imports():
    import symbiote_lite.agent
    assert hasattr(symbiote_lite.agent, "run_agent")

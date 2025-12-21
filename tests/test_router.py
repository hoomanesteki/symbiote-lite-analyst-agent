from scripts.symbiote_lite_agent import ask_gemini_router

class FakeModel:
    def generate_content(self, _):
        class R:
            text = '{"intent":"trip_frequency","dataset_match":true}'
        return R()

def test_router_parsing(monkeypatch):
    import scripts.symbiote_lite_agent as agent
    monkeypatch.setattr(agent, "MODEL", FakeModel())

    result = agent.ask_gemini_router("show trips")
    assert result["intent"] == "trip_frequency"

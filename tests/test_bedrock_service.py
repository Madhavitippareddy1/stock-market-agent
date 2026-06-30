import json

from stock_market_agent.services.bedrock_service import BedrockService


class FakeBody:
    def read(self):
        return json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode()


class FakeBedrockClient:
    def converse(self, **kwargs):
        return {"output": {"message": {"content": [{"text": "Generated answer"}]}}}

    def invoke_model(self, **kwargs):
        return {"body": FakeBody()}


def test_generate_text_uses_bedrock_converse():
    service = BedrockService(client=FakeBedrockClient())
    assert service.generate_text("hello") == "Generated answer"


def test_embed_text_uses_titan_payload():
    service = BedrockService(client=FakeBedrockClient())
    assert service.embed_text("hello") == [0.1, 0.2, 0.3]

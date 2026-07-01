from stock_market_agent.config import Settings
from stock_market_agent.services.prompt_catalog import PromptCatalog


def test_prompt_catalog_loads_active_investment_prompt():
    catalog = PromptCatalog(Settings(prompt_catalog_path="data/prompts/prompts.json"))

    prompt = catalog.get("investment_research_summary")

    assert prompt.version == "v1.0.0"
    assert "{question}" in prompt.text
    assert prompt.system_prompt
    assert catalog.active_versions()["investment_research_summary"] == "v1.0.0"

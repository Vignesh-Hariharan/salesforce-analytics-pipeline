import pytest

from config.prompts import PROMPT_CONFIGS, get_prompt


def test_get_prompt_substitutes_data_summary():
    prompt, temperature = get_prompt('sales-pipeline-health',
                                     "Total Opportunities: 99")
    assert "Total Opportunities: 99" in prompt
    assert 0.0 <= temperature <= 1.0


def test_get_prompt_unknown_workflow_raises():
    with pytest.raises(ValueError):
        get_prompt('not-a-workflow', "")


def test_every_workflow_has_prompt_and_temperature():
    for workflow, cfg in PROMPT_CONFIGS.items():
        assert 'template' in cfg, workflow
        assert 'temperature' in cfg, workflow
        assert "{data_summary}" in cfg['template'], workflow

"""Tests for the historical-weight derivation used by the revenue forecast.

These run without a real Snowflake connection by stubbing the client query
results, since the goal is to validate the math, not the integration.
"""
from unittest.mock import MagicMock

from workflows.revenue_forecast import (
    DEFAULT_STAGE_WEIGHTS,
    MIN_STAGE_SAMPLE,
    derive_stage_weights,
)


def _stub_client(rows):
    client = MagicMock()
    client.execute_query.return_value = rows
    return client


def test_derive_weights_uses_history_when_sample_meets_threshold():
    rows = [
        {'STAGE_NAME': 'Proposal',     'SAMPLE_SIZE': 50, 'WON_COUNT': 30, 'LOST_COUNT': 20},
        {'STAGE_NAME': 'Negotiation',  'SAMPLE_SIZE': 40, 'WON_COUNT': 32, 'LOST_COUNT': 8},
    ]
    weights, fallback = derive_stage_weights(_stub_client(rows))

    assert weights['Proposal']['source'] == 'historical'
    assert weights['Proposal']['weight'] == 30 / 50
    assert weights['Negotiation']['source'] == 'historical'
    assert weights['Negotiation']['weight'] == 32 / 40
    # Stages without historical coverage fall back to defaults
    assert weights['Prospecting']['source'] == 'default'
    assert weights['Prospecting']['weight'] == DEFAULT_STAGE_WEIGHTS['Prospecting']
    # Fallback count covers the four stages not present in `rows`
    assert fallback == len(DEFAULT_STAGE_WEIGHTS) - 2


def test_derive_weights_falls_back_when_sample_below_threshold():
    rows = [
        {'STAGE_NAME': 'Proposal', 'SAMPLE_SIZE': MIN_STAGE_SAMPLE - 1,
         'WON_COUNT': 0, 'LOST_COUNT': MIN_STAGE_SAMPLE - 1},
    ]
    weights, fallback = derive_stage_weights(_stub_client(rows))

    assert weights['Proposal']['source'] == 'default'
    assert weights['Proposal']['weight'] == DEFAULT_STAGE_WEIGHTS['Proposal']
    assert fallback == len(DEFAULT_STAGE_WEIGHTS)


def test_derive_weights_handles_empty_history():
    weights, fallback = derive_stage_weights(_stub_client([]))
    assert fallback == len(DEFAULT_STAGE_WEIGHTS)
    for stage, default in DEFAULT_STAGE_WEIGHTS.items():
        assert weights[stage]['weight'] == default
        assert weights[stage]['source'] == 'default'

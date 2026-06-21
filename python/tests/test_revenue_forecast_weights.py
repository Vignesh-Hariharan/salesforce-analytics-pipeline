"""Tests for revenue-forecast metric assembly from dbt marts."""
from unittest.mock import MagicMock

from workflows.revenue_forecast import calculate_metrics, map_stage_forecasts


def test_map_stage_forecasts_normalizes_mart_columns():
    rows = [{
        'STAGE_NAME': 'Proposal',
        'STAGE_VALUE': 100000,
        'OPEN_COUNT': 5,
        'WEIGHT': 0.6,
        'WEIGHTED_VALUE': 60000,
        'SAMPLE_SIZE': 50,
        'WEIGHT_SOURCE': 'historical',
    }]
    mapped = map_stage_forecasts(rows)
    assert mapped[0]['stage'] == 'Proposal'
    assert mapped[0]['weight'] == 0.6
    assert mapped[0]['weight_source'] == 'historical'
    assert mapped[0]['weighted_value'] == 60000


def test_calculate_metrics_reads_summary_and_forecast_marts():
    client = MagicMock()
    client.execute_query.side_effect = [
        [{
            'TOTAL_PIPELINE': 500000,
            'OPEN_OPPS': 12,
            'WEIGHTED_FORECAST': 210000,
            'AT_RISK_VALUE': 40000,
            'WEIGHTS_FALLBACK_COUNT': 2,
        }],
        [{
            'STAGE_NAME': 'Proposal',
            'OPEN_COUNT': 3,
            'STAGE_VALUE': 200000,
            'WEIGHT': 0.6,
            'WEIGHTED_VALUE': 120000,
            'SAMPLE_SIZE': 25,
            'WEIGHT_SOURCE': 'historical',
        }],
        [{'MONTH': '2026-01-01', 'REVENUE': 80000}],
    ]

    metrics = calculate_metrics(client)

    assert metrics['total_pipeline'] == 500000
    assert metrics['weighted_forecast'] == 210000
    assert metrics['weights_fallback_count'] == 2
    assert metrics['stage_forecasts'][0]['stage'] == 'Proposal'
    assert len(metrics['historical_revenue']) == 1

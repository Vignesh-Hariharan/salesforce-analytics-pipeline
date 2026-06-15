from clients.slack_client import SlackClient


def test_parse_insights_groups_at_finding_markers():
    raw = (
        "Finding: A first observation\n"
        "Impact: Some impact\n"
        "Action: Take this step\n"
        "\n"
        "Finding: A second observation\n"
        "Impact: Other impact\n"
        "Action: Different step\n"
    )
    parsed = SlackClient._parse_insights(raw)
    assert len(parsed) == 2
    assert parsed[0].startswith("Finding: A first observation")
    assert "Action: Take this step" in parsed[0]
    assert parsed[1].startswith("Finding: A second observation")


def test_parse_insights_handles_blank_input():
    assert SlackClient._parse_insights("") == []


def test_parse_insights_preserves_special_characters():
    raw = "Finding: Deals <7 days old & >$50K converting at 30%"
    parsed = SlackClient._parse_insights(raw)
    assert parsed == ["Finding: Deals <7 days old & >$50K converting at 30%"]


def test_format_metrics_pipeline_health_uses_close_rate_and_value():
    fields = SlackClient._format_metrics(
        'sales-pipeline-health',
        {
            'total_opportunities': 42,
            'close_rate': 18.7,
            'avg_days_to_close': 33,
            'pipeline_value': 250_000,
        },
    )
    rendered = " ".join(f['text'] for f in fields)
    assert "42" in rendered
    assert "18.7%" in rendered
    assert "$250,000" in rendered


def test_format_metrics_revenue_forecast_flags_fallback_weights():
    fields = SlackClient._format_metrics(
        'revenue-forecast',
        {
            'total_pipeline': 500_000,
            'weighted_forecast': 175_000,
            'open_opps': 20,
            'at_risk_value': 40_000,
            'weights_fallback_count': 3,
        },
    )
    rendered = " ".join(f['text'] for f in fields)
    assert "fell back" in rendered
    assert "$175,000" in rendered

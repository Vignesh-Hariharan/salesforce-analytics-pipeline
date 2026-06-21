{#
    Build every model into the single target schema instead of dbt's default
    "<target_schema>_<custom_schema>" pattern. The Python loader writes raw_*
    tables and selects the marts back from one schema, so a custom-schema split
    would break those reads.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ target.schema | trim }}
{%- endmacro %}

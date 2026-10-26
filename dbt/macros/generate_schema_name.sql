{#
  By default dbt names custom schemas "<target schema>_<custom schema>" (e.g. main_silver).
  We want the layer names exactly as written: bronze, silver, gold.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

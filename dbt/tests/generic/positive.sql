{#
  Fails for every row where the column is zero or negative. NULLs pass:
  a missing amount is allowed, an impossible one is not.
#}
{% test positive(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} <= 0
{% endtest %}

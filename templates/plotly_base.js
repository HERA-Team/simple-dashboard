var data = {{ data|tojson|wordwrap(break_long_words=False) }};


var layout = {{ layout|tojson }};

{% if updatemenus is defined %}
var updatemenus = {{ updatemenus|tojson }};
layout.updatemenus = updatemenus;
{% endif %}

Plotly.plot("{{ plotname }}", data, layout, {responsive: true});

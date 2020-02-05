{% for name in json_name|listify %}
{% set layout, plotname = layout|listify, plotname|listify %}
$.getJSON("./{{ name }}.json", function(data){

var layout = {{ layout[loop.index0]|tojson }};

{% if updatemenus is defined %}
var updatemenus = {{ updatemenus[loop.index0]|listify|tojson }};
layout.updatemenus = updatemenus;
{% endif %}

Plotly.plot("{{ plotname[loop.index0] }}", data, layout, {responsive: true});
});
{% endfor %}

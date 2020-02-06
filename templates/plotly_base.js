{% set json_name, layout, plotname, updatemenus = json_name|listify, layout|listify, plotname|listify, [updatemenus] %}
{% for name in json_name %}
$.getJSON("./{{ name }}.json", function(data){

var layout = {{ layout[loop.index0]|tojson }};

{% if updatemenus is defined %}
var updatemenus = {{ updatemenus[loop.index0]|tojson }};
layout.updatemenus = updatemenus;
{% endif %}

Plotly.plot("{{ plotname[loop.index0] }}", data, layout, {responsive: true});
});
{% endfor %}

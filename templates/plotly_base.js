{% set json_name, layout, plotname = json_name|listify, layout|listify, plotname|listify %}
{% if updatemenus is defined %}
{% set updatemenus = [updatemenus]%}
{% endif %}
{% for name in json_name %}
$.getJSON("./{{ name }}.json", function(data){

var layout = {{ layout[loop.index0]|tojson }};

{% if updatemenus is defined %}
var updatemenus = {{ updatemenus[loop.index0]|tojson }};
layout.updatemenus = updatemenus;
{% endif %}
Plotly.react("{{ plotname[loop.index0] }}", data, layout, {responsive: true});
});
{% endfor %}

{% extends "plotly_base.js" %}

{% block menus %}
    var updatemenus = {{ updatemenus|tojson }};
    layout.updatemenus = updatemenus;
{% endblock %}

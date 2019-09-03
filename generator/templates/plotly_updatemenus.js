{% extends "plotly_base.js" %}

{% block content %}
    var updatemenus = {{ updatemenus|tojson }};
    layout.updatemenus = updatemenus;
{% endblock %}

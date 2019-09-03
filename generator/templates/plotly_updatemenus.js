{% extends "ploty_base.js" %}

{% block content %}
    var updatemenus = {{ updatemenus|tojson|wordwrap }};
    layout.updatemenus = updatemenus;
{% endblock %}

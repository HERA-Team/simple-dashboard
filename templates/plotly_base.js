var data = {{ data|tojson|wordwrap(break_long_words=False) }};


var layout = {{ layout|tojson }};

{% block menus %}{% endblock %}

Plotly.plot("{{ plotname }}", data, layout, {responsive: true});

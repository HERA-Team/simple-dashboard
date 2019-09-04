var report_age = 0.001 * (Date.now() - {{gen_time_unix_ms}});
var age_text = "?";
if (report_age < 300) {
  age_text = report_age.toFixed(0) + " seconds";
} else if (report_age < 10800) { // 3 hours
  age_text = (report_age / 60).toFixed(0) + " minutes";
} else if (report_age < 172800) { // 48 hours
  age_text = (report_age / 3600).toFixed(0) + " hours";
} else {
  age_text = (report_age / 86400).toFixed(1) + " days";
}
document.getElementById("age").textContent = age_text;
if (report_age > 1800) {
    document.getElementById("age").style.color = 'red';
}

var data = {{ data|tojson|wordwrap(break_long_words=False) }};


var layout = {{ layout|tojson }};

{% block menus %}{% endblock %}

Plotly.plot("{{ plotname }}", data, layout, {responsive: true});

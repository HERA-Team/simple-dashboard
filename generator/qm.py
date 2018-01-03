#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2018 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for monitoring data quality."""

from __future__ import absolute_import, division, print_function

from astropy.time import Time, TimeDelta
from hera_mc import mc
from hera_mc.qm import AntMetrics, ArrayMetrics
import sqlalchemy


def main():
    parser = mc.get_mc_argument_parser()
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    with db.sessionmaker() as session, \
         open('qm.html', 'wt') as html_file, \
         open('qm.js', 'wt') as js_file:
        def emit_html(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_file, end=end)
        def emit_js(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_file, end=end)

        Emitter(session, emit_html, emit_js).emit()


HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HERA Quality Metrics Dashboard</title>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
  <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
  <![endif]-->
</head>
<body>
<div class="container">
  <div class="row">
    <div class="col-md-12">
        <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
    </div>
  </div>\
"""

HTML_FOOTER = """\
  <div class="row">
    <div class="col-md-12">
        <p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a>.</p>
    </div>
  </div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="qm.js"></script>
</body>
</html>\
"""

JS_HEADER = """\
var report_age = 0.001 * (Date.now() - {gen_time_unix_ms});
var age_text = "?";
if (report_age < 300) {{
  age_text = report_age.toFixed(0) + " seconds";
}} else if (report_age < 10800) {{ // 3 hours
  age_text = (report_age / 60).toFixed(0) + " minutes";
}} else if (report_age < 172800) {{ // 48 hours
  age_text = (report_age / 3600).toFixed(0) + " hours";
}} else {{
  age_text = (report_age / 86400).toFixed(1) + " days";
}}
document.getElementById("age").textContent = age_text;

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'placeholder'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};\
"""


class Emitter(object):
    TIME_WINDOW = 7 # days

    def __init__(self, session, emit_html, emit_js):
        self.session = session
        self.emit_html = emit_html
        self.emit_js = emit_js

        self.now = Time.now()
        self.cutoff = self.now - TimeDelta(self.TIME_WINDOW, format='jd')
        self.cutoff_gps = self.cutoff.gps
        self.cutoff_obsid = self.cutoff_gps - 300 # NOTE encoding the obsid <=> GPS-time mapping
        self.time_axis_range = 'range: ["{}", "{}"]'.format(self.cutoff.iso, self.now.iso)


    def emit(self):
        self.emit_html(HTML_HEADER,
                       gen_date = self.now.iso
        )
        self.emit_js(JS_HEADER,
                     gen_time_unix_ms = self.now.unix * 1000,
                     time_axis_range = self.time_axis_range,
        )

        self.emit_html("""\
  <div class="row">
    <div id="am-xants" class="col-md-6"></div>
    <div id="am-meanVij" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="am-redCorr" class="col-md-6"></div>
    <div id="am-meanVijXpol" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="fc-agg_std" class="col-md-6"></div>
    <div id="fc-max_std" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="oc-ant_phs_std_max" class="col-md-6"></div>
    <div id="oc-chisq_tot_avg" class="col-md-6"></div>
  </div>
""")

        # If an antpol is detected as bad (`val` not used).
        self.do_ant_metric(
            'am-xants',
            'ant_metrics_xants',
            sqlalchemy.func.count(),
            yformat = '{x:d}',
            ymode = 'markers',
            yname = 'Data',
            ylabel = 'AM count(xants)',
        )

        # "Mean of the absolute value of all visibilities associated with an
        # antenna".
        self.do_ant_metric(
            'am-meanVij',
            'ant_metrics_meanVij',
            sqlalchemy.func.avg(AntMetrics.val),
            yformat = '{x:.2f}',
            yname = 'Data',
            ylabel = 'AM avg(meanVij)',
        )

        # "Extent to which baselines involving an antenna do not correlate
        # with others they are nominmally redundant with".
        self.do_ant_metric(
            'am-redCorr',
            'ant_metrics_redCorr',
            sqlalchemy.func.avg(AntMetrics.val),
            yformat = '{x:.2f}',
            yname = 'Data',
            ylabel = 'AM avg(redCorr)',
        )

        # "Ratio of mean cross-pol visibilities to mean same-pol visibilities:
        # (Vxy+Vyx)/(Vxx+Vyy)".
        self.do_ant_metric(
            'am-meanVijXpol',
            'ant_metrics_meanVijXPol',
            sqlalchemy.func.avg(AntMetrics.val),
            yformat = '{x:.2f}',
            yname = 'Data',
            ylabel = 'AM avg(meanVijXPol)',
        )

        # "Aggregate standard deviation of delay solutions".
        self.do_xy_array_metric(
            'fc-agg_std',
            'firstcal_metrics_agg_std',
            yformat = '{x:.3f}',
            ylabel = 'FC agg_std',
        )

        # "Maximum antenna standard deviation of delay solutions".
        self.do_xy_array_metric(
            'fc-max_std',
            'firstcal_metrics_max_std',
            yformat = '{x:.3f}',
            ylabel = 'FC max_std',
        )

        # Maximum of "gain phase standard deviation per-antenna across file".
        self.do_xy_array_metric(
            'oc-ant_phs_std_max',
            'omnical_metrics_ant_phs_std_max',
            doubled_suffix = True,
            yformat = '{x:.3f}',
            ylabel = 'OC ant_phs_std_max',
        )

        # "Median of chi-square across entire file".
        self.do_xy_array_metric(
            'oc-chisq_tot_avg',
            'omnical_metrics_chisq_tot_avg',
            doubled_suffix = True,
            yformat = '{x:.4f}',
            ylabel = 'OC chisq_tot_avg',
        )

        self.emit_html(HTML_FOOTER)


    def do_ant_metric(self, div_id, metric, yexpression, yformat='{x:.1f}', ymode='lines',
                      yname='NONAME', ylabel='NOTITLE'):
        data = (self.session.query(AntMetrics.obsid, yexpression)
                .filter(AntMetrics.metric == metric)
                .filter(AntMetrics.obsid > self.cutoff_obsid)
                .group_by(AntMetrics.obsid)
                .order_by(AntMetrics.obsid)
                .all())

        self.emit_js('data = [{{x:', end='')
        self.emit_obsid_as_time_array(t[0] for t in data)
        self.emit_js(', y:', end='')
        self.emit_data_array((t[1] for t in data), yformat)
        self.emit_js(''', name: "{yname}", mode: "{ymode}"}}];
layout.yaxis.title = "{ylabel}";
Plotly.plot('{div_id}', {{data: data, layout: layout}});\
''', div_id=div_id, yname=yname, ymode=ymode, ylabel=ylabel)


    def do_xy_array_metric(self, div_id, metric_base, yexpression=ArrayMetrics.val, doubled_suffix=False,
                           yformat='{x:.1f}', ymode='lines', ylabel='NOTITLE'):
        if doubled_suffix:
            suffixes = ['_XX', '_YY']
        else:
            suffixes = ['_x', '_y']

        self.emit_js('data = [', end='')
        sep = ''

        for desc, suffix in zip('XY', suffixes):
            self.emit_js('{sep}{{x:', sep=sep, end='')
            sep = ','

            data = (self.session.query(ArrayMetrics.obsid, yexpression)
                .filter(ArrayMetrics.metric == metric_base + suffix)
                .filter(ArrayMetrics.obsid > self.cutoff_obsid)
                .order_by(ArrayMetrics.obsid)
                .all())

            self.emit_obsid_as_time_array(t[0] for t in data)
            self.emit_js(', y:', end='')
            self.emit_data_array((t[1] for t in data), yformat)
            self.emit_js(', name: "{desc}", mode: "{ymode}"}}', desc=desc, ymode=ymode)

        self.emit_js('''];
layout.yaxis.title = "{ylabel}";
Plotly.plot('{div_id}', {{data: data, layout: layout}});\
''', div_id=div_id, ymode=ymode, ylabel=ylabel)


    def emit_data_array(self, data, fmt):
        self.emit_js('[', end='')
        first = True

        for x in data:
            if first:
                first = False
            else:
                self.emit_js(',', end='')
            self.emit_js(fmt, x=x, end='')

        self.emit_js(']', end='')


    def emit_gpstime_array(self, data):
        self.emit_js('[', end='')
        first = True

        for t in data:
            if first:
                first = False
            else:
                self.emit_js(',', end='')
            self.emit_js('"{x}"', x=Time(t, format='gps').iso, end='')

        self.emit_js(']', end='')


    def emit_obsid_as_time_array(self, data):
        self.emit_gpstime_array(x + 300. for x in data)


if __name__ == '__main__':
    main()

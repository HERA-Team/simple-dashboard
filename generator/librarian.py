#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Librarian."""

from __future__ import absolute_import, division, print_function

from astropy.time import Time, TimeDelta
from cgi import escape
from hera_mc import mc
from hera_mc.librarian import LibRAIDErrors, LibRAIDStatus, LibRemoteStatus, LibServerStatus, LibStatus


def main():
    parser = mc.get_mc_argument_parser()
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    with db.sessionmaker() as session, \
         open('librarian.html', 'wt') as html_file, \
         open('librarian.js', 'wt') as js_file:
        def emit_html(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_file, end=end)
        def emit_js(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_file, end=end)

        Emitter(session, emit_html, emit_js).emit()


HTML_HEADER="""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HERA Librarian Dashboard</title>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
  <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
  <![endif]-->
</head>
"""

HOSTNAMES = ['qmaster', 'pot1', 'pot6.karoo.kat.ac.za', 'pot7.still.pvt', 'pot8.still.pvt']

UI_HOSTNAMES = {
    'pot6.karoo.kat.ac.za': 'pot6',
    'pot7.still.pvt': 'pot7',
    'pot8.still.pvt': 'pot8',
    'per715-1.still.pvt': 'still1',
    'per715-2.still.pvt': 'still2',
    'per715-3.still.pvt': 'still3',
    'per715-4.still.pvt': 'still4',
}

REMOTES = ['aoc-uploads', 'shredder']


class Emitter(object):
    TIME_WINDOW = 14 # days

    def __init__(self, session, emit_html, emit_js):
        self.session = session
        self.emit_html = emit_html
        self.emit_js = emit_js

        self.now = Time.now()
        self.cutoff = self.now - TimeDelta(self.TIME_WINDOW, format='jd')
        self.cutoff_gps = self.cutoff.gps
        self.time_axis_range = 'range: ["{}", "{}"]'.format(self.cutoff.iso, self.now.iso)


    def emit(self):
        self.emit_html(HTML_HEADER)

        self.emit_html("""\
<body>
<div class="container">
  <div class="row">
    <div class="col-md-12">
        <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
    </div>
  </div>
  <div class="row">
    <div id="server-loads" class="col-md-6"></div>
    <div id="upload-ages" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="disk-space" class="col-md-6"></div>
    <div id="bandwidths" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="num-files" class="col-md-6"></div>
    <div id="ping-times" class="col-md-6"></div>
  </div>
""", gen_date = self.now.iso)

        self.emit_js("""\
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
if (report_age > 1800) {{
    document.getElementById("age").style.color = 'red';
}}
""", gen_time_unix_ms = self.now.unix * 1000)

        self.do_server_loads()
        self.do_disk_space()
        self.do_upload_ages()
        self.do_bandwidths()
        self.do_ping_times()
        self.do_num_files()
        self.do_raid_errors()
        self.do_raid_status()

        self.emit_html("""\
  <div class="row">
    <div class="col-md-12">
        <p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a>.</p>
    </div>
  </div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="librarian.js"></script>
</body>
</html>
""")


    def do_server_loads(self):
        sep = ''

        self.emit_js('data = [')

        for host in HOSTNAMES:
            data = (self.session.query(LibServerStatus.mc_time, LibServerStatus.cpu_load_pct)
                    .filter(LibServerStatus.hostname == host)
                    .filter(LibServerStatus.mc_time > self.cutoff_gps)
                    .order_by(LibServerStatus.mc_time)
                    .all())

            self.emit_js('{sep}{{x:', sep=sep, end='')
            self.emit_gpstime_array(t[0] for t in data)
            self.emit_js(',y:', end='')
            self.emit_data_array((t[1] for t in data), '{x:.2f}')
            self.emit_js(',name:"{name}",type:"scatter"}}', name=UI_HOSTNAMES.get(host, host))
            sep = ','

        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'Load % per CPU'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('server-loads', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_disk_space(self):
        self.emit_js('data = [')

        data = (self.session.query(LibStatus.time, LibStatus.data_volume_gb)
                .filter(LibStatus.time > self.cutoff_gps)
                .order_by(LibStatus.time)
                .all())
        self.emit_js('{{x:', end='')
        self.emit_gpstime_array(t[0] for t in data)
        self.emit_js(',y:', end='')
        self.emit_data_array((t[1] for t in data), '{x:.0f}')
        self.emit_js(',name:"Data volume",type:"scatter"}},')

        data = (self.session.query(LibStatus.time, LibStatus.free_space_gb)
                .filter(LibStatus.time > self.cutoff_gps)
                .order_by(LibStatus.time)
                .all())
        self.emit_js('{{x:', end='')
        self.emit_gpstime_array(t[0] for t in data)
        self.emit_js(',y:', end='')
        self.emit_data_array((t[1] for t in data), '{x:.0f}')
        self.emit_js(',name:"Free space",type:"scatter"}}')
        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'Gigabytes', zeroline: true}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('disk-space', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_upload_ages(self):
        self.emit_js('data = [')

        data = (self.session.query(LibStatus.time, LibStatus.upload_min_elapsed)
                .filter(LibStatus.time > self.cutoff_gps)
                .order_by(LibStatus.time)
                .all())
        self.emit_js('{{x:', end='')
        self.emit_gpstime_array(t[0] for t in data)
        self.emit_js(',y:', end='')
        self.emit_data_array((t[1] for t in data), '{x:.0f}')
        self.emit_js(',name:"Time since last upload",type:"scatter"}}')
        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'Minutes'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('upload-ages', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_bandwidths(self):
        sep = ''
        self.emit_js('data = [')

        for remote in REMOTES:
            data = (self.session.query(LibRemoteStatus.time, LibRemoteStatus.bandwidth_mbs)
                    .filter(LibRemoteStatus.remote_name == remote)
                    .filter(LibRemoteStatus.time > self.cutoff_gps)
                    .order_by(LibRemoteStatus.time)
                    .all())

            self.emit_js('{sep}{{x:', sep=sep, end='')
            self.emit_gpstime_array(t[0] for t in data)
            self.emit_js(',y:', end='')
            self.emit_data_array((t[1] for t in data), '{x:.1f}')
            self.emit_js(',name:"{name} transfer rate",type:"scatter"}}', name=remote)
            sep = ','

        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'MB/s'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('bandwidths', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_ping_times(self):
        sep = ''
        self.emit_js('data = [')

        for remote in REMOTES:
            data = (self.session.query(LibRemoteStatus.time, LibRemoteStatus.ping_time)
                    .filter(LibRemoteStatus.remote_name == remote)
                    .filter(LibRemoteStatus.time > self.cutoff_gps)
                    .order_by(LibRemoteStatus.time)
                    .all())

            self.emit_js('{sep}{{x:', sep=sep, end='')
            self.emit_gpstime_array(t[0] for t in data)
            self.emit_js(',y:', end='')
            self.emit_data_array((1000 * t[1] for t in data), '{x:.1f}')
            self.emit_js(',name:"{name} ping time",type:"scatter"}}', name=remote)
            sep = ','

        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'ms', rangemode: 'tozero', zeroline: true}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('ping-times', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_num_files(self):
        self.emit_js('data = [')

        data = (self.session.query(LibStatus.time, LibStatus.num_files)
                .filter(LibStatus.time > self.cutoff_gps)
                .order_by(LibStatus.time)
                .all())
        self.emit_js('{{x:', end='')
        self.emit_gpstime_array(t[0] for t in data)
        self.emit_js(',y:', end='')
        self.emit_data_array((t[1] for t in data), '{x}')
        self.emit_js(',name:"Number of files",type:"scatter"}}')
        self.emit_js("""\
];

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'Number'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};

Plotly.plot('num-files', {{data: data, layout: layout}});\
""", time_axis_range=self.time_axis_range)


    def do_raid_errors(self):
        q = (self.session.query(LibRAIDErrors)
             .filter(LibRAIDErrors.time > self.cutoff_gps)
             .order_by(LibRAIDErrors.time.desc())
             .limit(10))

        self.emit_html("""\
<h2>Recent RAID Errors</h2>
<div class="table-responsive">
<table class="table table-striped">
<thead>
<tr>
<th>Date</th>
<th>Host</th>
<th>Disk</th>
<th>Message</th>
</thead><tbody>
</tr>""")

        did_any = False

        for rec in q:
            self.emit_html('<tr><td>{time}<td>{rec.hostname}<td>{rec.disk}<td>{e_message}</tr>',
                           time = Time(rec.time, format='gps').iso,
                           rec = rec,
                           e_message = escape(rec.message),
            )
            did_any = True

        if not did_any:
            self.emit_html('<tr><td><td><td><td>(no recent RAID errors)</tr>')

        self.emit_html("""
</tbody>
</table>
</div>""")


    def do_raid_status(self):
        q = (self.session.query(LibRAIDStatus)
             .filter(LibRAIDStatus.time > self.cutoff_gps)
             .filter(~LibRAIDStatus.hostname.startswith('per')) # hack
             .order_by(LibRAIDStatus.time.desc())
             .limit(10))

        self.emit_html("""\
<h2>Recent RAID Status Reports</h2>
<div class="table-responsive">
<table class="table table-striped">
<thead>
<tr>
<th>Date</th>
<th>Host</th>
<th>Num. Disks</th>
<th>Message</th>
</tr>
</thead><tbody>
""")

        did_any = False

        for rec in q:
            self.emit_html('<tr><td>{time}<td>{rec.hostname}<td>{rec.num_disks}<td>{e_info}</tr>',
                           time = Time(rec.time, format='gps').iso,
                           rec = rec,
                           e_info = escape(rec.info),
            )
            did_any = True

        if not did_any:
            self.emit_html('<tr><td><td><td><td>(no recent RAID status reports)</tr>')

        self.emit_html("""
</tbody>
</table>
</div>""")


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


if __name__ == '__main__':
    main()

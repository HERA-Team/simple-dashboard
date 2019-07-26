#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import os
import numpy as np
import re
import redis
from hera_mc import mc, cm_sysutils
from astropy.time import Time


HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HERA Compute Dashboard</title>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
  <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
  <![endif]-->
</head>
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
if (report_age > 1800) {{
    document.getElementById("age").style.color = 'red';
}}
"""

HTML_FOOTER = """\
<div class="row">
<div class="col-md-12">
<p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a></p>
</div>
</div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="{js_name}.js"></script>
</body>
</html>
"""


def main():
    # The standard M&C argument parser
    parser = mc.get_mc_argument_parser()
    # we'll have to add some extra options too
    parser.add_argument('--redishost', dest='redishost', type=str,
                        default='redishost',
                        help=('The host name for redis to connect to, defualts to "redishost"'))
    parser.add_argument('--port', dest='port', type=int, default=6379,
                        help='Redis port to connect.')
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    try:
        redis_db = redis.Redis(args.redishost, port=args.port)
        redis_db.keys()
    except Exception as err:
        raise SystemExit(str(err))

    with db.sessionmaker() as session, \
         open('hex_amp.html', 'wt') as html_hex, \
         open('hex_amp.js', 'wt') as js_hex, \
         open('node_amp.html', 'wt') as html_node, \
         open('node_amp.js', 'wt') as js_node:

        def emit_html_hex(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_hex, end=end)

        def emit_js_hex(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_hex, end=end)

        def emit_html_node(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_node, end=end)

        def emit_js_node(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_node, end=end)

        Emitter(session, redis_db,
                emit_html_hex, emit_js_hex,
                emit_html_node, emit_js_node).emit()


class Emitter(object):

    def __init__(self, session, redis_db,
                 emit_html_hex, emit_js_hex,
                 emit_html_node, emit_js_node):
        self.session = session
        self.redis_db = redis_db

        self.emit_html_hex = emit_html_hex
        self.emit_js_hex = emit_js_hex
        self.emit_html_node = emit_html_node
        self.emit_js_node = emit_js_node
        self.latest = Time(np.frombuffer(self.redis_db.get('auto:timestamp'),
                           dtype=np.float64).item(), format='jd')

        self.now = Time.now()

    def emit_data_array(self, data, fmt, emit_fn):
        emit_fn('[', end='')
        first = True

        for x in data:
            if first:
                first = False
            else:
                emit_fn(',', end='')
            emit_fn(fmt, x=x, end='')

        emit_fn(']', end='')

    def emit_text_array(self, data, fmt, emit_fn):
        emit_fn('[', end='')
        first = True

        for x in data:
            if first:
                first = False
            else:
                emit_fn(',', end='')
            emit_fn("'" + fmt + "'", x=x, end='')

        emit_fn(']', end='')

    def prep_data(self):
        autos = {}
        autos_raw = {}
        amps = {}
        keys = [k.decode() for k in self.redis_db.keys()
                if k.startswith(b'auto') and not k.endswith(b'timestamp')]
        # without item this will be an array which will break database queries
        timestamp = np.frombuffer(self.redis_db.get('auto:timestamp'),
                                  dtype=np.float64).item()
        latest = Time(timestamp, format='jd')
        for key in keys:
            match = re.search(r'auto:(?P<ant>\d+)(?P<pol>e|n)', key)
            if match is not None:
                ant, pol = int(match.group('ant')), match.group('pol')

                autos_raw[(ant, pol)] = np.frombuffer(self.redis_db.get(key),
                                                      dtype=np.float32)
                autos[(ant, pol)] = 10.0 * np.log10(autos_raw[(ant, pol)])

                tmp_amp = np.median(autos_raw[(ant, pol)])
                amps[(ant, pol)] = 10.0 * np.log10(tmp_amp)

        hsession = cm_sysutils.Handling(self.session)
        ants = np.unique([ant for (ant, pol) in autos.keys()])
        pols = np.unique([pol for (ant, pol) in autos.keys()])

        antpos = np.genfromtxt(os.path.join(mc.data_path, "HERA_350.txt"),
                               usecols=(0, 1, 2, 3),
                               dtype={'names': ('ANTNAME', 'EAST', 'NORTH', 'UP'),
                                      'formats': ('<U5', '<f8', '<f8', '<f8')},
                               encoding=None)
        antnames = antpos['ANTNAME']
        antpos = np.array([antpos['EAST'],
                           antpos['NORTH'],
                           antpos['UP']])
        array_center = np.mean(antpos, axis=1, keepdims=True)
        antpos -= array_center

        stations = hsession.get_all_fully_connected_at_date(at_date='now')

        for station in stations:
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants)

        # Get node and PAM info
        node_ind = np.zeros_like(ants, dtype=np.int)
        pam_ind = np.zeros_like(ants, dtype=np.int)
        pam_power = {}
        adc_power = {}
        time_array = {}
        for ant in ants:
            for pol in pols:
                amps.setdefault((ant, pol), np.Inf)
                pam_power.setdefault((ant, pol), np.Inf)
                adc_power.setdefault((ant, pol), np.Inf)
                time_array.setdefault((ant, pol), Time(0, format='gps'))

        for ant_cnt, ant in enumerate(ants):
            station_status = self.session.get_antenna_status(most_recent=True,
                                                             antenna_number=int(ant))
            for status in station_status:
                if status.pam_power is not None:
                    pam_power[(status.antenna_number,
                               status.antenna_feed_pol)] = status.pam_power
                if status.adc_power is not None:
                    adc_power[(status.antenna_number,
                               status.antenna_feed_pol)] = status.adc_power
                if status.time is not None:
                    time_array[(status.antenna_number,
                                status.anenna_feed_pol)] = Time(status.time, format='gps')

            pam_info = hsession.get_part_at_station_from_type('HH{:d}'.format(ant), latest, 'post-amp')
            if pam_info[list(pam_info.keys())[0]]['e'] is not None:
                _pam_num = re.findall(r'PAM(\d+)', pam_info[list(pam_info.keys())[0]]['e'])[0]
                pam_ind[ant_cnt] = np.int(_pam_num)
            else:
                pam_ind[ant_cnt] = -1

            node_info = hsession.get_part_at_station_from_type('HH{:d}'.format(ant), latest, 'node')
            if node_info[list(node_info.keys())[0]]['e'] is not None:
                _node_num = re.findall(r'N(\d+)', node_info[list(node_info.keys())[0]]['e'])[0]
                node_ind[ant_cnt] = np.int(_node_num)
            else:
                node_ind[ant_cnt] = -1

        pams, _pam_ind = np.unique(pam_ind, return_inverse=True)
        nodes, _node_ind = np.unique(node_ind, return_inverse=True)

        xs_offline = np.ma.masked_array(antpos[0, :],
                                        mask=[True if int(name[2:]) in ants
                                              else False for name in antnames])
        ys_offline = np.ma.masked_array(antpos[1, :],
                                        mask=xs_offline.mask).compressed()
        name_offline = np.ma.masked_array(antnames,
                                          mask=xs_offline.mask).compressed()
        xs_offline = xs_offline.compressed()

        ant_index = np.array([np.argwhere('HH{:d}'.format(ant) == antnames)
                              for ant in ants]).squeeze()

        _amps = np.ma.masked_invalid([[amps[ant, pol] for ant in ants]
                                      for pol in pols])
        _adc_power = np.ma.masked_invalid([[adc_power[ant, pol] for ant in ants]
                                           for pol in pols])
        # conver adc power to dB
        _adc_power = 10 * np.log10(_adc_power)
        _pam_power = np.ma.masked_invalid([[pam_power[ant, pol] for ant in ants]
                                           for pol in pols])
        time_array = Time([[time_array[ant, pol].gps
                            for ant in ants] for pol in pols], format='gps')
        xs = np.ma.masked_array(antpos[0, ant_index], mask=_amps[0].mask)
        ys = np.ma.masked_array([antpos[1, ant_index] + 3 * (pol_cnt - .5)
                                 for pol_cnt, pol in enumerate(pols)],
                                mask=_amps.mask)
        _text = np.array([[antnames[ant_index[ant_cnt]] + pol
                           + '<br>' + 'PAM #: ' + str(pam_ind[ant_cnt])
                           + '<br>' + 'Node #:' + str(node_ind[ant_cnt])
                           for ant_cnt, ant in enumerate(ants)]
                          for pol_cnt, pol in enumerate(pols)], dtype='object')

        #  want to format No Data where data was not retrieved for each type of power
        for pol_cnt, pol in enumerate(pols):
            for ant_cnt, ant in enumerate(ants):
                for _name, _power in zip(['Amp', 'PAM', 'ADC'], [_amps, _pam_power, _adc_power]):
                    if not _power.mask[pol_cnt, ant_cnt]:
                        _text[pol_cnt, ant_cnt] += '<br>' + _name + ' [dB]: {0:.2f}'.format(_power[pol_cnt, ant_cnt])
                    else:
                        _text[pol_cnt, ant_cnt] += '<br>' + _name + ' [dB]: No Data'
                if time_array[pol_cnt, ant_cnt].gps == 0:
                    _text[pol_cnt, ant_cnt] += '<br>' + 'SNAP timestamp: No Data'
                else:
                    _text[pol_cnt, ant_cnt] += '<br>' + 'SNAP timestamp: {0} ({1:.6f})'.format(time_array[pol_cnt, ant_cnt].iso, time_array[pol_cnt, ant_cnt].jd)

        self.emit_js_hex('var data = [')

        amp_mask = ['true']
        pam_mask = ['true']
        adc_mask = ['true']
        # Offline antennas
        self.emit_js_hex('{{x: ', end='')
        self.emit_data_array(xs_offline, '{x:.3f}', self.emit_js_hex)
        self.emit_js_hex(',\ny :', end='')
        self.emit_data_array(ys_offline, '{x:.3f}', self.emit_js_hex)
        self.emit_js_hex(',\ntext:', end='')
        self.emit_text_array(name_offline, '{x}', self.emit_js_hex)
        self.emit_js_hex(",\nmode: 'markers'", end='')
        self.emit_js_hex(",\nvisible: true", end='')
        self.emit_js_hex(",\nmarker: {{color: 'black', size : 14,", end='')
        self.emit_js_hex("opacity: .5, symbol: 'hexagon' }}", end='')
        self.emit_js_hex(",\nhovertemplate: '%{{text}}<br>OFFLINE<extra></extra>' ", end='')
        self.emit_js_hex('}},', end='\n')

        #  for each type of power, loop over pols and print out the data
        #  save up a mask array used for the buttons later
        #  also plot the bad ones!3
        colorscale = "Viridis"
        for pow_ind, power in enumerate([_amps, _pam_power, _adc_power]):
            if pow_ind == 0:
                self.emit_js_hex("// AMPLITUDE DATA ")
            elif pow_ind == 1:
                self.emit_js_hex("// PAM DATA ")
            else:
                self.emit_js_hex("// ADC DATA ")

            if power.compressed().size > 0:
                vmax = np.max(power.compressed())
                vmin = np.min(power.compressed())
            else:
                vmax = 1
                vmin = 0

            for pol_ind, pol in enumerate(pols):
                if pow_ind == 0:
                    amp_mask.extend(['true'] * 2)
                    pam_mask.extend(['false'] * 2)
                    adc_mask.extend(['false'] * 2)
                    visible = 'true'
                    title = 'dB'

                elif pow_ind == 1:
                    amp_mask.extend(['false'] * 2)
                    pam_mask.extend(['true'] * 2)
                    adc_mask.extend(['false'] * 2)
                    visible = 'false'
                    title = 'dB'
                else:
                    amp_mask.extend(['false'] * 2)
                    pam_mask.extend(['false'] * 2)
                    adc_mask.extend(['true'] * 2)
                    visible = 'false'
                    title = 'dB'

                self.emit_js_hex('{{x: ', end='')
                self.emit_data_array(xs.data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_hex)
                self.emit_js_hex(',\ny: ', end='')
                self.emit_data_array(ys[pol_ind].data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_hex)
                self.emit_js_hex(",\nmode: 'markers'", end='')
                self.emit_js_hex(",\nvisible: {visible}", visible=visible, end='')
                self.emit_js_hex(",\ntext: ", end='')
                self.emit_text_array(_text[pol_ind][~power[pol_ind].mask], '{x}', self.emit_js_hex)
                self.emit_js_hex(',\n marker: {{  color:', end='')
                self.emit_data_array(power[pol_ind].data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_hex)
                self.emit_js_hex(", cmin: {vmin}, cmax: {vmax}, ", vmin=vmin, vmax=vmax, end='')
                self.emit_js_hex("colorscale: '{colorscale}', size: 14,", colorscale=colorscale, end='')
                self.emit_js_hex("\ncolorbar: {{thickness: 20, title: '{title}'}}", title=title, end='')
                self.emit_js_hex("}},\nhovertemplate: '%{{text}}<extra></extra>'", end='')
                # self.emit_js_hex("Amp [dB]: %{{marker.color:.3f}}", end='')
                self.emit_js_hex('}},', end='\n')

                self.emit_js_hex('{{x: ', end='')
                self.emit_data_array(xs.data[power[pol_ind].mask], '{x:.3f}', self.emit_js_hex)
                self.emit_js_hex(',\ny: ', end='')
                self.emit_data_array(ys[pol_ind].data[power[pol_ind].mask], '{x:.3f}', self.emit_js_hex)
                self.emit_js_hex(",\nmode: 'markers'", end='')
                self.emit_js_hex(",\nvisible: {visible}", visible=visible, end='')
                self.emit_js_hex(",\ntext: ", end='')
                self.emit_text_array(_text[pol_ind][power[pol_ind].mask], '{x}', self.emit_js_hex)
                self.emit_js_hex(",\n marker: {{  color: 'orange'", end='')
                self.emit_js_hex(", size: 14", end='')
                self.emit_js_hex("}},\nhovertemplate: '%{{text}}<extra></extra>'", end='')
                self.emit_js_hex('}},\n', end='\n')

        self.emit_js_hex(']', end='\n')

        self.emit_js_hex(' var updatemenus=[')
        self.emit_js_hex('{{buttons : [')

        # Amplitude Button
        self.emit_js_hex('{{')
        self.emit_js_hex('args: [')
        self.emit_js_hex("{{'visible': ", end='')
        self.emit_data_array(amp_mask, '{x}', self.emit_js_hex)
        self.emit_js_hex("}},\n{{'title': '',")
        self.emit_js_hex("'annotations': {{}} }}")
        self.emit_js_hex('],')
        self.emit_js_hex("label: 'Auto Corr',")
        self.emit_js_hex("method: 'update'")
        self.emit_js_hex('}},')

        # PAMS buttons
        self.emit_js_hex('{{')
        self.emit_js_hex('args: [')
        self.emit_js_hex("{{'visible': ", end='')
        self.emit_data_array(pam_mask, '{x}', self.emit_js_hex)
        self.emit_js_hex("}},\n{{'title': '',")
        self.emit_js_hex("'annotations': {{}} }}")
        self.emit_js_hex('],')
        self.emit_js_hex("label: 'Pam Power',")
        self.emit_js_hex("method: 'update'")
        self.emit_js_hex('}},')

        # ADC buttons
        self.emit_js_hex('{{')
        self.emit_js_hex('args: [')
        self.emit_js_hex("{{'visible': ", end='')
        self.emit_data_array(adc_mask, '{x}', self.emit_js_hex)
        self.emit_js_hex("}},\n{{'title': '',")
        self.emit_js_hex("'annotations': {{}} }}")
        self.emit_js_hex('],')
        self.emit_js_hex("label: 'ADC Power',")
        self.emit_js_hex("method: 'update'")
        self.emit_js_hex('}},')

        self.emit_js_hex('],', end='\n')
        self.emit_js_hex('showactive: true,')
        self.emit_js_hex("type: 'buttons',")
        self.emit_js_hex('}},')
        self.emit_js_hex(']', end='\n')

        self.emit_js_hex("""

var layout = {{
    // title: 'Median Auto Amplitude',
    xaxis: {{title: 'East-Westh Position [m]'}},
    yaxis: {{title: 'North-South Position [m]'}},
    margin: {{
        t: 10,
    }},
    autosize: true,
    showlegend: false,
    updatemenus: updatemenus,
    hovermode: 'closest'
}};

Plotly.plot("plotly-hex", data, layout, {{responsive: true}});
// window.onresize = function() {{
// Plotly.relayout("plotly-div", {{
//                    width: 0.7 * window.innerWidth,
//                    height: 0.8 * window.innerHeight
//                          }})
//}}
        """)

        self.emit_js_node("var data = [")
        amp_mask = []
        pam_mask = []
        adc_mask = []

        vmax = [np.max(power.compressed()) if power.compressed().size > 1 else 1
                for power in [_amps, _pam_power, _adc_power]]
        vmin = [np.min(power.compressed()) if power.compressed().size > 1 else 0
                for power in [_amps, _pam_power, _adc_power]]
        for node in nodes:
            node_index = np.where(node_ind == node)[0]

            ys = np.ma.masked_array([np.arange(node_index.size) + .3 * pol_cnt
                                     for pol_cnt, pol in enumerate(pols)], mask=_amps[:, node_index].mask)
            xs = np.zeros_like(ys)
            xs[:] = node
            __amps = _amps[:, node_index]
            __adc = _adc_power[:, node_index]
            __pam = _pam_power[:, node_index]
            __text = _text[:, node_index]

            for pow_ind, power in enumerate([__amps, __pam, __adc]):
                if pow_ind == 0:
                    self.emit_js_node("// AMPLITUDE DATA ")
                elif pow_ind == 1:
                    self.emit_js_node("// PAM DATA ")
                else:
                    self.emit_js_node("// ADC DATA ")

                for pol_ind, pol in enumerate(pols):
                    if pow_ind == 0:
                        amp_mask.extend(['true'] * 2)
                        pam_mask.extend(['false'] * 2)
                        adc_mask.extend(['false'] * 2)
                        visible = 'true'
                        title = 'dB'

                    elif pow_ind == 1:
                        amp_mask.extend(['false'] * 2)
                        pam_mask.extend(['true'] * 2)
                        adc_mask.extend(['false'] * 2)
                        visible = 'false'
                        title = 'dB'
                    else:
                        amp_mask.extend(['false'] * 2)
                        pam_mask.extend(['false'] * 2)
                        adc_mask.extend(['true'] * 2)
                        visible = 'false'
                        title = 'dB'

                    self.emit_js_node('{{x: ', end='')
                    self.emit_data_array(xs[pol_ind].data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_node)
                    self.emit_js_node(',\ny: ', end='')
                    self.emit_data_array(ys[pol_ind].data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_node)
                    self.emit_js_node(",\nmode: 'markers'", end='')
                    self.emit_js_node(",\nvisible: {visible}", visible=visible, end='')
                    self.emit_js_node(",\ntext: ", end='')
                    self.emit_text_array(__text[pol_ind][~power[pol_ind].mask], '{x}', self.emit_js_node)
                    self.emit_js_node(',\n marker: {{  color:', end='')
                    self.emit_data_array(power[pol_ind].data[~power[pol_ind].mask], '{x:.3f}', self.emit_js_node)
                    self.emit_js_node(", cmin: {vmin}, cmax: {vmax}, ", vmin=vmin[pow_ind], vmax=vmax[pow_ind], end='')
                    self.emit_js_node("colorscale: '{colorscale}', size: 14,", colorscale=colorscale, end='')
                    self.emit_js_node("\ncolorbar: {{thickness: 20, title: '{title}'}}", title=title, end='')
                    self.emit_js_node("}},\nhovertemplate: '%{{text}}<extra></extra>'", end='')
                    self.emit_js_node('}},', end='\n')

                    self.emit_js_node('{{x: ', end='')
                    self.emit_data_array(xs[pol_ind].data[power[pol_ind].mask], '{x:.3f}', self.emit_js_node)
                    self.emit_js_node(',\ny: ', end='')
                    self.emit_data_array(ys[pol_ind].data[power[pol_ind].mask], '{x:.3f}', self.emit_js_node)
                    self.emit_js_node(",\nmode: 'markers'", end='')
                    self.emit_js_node(",\nvisible: {visible}", visible=visible, end='')
                    self.emit_js_node(",\ntext: ", end='')
                    self.emit_text_array(__text[pol_ind][power[pol_ind].mask], '{x}', self.emit_js_node)
                    self.emit_js_node(",\n marker: {{  color: 'orange'", end='')
                    self.emit_js_node(", size: 14", end='')
                    self.emit_js_node("}},\nhovertemplate: '%{{text}}<extra></extra>'", end='')
                    self.emit_js_node('}},\n', end='\n')

        self.emit_js_node(']', end='\n')

        self.emit_js_node(' var updatemenus=[')
        self.emit_js_node('{{buttons : [')

        # Amplitude Button
        self.emit_js_node('{{')
        self.emit_js_node('args: [')
        self.emit_js_node("{{'visible': ", end='')
        self.emit_data_array(amp_mask, '{x}', self.emit_js_node)
        self.emit_js_node("}},\n{{'title': '',")
        self.emit_js_node("'annotations': {{}} }}")
        self.emit_js_node('],')
        self.emit_js_node("label: 'Auto Corr',")
        self.emit_js_node("method: 'update'")
        self.emit_js_node('}},')

        # PAMS buttons
        self.emit_js_node('{{')
        self.emit_js_node('args: [')
        self.emit_js_node("{{'visible': ", end='')
        self.emit_data_array(pam_mask, '{x}', self.emit_js_node)
        self.emit_js_node("}},\n{{'title': '',")
        self.emit_js_node("'annotations': {{}} }}")
        self.emit_js_node('],')
        self.emit_js_node("label: 'Pam Power',")
        self.emit_js_node("method: 'update'")
        self.emit_js_node('}},')

        # ADC buttons
        self.emit_js_node('{{')
        self.emit_js_node('args: [')
        self.emit_js_node("{{'visible': ", end='')
        self.emit_data_array(adc_mask, '{x}', self.emit_js_node)
        self.emit_js_node("}},\n{{'title': '',")
        self.emit_js_node("'annotations': {{}} }}")
        self.emit_js_node('],')
        self.emit_js_node("label: 'ADC Power',")
        self.emit_js_node("method: 'update'")
        self.emit_js_node('}},')

        self.emit_js_node('],', end='\n')
        self.emit_js_node('showactive: true,')
        self.emit_js_node("type: 'buttons',")
        self.emit_js_node('}},')
        self.emit_js_node(']', end='\n')

        self.emit_js_node("""

var layout = {{
    // title: 'Power vs Node',
    xaxis: {{title: 'Node Number',
             dtick:1,
             tick0: 0,
             shogrid: false,
             zeroline: false}},
    yaxis: {{showticklabels: false,
             showgrid: false,
             zeroline: false}},
    margin: {{
           t: 10,
    }},
    autosize: true,
    showlegend: false,
    updatemenus: updatemenus,
    hovermode: 'closest'
}};

Plotly.plot("plotly-node", data, layout, {{responsive: true}});
//window.onresize = function() {{
// Plotly.relayout("plotly-div", {{
//                    width: 0.7 * window.innerWidth,
//                    height: 0.8 * window.innerHeight
//                          }})
// }}""")

    def emit(self):
        self.emit_html_hex(HTML_HEADER)

        self.emit_html_hex("""\
<body>
<div class="container">
  <div class="row">
    <div id="plotly-hex" class="col-md-12", style="height: 85vh"></div>
  </div>
  <div class="row">
    <div class="col-md-12">
        <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
    </div>
    <div class="col-md-12">
        <p class="text-center">Data observed on {iso_date} (JD: {jd_date:.6f})</p>
    </div>
  </div>
""", gen_date=self.now.iso,
     iso_date=self.latest.iso,
     jd_date=self.latest.jd)

        self.emit_js_hex(JS_HEADER,
                         gen_time_unix_ms=self.now.unix * 1000,
                         )

        self.emit_html_node(HTML_HEADER)
        self.emit_html_node("""\
 <body>
 <div class="container">
   <div class="row">
     <div id="plotly-node" class="col-md-12", style="height: 70vh"></div>
   </div>
   <div class="row">
     <div class="col-md-12">
         <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
     </div>
     <div class="col-md-12">
         <p class="text-center">Data observed on {iso_date} (JD: {jd_date:.6f})</p>
     </div>
   </div>
 """, gen_date=self.now.iso,
      iso_date=self.latest.iso,
      jd_date=self.latest.jd)

        self.emit_js_node(JS_HEADER,
                          gen_time_unix_ms=self.now.unix * 1000,
                          )
        self.prep_data()

        self.emit_html_hex(HTML_FOOTER, js_name='hex_amp')
        self.emit_html_node(HTML_FOOTER, js_name='node_amp')


if __name__ == '__main__':
    main()

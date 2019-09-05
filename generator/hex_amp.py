#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import os
import sys
import numpy as np
import re
import redis
from hera_mc import mc, cm_sysutils
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader


def main():
    # templates are stored relative to the script dir
    script_dir = os.path.dirname(os.path.realpath(__file__))
    template_dir = os.path.join(script_dir, 'templates')

    env = Environment(loader=FileSystemLoader(template_dir))
    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

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

    with db.sessionmaker() as session:
        # without item this will be an array which will break database queries
        latest = Time(np.frombuffer(redis_db.get('auto:timestamp'),
                      dtype=np.float64).item(), format='jd')

        now = Time.now()
        autos = {}
        autos_raw = {}
        amps = {}
        keys = [k.decode() for k in redis_db.keys()
                if k.startswith(b'auto') and not k.endswith(b'timestamp')]

        for key in keys:
            match = re.search(r'auto:(?P<ant>\d+)(?P<pol>e|n)', key)
            if match is not None:
                ant, pol = int(match.group('ant')), match.group('pol')

                autos_raw[(ant, pol)] = np.frombuffer(redis_db.get(key),
                                                      dtype=np.float32)
                autos[(ant, pol)] = 10.0 * np.log10(autos_raw[(ant, pol)])

                tmp_amp = np.median(autos_raw[(ant, pol)])
                amps[(ant, pol)] = 10.0 * np.log10(tmp_amp)

        hsession = cm_sysutils.Handling(session)
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
        # defaul the snap name to "No Data"
        hostname = np.full_like(ants, 'No\tData', dtype=object)
        snap_serial = np.full_like(ants, 'No\tData', dtype=object)

        pam_power = {}
        adc_power = {}
        time_array = {}
        for ant in ants:
            for pol in pols:
                amps.setdefault((ant, pol), np.Inf)
                pam_power.setdefault((ant, pol), np.Inf)
                adc_power.setdefault((ant, pol), np.Inf)
                time_array.setdefault((ant, pol), now - Time(0, format='gps'))

        for ant_cnt, ant in enumerate(ants):
            station_status = session.get_antenna_status(most_recent=True,
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
                                status.antenna_feed_pol)] = now - Time(status.time, format='gps')

            # Try to get the snap info. Output is a dictionary with 'e' and 'n' keys
            mc_name = 'HH{:d}'.format(ant)
            snap_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'snap')
            # get the first key in the dict to index easier
            _key = list(snap_info.keys())[0]
            if snap_info[_key]['e'] is not None:
                snap_serial[ant_cnt] = snap_info[_key]['e']

            # Try to get the pam info. Output is a dictionary with 'e' and 'n' keys
            pam_info = hsession.get_part_at_station_from_type(mc_name,
                                                              'now', 'post-amp')
            # get the first key in the dict to index easier
            _key = list(pam_info.keys())[0]
            if pam_info[_key]['e'] is not None:
                _pam_num = re.findall(r'PAM(\d+)', pam_info[_key]['e'])[0]
                pam_ind[ant_cnt] = np.int(_pam_num)
            else:
                pam_ind[ant_cnt] = -1

            # Try to get the ADC info. Output is a dictionary with 'e' and 'n' keys
            node_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'node')
            # get the first key in the dict to index easier
            _key = list(node_info.keys())[0]
            if node_info[_key]['e'] is not None:
                _node_num = re.findall(r'N(\d+)', node_info[_key]['e'])[0]
                node_ind[ant_cnt] = np.int(_node_num)

                snap_status = session.get_snap_status(most_recent=True,
                                                      nodeID=np.int(_node_num))
                for _status in snap_status:
                    if _status.serial_number == snap_serial[ant_cnt]:
                        hostname[ant_cnt] = _status.hostname
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
        time_array = np.array([[time_array[ant, pol].to('hour').value
                               for ant in ants] for pol in pols])
        xs = np.ma.masked_array(antpos[0, ant_index], mask=_amps[0].mask)
        ys = np.ma.masked_array([antpos[1, ant_index] + 3 * (pol_cnt - .5)
                                 for pol_cnt, pol in enumerate(pols)],
                                mask=_amps.mask)
        _text = np.array([[antnames[ant_index[ant_cnt]] + pol
                           + '<br>' + str(hostname[ant_cnt])
                           + '<br>' + 'PAM\t#:\t' + str(pam_ind[ant_cnt])
                           for ant_cnt, ant in enumerate(ants)]
                          for pol_cnt, pol in enumerate(pols)], dtype='object')

        #  want to format No Data where data was not retrieved for each type of power
        for pol_cnt, pol in enumerate(pols):
            for ant_cnt, ant in enumerate(ants):
                for _name, _power in zip(['Auto', 'PAM', 'ADC'], [_amps, _pam_power, _adc_power]):
                    if not _power.mask[pol_cnt, ant_cnt]:
                        _text[pol_cnt, ant_cnt] += '<br>' + _name + '\t[dB]:\t{0:.2f}'.format(_power[pol_cnt, ant_cnt])
                    else:
                        _text[pol_cnt, ant_cnt] += '<br>' + _name + '\t[dB]:\tNo\tData'
                if time_array[pol_cnt, ant_cnt] > 2 * 24 * 365:
                    # if the value is older than 2 years it is bad
                    # value are stored in hours.
                    # 2 was chosen arbitraritly.
                    _text[pol_cnt, ant_cnt] += '<br>' + 'PAM/ADC\t-\tNo\tData'
                else:
                    _text[pol_cnt, ant_cnt] += '<br>' + 'PAM/ADC:\t{0:.2f}\thrs\told'.format(time_array[pol_cnt, ant_cnt])
        amp_mask = [True]
        pam_mask = [True]
        adc_mask = [True]
        # Offline antennas
        data_hex = []
        offline_ants = {"x": xs_offline.tolist(),
                        "y": ys_offline.tolist(),
                        "text": name_offline.tolist(),
                        "mode": 'markers',
                        "visible": True,
                        "marker": {"color": 'black',
                                   "size": 14,
                                   "opacity": .5,
                                   "symbol": 'hexagon'},
                        "hovertemplate": "%{text}<br>OFFLINE<extra></extra>"}
        data_hex.append(offline_ants)

        #  for each type of power, loop over pols and print out the data
        #  save up a mask array used for the buttons later
        #  also plot the bad ones!3
        colorscale = "Viridis"
        for pow_ind, power in enumerate([_amps, _pam_power, _adc_power]):
            if power.compressed().size > 0:
                vmax = np.max(power.compressed())
                vmin = np.min(power.compressed())
            else:
                vmax = 1
                vmin = 0

            for pol_ind, pol in enumerate(pols):
                cbar_title = 'dB'
                if pow_ind == 0:
                    amp_mask.extend([True] * 2)
                    pam_mask.extend([False] * 2)
                    adc_mask.extend([False] * 2)
                    visible = True

                elif pow_ind == 1:
                    amp_mask.extend([False] * 2)
                    pam_mask.extend([True] * 2)
                    adc_mask.extend([False] * 2)
                    visible = False
                else:
                    amp_mask.extend([False] * 2)
                    pam_mask.extend([False] * 2)
                    adc_mask.extend([True] * 2)
                    visible = False

                _power = {"x": xs.data[~power[pol_ind].mask].tolist(),
                          "y": ys[pol_ind].data[~power[pol_ind].mask].tolist(),
                          "text": _text[pol_ind][~power[pol_ind].mask].tolist(),
                          "mode": 'markers',
                          "visible": visible,
                          "marker": {"color": power[pol_ind].data[~power[pol_ind].mask].tolist(),
                                     "size": 14,
                                     "cmin": vmin,
                                     "cmax": vmax,
                                     "colorscale": colorscale,
                                     "colorbar": {"thickness": 20,
                                                  "title": cbar_title}
                                     },
                          "hovertemplate": "%{text}<extra></extra>"}

                data_hex.append(_power)

                _power_offline = {"x": xs.data[power[pol_ind].mask].tolist(),
                                  "y": ys[pol_ind].data[power[pol_ind].mask].tolist(),
                                  "text": _text[pol_ind][power[pol_ind].mask].tolist(),
                                  "mode": 'markers',
                                  "visible": visible,
                                  "marker": {"color": "orange",
                                             "size": 14,
                                             "cmin": vmin,
                                             "cmax": vmax,
                                             "colorscale": colorscale,
                                             "colorbar": {"thickness": 20,
                                                          "title": cbar_title}
                                             },
                                  "hovertemplate": "%{text}<extra></extra>"}
                data_hex.append(_power_offline)

        buttons = []
        amp_button = {"args": [{"visible": amp_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "Auto Corr",
                      "method": "restyle"
                      }
        buttons.append(amp_button)

        pam_button = {"args": [{"visible": pam_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "Pam Power",
                      "method": "restyle"
                      }
        buttons.append(pam_button)

        adc_button = {"args": [{"visible": adc_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "ADC Power",
                      "method": "restyle"
                      }
        buttons.append(adc_button)

        updatemenus_hex = [{"buttons": buttons,
                            "show_active": True,
                            "type": "buttons"
                            }
                           ]

        layout_hex = {"xaxis": {"title": "East-West Position [m]"},
                      "yaxis": {"title": "North-South Position [m]"},
                      "hoverlabel": {"align": "left"},
                      "margin": {"t": 10},
                      "autosize": True,
                      "showlegend": False,
                      "hovermode": "closest"
                      }

        # Render all the power vs position files
        plotname = "plotly-hex"
        html_template = env.get_template("plotly_base.html")
        js_template = env.get_template("plotly_updatemenus.js")

        rendered_hex_html = html_template.render(plotname=plotname,
                                                 data_type="Auto correlations",
                                                 plotstyle="height: 85vh",
                                                 gen_date=now.iso,
                                                 data_date=latest.iso,
                                                 data_jd_date=latest.jd,
                                                 js_name="hex_amp",
                                                 now=now.iso,
                                                 scriptname=os.path.basename(__file__),
                                                 hostname=hostname)

        rendered_hex_js = js_template.render(gen_time_unix_ms=now.unix * 1000,
                                             data=data_hex,
                                             layout=layout_hex,
                                             updatemenus=updatemenus_hex,
                                             plotname=plotname)

        with open('hex_amp.html', 'w') as h_file:
            h_file.write(rendered_hex_html)

        with open('hex_amp.js', 'w') as js_file:
            js_file.write(rendered_hex_js)

        # now prepare the data to be plotted vs node number
        data_node = []

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
                                     for pol_cnt, pol in enumerate(pols)],
                                    mask=_amps[:, node_index].mask)
            xs = np.zeros_like(ys)
            xs[:] = node
            __amps = _amps[:, node_index]
            __adc = _adc_power[:, node_index]
            __pam = _pam_power[:, node_index]
            __text = _text[:, node_index]

            cbar_title = 'dB'
            for pow_ind, power in enumerate([__amps, __pam, __adc]):

                for pol_ind, pol in enumerate(pols):
                    if pow_ind == 0:
                        amp_mask.extend([True] * 2)
                        pam_mask.extend([False] * 2)
                        adc_mask.extend([False] * 2)
                        visible = True
                    elif pow_ind == 1:
                        amp_mask.extend([False] * 2)
                        pam_mask.extend([True] * 2)
                        adc_mask.extend([False] * 2)
                        visible = False
                    else:
                        amp_mask.extend([False] * 2)
                        pam_mask.extend([False] * 2)
                        adc_mask.extend([True] * 2)
                        visible = False

                    _power = {"x": xs[pol_ind].data[~power[pol_ind].mask].tolist(),
                              "y": ys[pol_ind].data[~power[pol_ind].mask].tolist(),
                              "text": __text[pol_ind][~power[pol_ind].mask].tolist(),
                              "mode": 'markers',
                              "visible": visible,
                              "marker": {"color": power[pol_ind].data[~power[pol_ind].mask].tolist(),
                                         "size": 14,
                                         "cmin": vmin[pow_ind],
                                         "cmax": vmax[pow_ind],
                                         "colorscale": colorscale,
                                         "colorbar": {"thickness": 20,
                                                      "title": cbar_title}
                                         },
                              "hovertemplate": "%{text}<extra></extra>"}

                    data_node.append(_power)

                    _power_offline = {"x": xs[pol_ind].data[power[pol_ind].mask].tolist(),
                                      "y": ys[pol_ind].data[power[pol_ind].mask].tolist(),
                                      "text": __text[pol_ind][power[pol_ind].mask].tolist(),
                                      "mode": 'markers',
                                      "visible": visible,
                                      "marker": {"color": "orange",
                                                 "size": 14,
                                                 "cmin": vmin[pow_ind],
                                                 "cmax": vmax[pow_ind],
                                                 "colorscale": colorscale,
                                                 "colorbar": {"thickness": 20,
                                                              "title": cbar_title
                                                              }
                                                 },
                                      "hovertemplate": "%{text}<extra></extra>"}

                    data_node.append(_power_offline)
        buttons = []
        amp_button = {"args": [{"visible": amp_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "Auto Corr",
                      "method": "restyle"
                      }
        buttons.append(amp_button)

        pam_button = {"args": [{"visible": pam_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "Pam Power",
                      "method": "restyle"
                      }
        buttons.append(pam_button)

        adc_button = {"args": [{"visible": adc_mask},
                               {"title": '',
                                "annotations": {}
                                }
                               ],
                      "label": "ADC Power",
                      "method": "restyle"
                      }
        buttons.append(adc_button)

        updatemenus_node = [{"buttons": buttons,
                             "show_active": True,
                             "type": "buttons"
                             }
                            ]

        layout_node = {"xaxis": {"title": "Node Number",
                                 "dtick": 1,
                                 "tick0": 0,
                                 "showgrid": False,
                                 "zeroline": False},
                       "yaxis": {"showticklabels": False,
                                 "showgrid": False,
                                 "zeroline": False},
                       "hoverlabel": {"align": "left"},
                       "margin": {"t": 10},
                       "autosize": True,
                       "showlegend": False,
                       "hovermode": "closest"
                       }

        # Render all the power vs ndde files
        plotname = "plotly-node"
        html_template = env.get_template("plotly_base.html")
        js_template = env.get_template("plotly_updatemenus.js")

        rendered_hex_html = html_template.render(plotname=plotname,
                                                 data_type="Auto correlations",
                                                 plotstyle="height: 85vh",
                                                 gen_date=now.iso,
                                                 data_date=latest.iso,
                                                 data_jd_date=latest.jd,
                                                 js_name="node_amp",
                                                 now=now.iso,
                                                 scriptname=os.path.basename(__file__),
                                                 hostname=computer_hostname)

        rendered_hex_js = js_template.render(gen_time_unix_ms=now.unix * 1000,
                                             data=data_node,
                                             layout=layout_node,
                                             updatemenus=updatemenus_node,
                                             plotname=plotname)

        with open('node_amp.html', 'w') as h_file:
            h_file.write(rendered_hex_html)

        with open('node_amp.js', 'w') as js_file:
            js_file.write(rendered_hex_js)


if __name__ == '__main__':
    main()

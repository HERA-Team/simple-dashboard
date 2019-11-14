#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page displaying issues from HERA-Team/HERA_Commissioning."""

from __future__ import absolute_import, division, print_function

import os
import sys
import github3
import argparse
import requests
import numpy as np
from dateutil import parser as dateparser
from datetime import timedelta, timezone
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader


def main(pem_file, app_id_file):
    t1 = Time.now()
    # templates are stored relative to the script dir
    # stored one level up, find the parent directory
    # and split the parent directory away
    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], 'templates')

    env = Environment(loader=FileSystemLoader(template_dir),
                      trim_blocks=True)

    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

    all_tables = []

    table = {}
    table["title"] = "Commissioning Daily Logs"
    table["div_style"] = 'style="max-height: 1500px;"'
    table["headers"] = [
        "Julian Date",
        "Issue",
        "Notes",
        "Nightly Notebook",
        "New Issues Opened<br>On This Day",
        "Total Open Issues<br>On This Day"
    ]
    table["rows"] = []

    with open(pem_file, 'r') as key_file:
        key = key_file.read()
    with open(app_id_file, 'r') as id_file:
        app_id = int(id_file.read())

    gh = github3.github.GitHub()
    gh.login_as_app(key.encode(), app_id)
    app = gh.authenticated_app()
    inst = gh.app_installation_for_repository('mkolopanis', 'mwa_simpleds')
    # inst = gh.app_installation_for_repository('HERA-Team', 'HERA_Commissioning')
    gh.login_as_app_installation(key.encode(), app.id, inst.id)

    # repo = gh.repository('HERA-Team', "HERA_Commissioning")
    repo = gh.repository('mkolopanis', "simpleDS")

    # issues = repo.issues(labels='Daily')
    issues = repo.issues(state='open')

    notebook_link = ("https://github.com/HERA-Team/H3C_plots"
                     "/blob/master/data_inspect_{}.ipynb")
    # replace the github.com with nbviwer.juptyer.org/github for actual
    # viewing link
    notebook_view = notebook_link.replace(
        'github.com', 'nbviewer.jupyter.org/github'
    )
    for cnt, issue in enumerate(issues):
        row = {}
        # jd = issue.title
        jd = int(np.floor(Time(issue.created_at, format='datetime').jd))
        # jd = int(issue.title.split(' ')[-1])
        try:
            obs_date = Time(jd, format='jd')
        except ValueError:
            obs_date = Time(2458600 + cnt*10, format='jd')

        obs_date = dateparser.parse(obs_date.iso).astimezone(timezone.utc)
        obs_end = obs_date + timedelta(days=1)

        # count the number of issues opened in this day
        # cound the number of total issues on this day
        num_opened = 0
        num_open_on_day = 0

        for _iss in repo.issues(state='all'):
            if obs_date <= _iss.created_at.astimezone(timezone.utc) <= obs_end:
                num_opened += 1
            if _iss.created_at.astimezone(timezone.utc) <= obs_end:
                if (_iss.closed_at is not None
                        and _iss.closed_at.astimezone(timezone.utc) >= obs_end):
                    num_open_on_day += 1
                elif _iss.closed_at is None:
                    num_open_on_day += 1
                else:
                    pass

        # See if the nightly notebook is up for that day
        request = requests.get(notebook_link.format(jd))
        if request.status_code == 200:
            url = notebook_view.format(jd)
            notebook = '<a href={url}>"Available"</a>'.format(url=url)
        else:
            notebook = "Unavaliable"

        number = issue.number
        link = issue.url.replace('api.', '').replace('repos/', '')
        other_labels = [lab.name for lab in issue.labels() if lab.name != 'Daily']
        display_number = '<a href={url}>{number}</a>'.format(url=link,
                                                             number=number)
        row["text"] = [jd,
                       display_number,
                       ' '.join(other_labels),
                       notebook,
                       num_opened,
                       num_open_on_day
                       ]
        table["rows"].append(row)

    all_tables.append(table)
    html_template = env.get_template("tables_with_footer.html")

    rendered_html = html_template.render(tables=all_tables,
                                         gen_date=Time.now().iso,
                                         gen_time_unix_ms=Time.now().unix * 1000,
                                         scriptname=os.path.basename(__file__),
                                         hostname=computer_hostname,
                                         colsize='6  col-md-offset-3')

    with open('issue_log.html', 'w') as h_file:
        h_file.write(rendered_html)

    print("Took: ", (Time.now() - t1).to('min'))
    return


if __name__ == "__main__":
    desc = ('Get list of Issues from the HERA Commissioning with the supplied '
            'credentials.')
    parser = argparse.ArgumentParser(description=desc,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(dest='pem_file', type=str, nargs=1,
                        help=("The pem file of the secret key for the app.")
                        )
    parser.add_argument('--app_id', '-a', dest='app_id_file',
                        type=str, nargs=1,
                        help='A text file with the app_id inside')
    args = parser.parse_args()

    main(pem_file=args.pem_file[0],
         app_id_file=args.app_id_file[0]
         )

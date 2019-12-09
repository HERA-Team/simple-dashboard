#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page displaying issues from HERA-Team/HERA_Commissioning."""

from __future__ import absolute_import, division, print_function

import os
import sys
import re
import github3
import argparse
import requests
import bisect
import numpy as np
from dateutil import parser as dateparser
from datetime import datetime, timedelta, timezone
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader

github_link_regex = r'data-url="([^"]+)"'


def main(pem_file, app_id_file, repo_owner, repo_name, time_window, all_issues=False):
    t1 = Time.now()
    # templates are stored relative to the script dir
    # stored one level up, find the parent directory
    # and split the parent directory away
    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], "templates")

    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)

    jd_today = int(np.floor(t1.jd))
    jd_list = []

    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

    all_tables = []

    table = {}
    table["title"] = "Commissioning Daily Logs"
    table["div_style"] = 'style="max-height: 82%; text-align: center; overflow-x: auto; overflow-y: scroll;"'

    table["headers"] = [
        "Julian Date",
        "Related Issues",
        "Log Labels",
        "Nightly Notebook",
        "RFI Notebook",
        "New Issues Opened<br>On This Day",
        "Total Open Issues<br>On This Day",
    ]
    table["rows"] = []

    with open(pem_file, "r") as key_file:
        key = key_file.read()
    with open(app_id_file, "r") as id_file:
        app_id = int(id_file.read())

    gh = github3.github.GitHub()
    if args.repo_name == "HERA_Commissioning":
        gh.login_as_app(key.encode(), app_id)
        app = gh.authenticated_app()
        inst = gh.app_installation_for_repository(repo_owner, repo_name)
        gh.login_as_app_installation(key.encode(), app.id, inst.id)
    else:
        gh = github3.github.GitHub()
    repo = gh.repository(repo_owner, repo_name)

    if all_issues:
        if args.repo_name == "HERA_Commissioning":
            issues = repo.issues(labels="Daily",)
        else:
            issues = repo.issues(state="open",)
    else:
        if args.repo_name == "HERA_Commissioning":
            issues = repo.issues(
                labels="Daily", since=datetime.now(timezone.utc) - timedelta(days=30)
            )
        else:
            issues = repo.issues(
                state="open", since=datetime.now(timezone.utc) - timedelta(days=30)
            )

    notebook_link = (
        "https://github.com/HERA-Team/H3C_plots" "/blob/master/data_inspect_{}.ipynb"
    )

    rfi_link = (
        "https://github.com/alphatangojuliett/HERA_daily_RFI"
        "/blob/herapost-master/daily_RFI_report_{}.ipynb"
    )

    label_issue_link = (
        "https://github.com/{owner}/{repo}".format(owner=repo_owner, repo=repo_name)
        + '/issues?q=is%3Aissue+is%3Aopen+label%3A"{url}"'
    )

    # replace the github.com with nbviwer.juptyer.org/github for actual
    # viewing link
    notebook_view = notebook_link.replace("github.com", "nbviewer.jupyter.org/github")
    rfi_view = rfi_link.replace("github.com", "nbviewer.jupyter.org/github")
    full_issue_iter = repo.issues(state="all")
    for cnt, issue in enumerate(issues):
        row = {}
        try:
            jd = int(issue.title.split(" ")[-1])
            obs_date = Time(jd, format="jd")
        except ValueError:
            obs_date = Time(2458750 - cnt * 5, format="jd")
            jd = int(np.floor(obs_date.jd))

        jd_list.insert(0, jd)

        obs_date = dateparser.parse(obs_date.iso).astimezone(timezone.utc)
        obs_end = obs_date + timedelta(days=1)

        # count the number of issues opened in this day
        # cound the number of total issues on this day
        num_opened = 0
        num_open_on_day = 0

        for _iss in full_issue_iter:
            if obs_date <= _iss.created_at.astimezone(timezone.utc) <= obs_end:
                num_opened += 1
            if _iss.created_at.astimezone(timezone.utc) <= obs_end:
                if (
                    _iss.closed_at is not None
                    and _iss.closed_at.astimezone(timezone.utc) >= obs_end
                ):
                    num_open_on_day += 1
                elif _iss.closed_at is None:
                    num_open_on_day += 1
                else:
                    pass

        # See if the nightly notebook is up for that day
        request = requests.get(notebook_link.format(jd))
        if request.status_code == 200:
            url = notebook_view.format(jd)
            notebook = "<a href={url}>View</a>".format(url=url)
        else:
            notebook = "N/A"

        request_date = obs_date.isoformat().split("T")[0].replace("-", "")
        # See if the RFI notebook is up for that day
        request = requests.get(rfi_link.format(request_date))
        if request.status_code == 200:
            url = rfi_view.format(request_date)
            rfi_notebook = "<a href={url}>View</a>".format(url=url)
        else:
            rfi_notebook = "N/A"

        link = issue.url.replace("api.", "").replace("repos/", "")
        other_labels = [lab.name for lab in issue.labels() if lab.name != "Daily"]
        other_labels = [
            ('<a target="_blank" href=' + label_issue_link + ">{label}</a>").format(
                url=label.replace(" ", "+"), label=label
            )
            for label in other_labels
        ]
        display_text = '<a target="_blank" href={url}>{number}</a>'.format(
            url=link, number=jd
        )

        iss_urls = re.findall(github_link_regex, issue.body_html)
        related_issues = []
        for url in iss_urls:
            url = url
            num = url.split("/")[-1]
            related_issues.append(
                '<a target="_blank" href={url}>{num}</a>'.format(url=url, num=num)
            )
        related_issues = [
            iss + "<br>" * (iss_cnt % 3 == 2)
            for iss_cnt, iss in enumerate(related_issues)
        ]

        row["text"] = [
            display_text,
            " ".join(related_issues),
            "<br>".join(other_labels),
            notebook,
            rfi_notebook,
            num_opened,
            num_open_on_day,
        ]
        table["rows"].append(row)

    jd_list = np.sort(jd_list)
    full_jd_range = np.arange(jd_today - time_window, jd_today + 1)
    for jd in full_jd_range:
        if jd not in jd_list:
            row = {}
            # See if the nightly notebook is up for that day
            request = requests.get(notebook_link.format(jd))
            if request.status_code == 200:
                url = notebook_view.format(jd)
                notebook = '<a target="_blank" href={url}>View</a>'.format(url=url)
            else:
                notebook = "N/A"

            obs_date = Time(jd, format="jd")
            request_date = obs_date.isot.split("T")[0].replace("-", "")
            # See if the RFI notebook is up for that day
            request = requests.get(rfi_link.format(request_date))
            if request.status_code == 200:
                url = rfi_view.format(request_date)
                rfi_notebook = '<a target="_blank" href={url}>View</a>'.format(url=url)
            else:
                rfi_notebook = "N/A"

            log_url = (
                "https://github.com/HERA-Team/HERA_Commissioning/issues"
                "/new?assignees=&labels=Daily&template=daily-log.md"
                "&title=Observing+report+{}"
            ).format(jd)

            display_text = '<a target="_blank" href={url}>{jd} No Entry</a>'.format(
                url=log_url, jd=jd
            )

            row["text"] = [display_text, "", "", notebook, rfi_notebook, "-", "-"]
            # bisect assumes monotonically increasing
            # but we want descending so we'll flip
            # the index around the length of the list
            index = bisect.bisect_left(jd_list, jd)
            table["rows"].insert(len(jd_list) - index, row)

    all_tables.append(table)
    html_template = env.get_template("tables_with_footer.html")

    rendered_html = html_template.render(
        tables=all_tables,
        gen_date=Time.now().iso,
        gen_time_unix_ms=Time.now().unix * 1000,
        scriptname=os.path.basename(__file__),
        hostname=computer_hostname,
        colsize="12",
    )

    with open("issue_log.html", "w") as h_file:
        h_file.write(rendered_html)

    print("Execution Length: ", (Time.now() - t1).to("min"))
    return


if __name__ == "__main__":
    desc = (
        "Get list of Issues from the inpute github owner/repo "
        "with the supplied credentials."
    )
    parser = argparse.ArgumentParser(
        description=desc, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        dest="pem_file",
        type=str,
        nargs=1,
        help=("The pem file of the secret key for the app."),
    )
    parser.add_argument(
        "app_id_file", type=str, nargs=1, help="A text file with the app_id inside"
    )
    parser.add_argument(
        "--repo",
        dest="repo_name",
        default="HERA_Commissioning",
        help="Name of repository to pull issues",
    )
    parser.add_argument(
        "--owner",
        dest="repo_owner",
        type=str,
        default="HERA-Team",
        help="Github Repository owner/organization.",
    )
    parser.add_argument(
        "--time_window",
        "-t",
        dest="time_window",
        default=30,
        type=int,
        help="The time window in days to query issues from.",
    )
    parser.add_argument(
        "--all",
        dest="all_issues",
        action="store_true",
        help=("Print all Daily issues even if outside of " "the input time window."),
    )
    args = parser.parse_args()

    main(
        pem_file=args.pem_file[0],
        app_id_file=args.app_id_file[0],
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        time_window=args.time_window,
        all_issues=args.all_issues,
    )

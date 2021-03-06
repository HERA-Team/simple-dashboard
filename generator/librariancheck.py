#! /usr/bin/env python

import os
import math
import os.path
import platform
from astropy.time import Time
from hera_librarian import LibrarianClient
from jinja2 import Environment, FileSystemLoader

connection_name = ['aoc-manual', 'local-rtp']

search = '''
{
    "age-less-than": 30
}'''


def main():
    if platform.python_version().startswith('3'):
        hostname = os.uname().nodename
    else:
        hostname = os.uname()[1]

    tables = []

    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], 'templates')
    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)

    clnrao = LibrarianClient(connection_name[0])
    cllocal = LibrarianClient(connection_name[1])
    JD = Time.now().jd
    yesterday = math.floor(JD) - 1
    filesearch = '''
    {"name-matches": "zen.''' + str(yesterday) + '''.%"
    }'''

    # obssearch = '''
    # {"start-time-jd-in-range":''' + str([yesterday,JD]) + '''
    # }'''
    # print(obssearch)
    nraofiles = clnrao.search_files(filesearch)['results']
    localfiles = cllocal.search_files(filesearch)['results']
    # nraoobs = clnrao.search_observations(obssearch)['results']
    # localobs = cllocal.search_observations(obssearch)['results']
    # print(len(nraofiles),len(localfiles))
    # print(len(nraoobs),len(localobs))
    nrao = {"title": "NRAO recent files from {}".format(yesterday), "tab_style": "float:left"}
    filesrownrao = []
    for file in nraofiles:
        rowdict = {"text": [file["name"], str(file["obsid"]), str(file["type"])]}
        filesrownrao.append(rowdict)
    nrao["rows"] = filesrownrao
    nrao["div_style"] = 'style="max-height: 60%; text-align: center; overflow-x: auto; overflow-y: scroll;"'
    nrao["headers"] = ['Name', 'Obsid', 'Type']
    nrao["colsize"] = 6
    tables.append(nrao)

    karoo = {"title": "KAROO recent files from {}".format(yesterday), "tab_style": "float:left"}
    filesrowkaroo = []
    for file in localfiles:
        rowdict = {"text": [file["name"], str(file["obsid"]), str(file["type"])]}
        filesrowkaroo.append(rowdict)
    karoo["rows"] = filesrowkaroo
    karoo["div_style"] = 'style="max-height: 60%; text-align: center; overflow-x: auto; overflow-y: scroll;"'
    karoo["headers"] = ['Name', 'Obsid', 'Type']
    karoo["colsize"] = 6
    tables.append(karoo)

    numbers = {"title": "File statistics from {}".format(yesterday)}
    numrow = []
    numrow.append({"text": [str(len(nraofiles)), str(len(localfiles))]})
    numbers["rows"] = numrow
    numbers["headers"] = ['Nfiles at NRAO', 'Nfiles at Karoo']
    numbers["colsize"] = 12
    tables.insert(0, numbers)
    # print(numrow, filesrownrao[0], filesrowkaroo[0], yesterday)

    template = env.get_template("tables_with_footer.html")
    rendered_html = template.render(
        tables=tables,
        gen_date=Time.now().iso,
        gen_time_unix_ms=Time.now().unix * 1000,
        scriptname=os.path.basename(__file__),
        hostname=hostname,
    )

    with open("librariancheck.html", "w") as h_file:
        h_file.write(rendered_html)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import os
import re
import sys
from contextlib import closing

import jinja2

import odoo
from odoo.addons.web.controllers.main import (DBNAME_PATTERN, Database,
                                              db_monodb)
from odoo.http import request

if hasattr(sys, 'frozen'):
    # When running on compiled windows binary, we don't have access to package loader.
    path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'views'))
    loader = jinja2.FileSystemLoader(path)
else:
    loader = jinja2.PackageLoader('odoo.addons.display_db_creation_datetime', "views")

env = jinja2.Environment(loader=loader, autoescape=True)


def db_filter(dbs):
    httprequest = request.httprequest
    h = httprequest.environ.get('HTTP_HOST', '').split(':')[0]
    d, _, r = h.partition('.')
    if d == "www" and r:
        d = r.partition('.')[0]
    if odoo.tools.config['dbfilter']:
        r = odoo.tools.config['dbfilter'].replace('%h', h).replace('%d', d)
        dbs = [i for i in dbs if re.match(r, i[0])]
    elif odoo.tools.config['db_name']:
        # In case --db-filter is not provided and --database is passed, Odoo will
        # use the value of --database as a comma seperated list of exposed databases.
        exposed_dbs = set(db.strip() for db in odoo.tools.config['db_name'].split(','))
        dbs = sorted(exposed_dbs.intersection(dbs))
    return dbs


def get_db_list(force=False):
    """
        Overwritten of 'list_dbs' method of service.db
    """
    if not odoo.tools.config['list_db'] and not force:
        raise odoo.exceptions.AccessDenied()

    if not odoo.tools.config['dbfilter'] and odoo.tools.config['db_name']:
        res = sorted(db.strip()
                     for db in odoo.tools.config['db_name'].split(','))
        return res

    chosen_template = odoo.tools.config['db_template']
    templates_list = tuple(set(['postgres', chosen_template]))
    db = odoo.sql_db.db_connect('postgres')
    with closing(db.cursor()) as cr:
        try:
            db_user = odoo.tools.config["db_user"]
            if not db_user and os.name == 'posix':
                import pwd
                db_user = pwd.getpwuid(os.getuid())[0]
            if not db_user:
                cr.execute("select usename from pg_user where usesysid=(select datdba from pg_database where datname=%s)",
                           (odoo.tools.config["db_name"],))
                res = cr.fetchone()
                db_user = res and str(res[0])
            if db_user:
                #  query to fetch timestamp of database creation
                cr.execute("select datname,(pg_stat_file('base/'||oid ||'/PG_VERSION')).modification from pg_database where datdba=(select usesysid from pg_user where usename=%s) and not datistemplate and datallowconn and datname not in %s order by datname", (db_user, templates_list))
            else:
                cr.execute(
                    "select datname from pg_database where not datistemplate and datallowconn and datname not in %s order by datname", (templates_list,))
            res = [(odoo.tools.ustr(name), created_on.strftime('%d/%m/%Y %H:%M:%S'))
                   for (name, created_on) in cr.fetchall()]
        except Exception:
            res = []
    res.sort()
    return db_filter(res)


class DatabaseInherit(Database):

    def _render_template(self, **d):
        """
        Render html template with datetime information of databases
        """
        d.setdefault('manage', True)
        d['insecure'] = odoo.tools.config['admin_passwd'] == 'admin'
        d['list_db'] = odoo.tools.config['list_db']
        d['langs'] = odoo.service.db.exp_list_lang()
        d['countries'] = odoo.service.db.exp_list_countries()
        d['pattern'] = DBNAME_PATTERN
        d['databases'] = []
        try:
            d['databases'] = get_db_list(False)
        except odoo.exceptions.AccessDenied:
            monodb = db_monodb()
            if monodb:
                d['databases'] = [monodb]
        return env.get_template("db_manager.html").render(d)

import os
from jinja2 import Environment, FileSystemLoader

from charmhelpers.core.host import (
    service_running,
    service_start,
    service_restart
)


SNAP_COMMON = os.path.join('/', 'var', 'snap', 'django-gunicorn-nginx', 'common')

DJANGO_SETTINGS_DIR = os.path.join(SNAP_COMMON, 'django_secrets')


def start_restart(service):
    if service_running(service):
        service_restart(service)
    else:
        service_start(service)


def render_settings_py(settings_filename, secrets=None):
    """Render Django Settings
    """
    if secrets:
        secrets = secrets
    else:
        secrets = {}

    settings_file = \
        os.path.join(DJANGO_SECRETS_DIR, settings_filename)

    # Render config source and target
    if os.path.exists(settings_file):
        os.remove(settings_file)

    app_yml = load_template("{}.tmpl".format(settings_filename))
    app_yml = app_yml.render(secrets=secrets)

    # Spew configs into source
    spew(settings_file, app_yml)


def load_template(name, path=None):
    """ load template file
    :param str name: name of template file
    :param str path: alternate location of template location
    """
    if path is None:
        path = os.path.join(charm_dir(), 'templates')
    env = Environment(
        loader=FileSystemLoader(path))
    return env.get_template(name)


def spew(path, data):
    """ Writes data to path
    :param str path: path of file to write to
    :param str data: contents to write
    """
    with open(path, 'w') as f:
        f.write(data)

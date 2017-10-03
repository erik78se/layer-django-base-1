import os
import shutil
from subprocess import call

from jinja2 import Environment, FileSystemLoader

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import config, charm_dir, status_set
from charmhelpers.core.host import (
    chownr,
    chdir,
    service_running,
    service_start,
    service_restart
)

from charms.layer import options


VENV_PIP = os.path.join('/', 'var', 'www', 'env', 'bin', 'pip')
VENV_PYTHON = os.path.join('/', 'var', 'www', 'env', 'bin', 'python')
APP_DIR = options('git-deploy').get('target')
APP_CURRENT = os.path.join(APP_DIR, 'current')
SU_CONF_DIR = "/var/www/config"
STATIC_ROOT = os.path.join('/', 'var', 'www', 'static')
LOG_DIR = os.path.join('/', 'var', 'log', 'django')


kv = unitdata.kv()


class UtilsException(Exception):
    pass


def start_restart(service):
    if service_running(service):
        service_restart(service)
    else:
        service_start(service)


def pip_install(pkg):
    status_set('maintenance', "{} install {}".format(VENV_PIP, pkg))
    with chdir(APP_CURRENT):
        call("{} install {}".format(VENV_PIP, pkg).split())
    status_set('active', "{} installed successfully".format(pkg))


def render_settings_py(settings_filename, secrets=None):
    """Render settings file
    """
    if not secrets:
        secrets = {}

    # Set paths
    config_source = \
        os.path.join(SU_CONF_DIR, settings_filename)
    config_target = \
        os.path.join(APP_CURRENT, config('django-project-name'),
                     settings_filename)

    # Render config source and target
    if os.path.exists(config_target):
        os.remove(config_target)

    if os.path.exists(config_source):
        os.remove(config_source)

    app_yml = load_template("{}.tmpl".format(settings_filename))
    app_yml = app_yml.render(secrets=secrets)

    # Spew configs into source
    spew(config_source, app_yml)

    # Create symlink from su config dir to app config dir
    os.symlink(config_source, config_target)

    # Set perms
    chownr(path=os.path.dirname(os.path.normpath(APP_DIR)),
           owner='www-data', group='www-data')


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


def spew(path, data, owner=None):
    """ Writes data to path
    :param str path: path of file to write to
    :param str data: contents to write
    :param str owner: optional owner of file
    """
    with open(path, 'w') as f:
        f.write(data)
    if owner:
        try:
            chown(path, owner)
        except:
            raise UtilsException("Unable to set ownership of {}".format(path))


def chown(path, user, group=None, recursive=False):
    """
    Change user/group ownership of file
    :param path: path of file or directory
    :param str user: new owner username
    :param str group: new owner group name
    :param bool recursive: set files/dirs recursively
    """
    try:
        if not recursive or os.path.isfile(path):
            shutil.chown(path, user, group)
        else:
            for root, dirs, files in os.walk(path):
                shutil.chown(root, user, group)
                for item in dirs:
                    shutil.chown(os.path.join(root, item), user, group)
                for item in files:
                    shutil.chown(os.path.join(root, item), user, group)
    except OSError as e:
        raise UtilsException(e)

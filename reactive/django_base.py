import os
from subprocess import call
from multiprocessing import cpu_count

from charmhelpers.core import unitdata
from charmhelpers.core.host import chownr, chdir
from charmhelpers.core.hookenv import (
    config,
    local_unit,
    status_set,
)

from charmhelpers.core.templating import render

from charms.reactive import (
    when,
    when_any,
    when_not,
    set_state,
    remove_state
)

from charms.layer.django_base import (
    VENV_PIP,
    APP_CURRENT,
    SU_CONF_DIR,
    LOG_DIR,
    render_settings_py,
)


kv = unitdata.kv()


@when_not('s3.storage.checked')
def check_for_django_aws_s3_storage_config():
    if not config('aws-access-key') and \
       not config('aws-secret-key') and \
       not config('aws-s3-bucket-name'):
        remove_state('s3.storage.available')
        set_state('local.storage.settings.avilable')
    else:
        kv.set('aws_access_key', config('aws-access-key'))
        kv.set('aws_secret_key', config('aws-secret-key'))
        kv.set('aws_s3_bucket_name', config('aws-s3-bucket-name'))
        remove_state('s3.storage.settings.available')
        set_state('s3.storage.avilable')
    set_state('s3.storage.checked')


@when_not('conf.dirs.available')
def create_conf_dir():
    """Ensure config dir exists
    """
    for directory in [SU_CONF_DIR, LOG_DIR]:
        if not os.path.isdir(directory):
            os.makedirs(directory, mode=0o755, exist_ok=True)
        chownr(directory, owner='www-data', group='www-data')
    set_state('conf.dirs.available')


@when('codebase.available')
@when_not('django.settings.available')
def render_django_settings():
    """Write out settings.py
    """
    status_set('maintenance', "Rendering Django settings")
    secrets = {'project_name': config('django-project-name')}
    if config('installed-apps'):
        secrets['installed_apps'] = config('installed-apps').split(',')
    render_settings_py(secrets=secrets)
    status_set('active', "Django settings rendered")
    set_state('django.settings.available')


@when('codebase.available')
@when_not('pip.deps.available')
def install_venv_and_pip_deps():
    status_set('maintenance', "Installing application deps")

    create_venv_cmd = "python3 -m venv /var/www/env"
    call(create_venv_cmd.split())

    with chdir(APP_CURRENT):
        pip_deps_install = "{} install -r requirements.txt".format(VENV_PIP)
        call(pip_deps_install.split())

    status_set('active', "Application pip deps installed")
    set_state('pip.deps.available')


@when('codebase.available')
@when_not('django.email.settings.available')
def render_email_config():
    status_set('maintenance', "Configuring email")

    email_config = {}
    if config('email-config'):
        for secret in config('email-config').strip().split(","):
            s = secret.split("=")
            email_config[s[0]] = s[1]

        render_settings_py(settings_filename="email.py",
                           secrets=email_config)
        status_set('active', "Django email settings available")
    else:
        status_set('active', "No SMTP configured")

    set_state('django.email.settings.available')


@when('codebase.available',
      's3.storage.avilable')
@when_not('s3.storage.settings.available')
def render_s3_storage_config():
    status_set('maintenance', "Configuring S3 storage")

    storage_config = {'aws_access_key': kv.get('aws_access_key'),
                      'aws_secret_key': kv.get('aws_secret_key'),
                      'aws_s3_bucket_name': kv.get('aws_s3_bucket_name')}

    render_settings_py(settings_filename="storage.py",
                       secrets=storage_config)

    status_set('active', "S3 storage available")
    set_state('s3.storage.settings.available')


@when('redis.available')
@when_not('django.redis.available')
def get_set_redis_uri(redis):
    """Get set redis connection details
    """
    status_set('maintenance', 'Acquiring Redis URI')
    kv.set('redis_uri', redis.redis_data()['uri'])
    status_set('active', 'Redis URI acquired')
    set_state('django.redis.available')


@when('codebase.available')
@when_not('django.celery.settings.available')
def write_celery_django_settings():
    """Write out celery django settings
    """

    status_set('maintenance', 'Writing celery settings')

    celery_config = {}
    if config('celery-config'):
        for secret in config('celery-config').strip().split(","):
            s = secret.split("=")
            celery_config[s[0]] = s[1]
        render_settings_py(
            settings_filename="celery_config.py", secrets=celery_config)

    status_set('active', 'Celery settings available')
    set_state('django.celery.settings.available')


@when('codebase.available')
@when_not('django.custom.settings.available')
def write_custom_django_settings():
    """Write out custom django settings
    """

    status_set('maintenance', 'Writing custom settings')

    custom_config = {'APPLICATION_COMPONENT': "'{}'".format(local_unit().replace("/", "-"))}
    if config('custom-config'):
        for secret in config('custom-config').strip().split(","):
            s = secret.split("=")
            custom_config[s[0]] = s[1]
        render_settings_py(
            settings_filename="custom.py", secrets=custom_config)

    status_set('active', 'Custom settings available')
    set_state('django.custom.settings.available')


@when('django.redis.available', 'codebase.available')
@when_not('django.redis.settings.available')
def render_redis_settings():
    status_set('maintenance', 'Rendering Redis settings')
    render_settings_py(settings_filename="redis.py",
                       secrets={'redis_uri': kv.get('redis_uri')})
    status_set('active', 'Redis config available')
    set_state('django.redis.settings.available')


@when_not('gunicorn.systemd.service.available')
def render_gunicorn_systemd():
    """Render the systemd conf for the django application
    """
    status_set('maintenance', "Preparing systemd")
    systemd_service_conf = "/etc/systemd/system/django-gunicorn.service"
    render('django-gunicorn.service.tmpl', systemd_service_conf,
           context={'cpus': cpu_count() + 1,
                    'project_name': config('django-project-name')})
    status_set('active', "Gunicorn systemd service vailable.")
    set_state('gunicorn.systemd.service.available')


@when('gunicorn.systemd.service.available', 'conf.dirs.available',
      'django.custom.settings.available', 'django.redis.settings.available',
      'django.email.settings.available', 'django.celery.settings.available')
#@when_any('s3.storage.settings.available',
#          'local.storage.settings.available')
@when_not('django.base.available')
def set_django_base_avail():
    call("chmod -R 755 /var/www".split())
    call("chmod -R 755 {}".format(LOG_DIR).split())
    call("chown -R www-data:www-data /var/www".split())
    call("chown -R www-data:www-data {}".format(LOG_DIR).split())
    set_state('django.base.available')


@when('config.changed.celery-config', 'django.base.available')
def render_django_email_config():
    remove_state('django.celery.settings.available')


#@when('config.changed.custom-config', 'django.base.available')
#def re_render_custom_config():
#    remove_state('django.custom.settings.available')

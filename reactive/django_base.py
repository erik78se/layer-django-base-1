import os
from subprocess import call
from multiprocessing import cpu_count

from charms.reactive.flags import (
    register_trigger,
    clear_flag,
    set_flag,
)

from charms.reactive.decorators import (
    when,
    when_any,
    when_not
)

from charmhelpers.core import unitdata
from charmhelpers.core.host import chownr
from charmhelpers.core.hookenv import (
    config,
    local_unit,
    status_set,
)

from charmhelpers.core.templating import render

from charms.layer.django_base import (
    SU_CONF_DIR,
    LOG_DIR,
    render_settings_py,
    pip_install,
)


kv = unitdata.kv()

register_trigger(when='config.changed.celery.config',
                 clear_flag='django.celery.settings.available')

register_trigger(when='config.changed.custom-config',
                 clear_flag='django.custom.settings.available')

register_trigger(when='config.changed.email-config',
                 clear_flag='django.email.settings.available')

register_trigger(when='redis.broken',
                 clear_flag='django.redis.available')


@when_not('s3.storage.checked')
def check_for_django_aws_s3_storage_config():
    status_set('maintenance', 'Checking S3 storage configs')
    if not config('aws-access-key') and \
       not config('aws-secret-key') and \
       not config('aws-s3-bucket-name'):
        clear_flag('s3.storage.available')
        set_flag('local.storage.settings.available')
        status_set('active', 'Django local storage available')
    else:
        kv.set('aws_access_key', config('aws-access-key'))
        kv.set('aws_secret_key', config('aws-secret-key'))
        kv.set('aws_s3_bucket_name', config('aws-s3-bucket-name'))
        clear_flag('s3.storage.settings.available')
        set_flag('s3.storage.avilable')
        status_set('active', 'Django S3 storage available')
    set_flag('s3.storage.checked')


@when_not('conf.dirs.available')
def create_conf_dir():
    """Ensure config dir exists
    """
    status_set('maintenance', "Creating application directories")
    for directory in [SU_CONF_DIR, LOG_DIR]:
        if not os.path.isdir(directory):
            os.makedirs(directory, mode=0o755, exist_ok=True)
        chownr(directory, owner='www-data', group='www-data')
    status_set('active', "Application directories created")
    set_flag('conf.dirs.available')


@when('codebase.available')
@when_not('django.settings.available')
def render_django_settings():
    """Write out settings.py
    """
    status_set('maintenance', "Rendering Django settings")
    secrets = {'project_name': config('django-project-name')}
    if config('installed-apps'):
        secrets['installed_apps'] = config('installed-apps').split(',')
    render_settings_py(settings_filename="settings.py", secrets=secrets)
    status_set('active', "Django settings rendered")
    set_flag('django.settings.available')


@when('codebase.available')
@when_not('django.wsgi.available')
def render_wsgi_py():
    """Write out settings.py
    """
    status_set('maintenance', "Rendering wsgi.py")
    secrets = {'project_name': config('django-project-name')}
    render_settings_py(settings_filename="wsgi.py", secrets=secrets)
    status_set('active', "Django wsgi.py rendered")
    set_flag('django.wsgi.available')


@when('codebase.available')
@when_not('pip.deps.available')
def install_venv_and_pip_deps():
    status_set('maintenance', "Installing application deps")

    create_venv_cmd = "python3 -m venv /var/www/env"
    call(create_venv_cmd.split())

    pip_install("-r requirements.txt")
    pip_install("gunicorn psycopg2 python-memcached")

    status_set('active', "Application pip deps installed")
    set_flag('pip.deps.available')


@when('codebase.available')
@when_not('django.email.settings.available')
def render_email_config():
    status_set('maintenance', "Configuring email")

    email_config = {}
    if config('email-config'):
        for secret in config('email-config').strip().split(","):
            s = secret.split("=")
            email_config[s[0]] = s[1]

        render_settings_py(settings_filename="email.py", secrets=email_config)
        status_set('active', "Django email settings available")
    else:
        status_set('active', "No SMTP configured")

    set_flag('django.email.settings.available')


@when('codebase.available',
      's3.storage.avilable')
@when_not('s3.storage.settings.available')
def render_s3_storage_config():
    status_set('maintenance', "Configuring S3 storage")

    render_settings_py(
        settings_filename="storage.py", secrets=kv.getrange('aws'))

    status_set('active', "S3 storage available")
    set_flag('s3.storage.settings.available')


@when('redis.available')
@when_not('django.redis.available')
def get_set_redis_uri(redis):
    """Get set redis connection details
    """
    status_set('maintenance', 'Acquiring Redis URI')
    redis_data = redis.redis_data()
    kv.set('redis_uri', redis_data['uri'])
    kv.set('redis_host', redis_data['host'])
    kv.set('redis_port', redis_data['port'])
    kv.set('redis_password', redis_data['password'])
    status_set('active', 'Redis URI acquired')
    clear_flag('django.redis.settings.available')
    set_flag('django.redis.available')


@when('codebase.available')
@when_not('django.cron.settings.available')
def write_cron_django_settings():
    """Write out cron django settings
    """

    status_set('maintenance', 'Writing cron settings')

    celery_config = {}
    if config('cron-config'):
        for secret in config('cron-config').strip().split("#"):
            s = secret.split("=")
            celery_config[s[0]] = s[1]
        render_settings_py(
            settings_filename="cron_config.py", secrets=celery_config)

    status_set('active', 'Cron settings available')
    set_flag('django.cron.settings.available')


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
    set_flag('django.celery.settings.available')


@when('codebase.available')
@when_not('django.custom.settings.available')
def write_custom_django_settings():
    """Write out custom django settings
    """

    status_set('maintenance', 'Writing custom settings')

    custom_config = \
        {'APPLICATION_COMPONENT': "'{}'".format(
            local_unit().replace("/", "-"))}
    if config('custom-config'):
        for secret in config('custom-config').strip().split("#"):
            s = secret.split("=")
            custom_config[s[0]] = s[1]
        render_settings_py(
            settings_filename="custom.py", secrets=custom_config)

    status_set('active', 'Custom settings available')
    set_flag('django.custom.settings.available')


@when('django.redis.available', 'codebase.available')
@when_not('django.redis.settings.available')
def render_redis_settings():
    status_set('maintenance', 'Rendering Redis settings')
    render_settings_py(
        settings_filename="redis.py", secrets=kv.getrange("redis"))
    status_set('active', 'Redis config available')
    set_flag('django.redis.settings.available')


@when('memcache.client.available')
@when_not('django.memcache.settings.available')
def render_memcache_config():
    status_set('maintenance', 'Rendering Memcache settings')
    render_settings_py(settings_filename="memcache_config.py")
    status_set('active', 'Memcache config available')
    set_flag('django.memcache.settings.available')


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
    set_flag('gunicorn.systemd.service.available')


@when('gunicorn.systemd.service.available',
      'pip.deps.available',
      'conf.dirs.available',
      'django.settings.available',
      'django.wsgi.available',
      'django.custom.settings.available',
      'django.email.settings.available',
      'django.celery.settings.available')
@when_any('s3.storage.settings.available',
          'local.storage.settings.available')
@when_not('django.base.available')
def set_django_base_avail():
    call("chmod -R 755 /var/www".split())
    call("chmod -R 755 {}".format(LOG_DIR).split())
    call("chown -R www-data:www-data /var/www".split())
    call("chown -R www-data:www-data {}".format(LOG_DIR).split())
    set_flag('django.base.available')

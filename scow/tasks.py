
#from collections import namedtuple

from os import path
from textwrap import dedent

import fabric
from fabric.api import cd, env, run, sudo, prefix, put
from fabric.context_managers import hide
#from fabric.tasks import Task
#import fabtools
from fabtools import (
    deb,
    files,
    require,
    user,
)
from project_settings import PYTHON_VERSION
from . import (
    scow_task,
    CONFIG_DIR,
    DEBIAN_PACKAGES as CORE_DEBIAN_PACKAGES,
    PYTHON_SYSTEM_PACKAGES,
    PYTHON_SRC_DIR,
    PYTHON_SOURCE_URL,
    EZ_SETUP_URL,
    DB_ENGINE_POSTGRES,
    #PROJECT_SHARED_SECRET,
    #PROJECT_SHARED_SECRET_PUB,
)
from .exceptions import (
    UserDoesNotExistError,
    UserExistsError,
)
from .utils import (
    remote_local_file,
    #append_admin_profiles,
)


@scow_task
def share_secrets():
    pass
    #for secret_path in (
    #        env.project.PROJECT_SHARED_SECRET,
    #        env.project.PROJECT_SHARED_SECRET_PUB):
    #    secret_dir, secret_file = path.split(secret_path)
    #    put(secret_path, path.join(env.scow.dirs.ETC_DIR, secret_file))

    #require.files.template_file(
    #    os.path.join(env.scow.pro)
    #)
    #fabric.contrib.
    #require.files.template_file()


@scow_task
def create_admin(username):
    if user.exists(username):
        raise UserExistsError("User already exists: " + username)
    for admin in env.project.ADMINS:
        if admin['username'] == username:
            break
    else:
        raise AttributeError("No dict with username {} in env.project.ADMINS (which should "
                             "be a list of dictionaries of admin profiles)".format(username))
    # TODO: Process more kwargs accepted by fabtools.require.user
    user_options = ('ssh_public_keys', 'shell',)
    user_kwargs = {kwarg: admin[kwarg] for kwarg in user_options if kwarg in admin}
    if 'skeleton_dir' in admin:
        with remote_local_file(admin['skeleton_dir']) as skel_dir:
            user_kwargs['skeleton_dir'] = skel_dir
            require.users.user(username, **user_kwargs)
    else:
        require.users.user(username, **user_kwargs)
    require.users.sudoer(username)


@scow_task
def create_missing_admins():
    for admin in env.project.ADMINS:
        if 'username' in admin and not user.exists(admin['username']):
            create_admin(admin['username'])


@scow_task
def delete_admin(username):
    if not user.exists(username):
        raise UserDoesNotExistError("User does not exist: " + username)
    user_home = user.home_directory(username)
    sudo('deluser ' + username)
    sudo('rm -Rf ' + user_home)


@scow_task
def recreate_admin(username):
    try:
        delete_admin(username)
    except UserDoesNotExistError:
        pass
    create_admin(username)


@scow_task
def update_deb_packages():
    deb.update_index()


@scow_task
def upgrade_deb_packages():
    update_deb_packages()
    deb.upgrade()


@scow_task
def install_deb_packages():
    pkgs = set(CORE_DEBIAN_PACKAGES)
    for admin_profile in env.project.ADMINS:
        if 'requires_deb_packages' in 'admin_profile':
            pkgs = pkgs | set(admin_profile['requires_deb_packages'])
    require.deb.packages(pkgs)


@scow_task
def setup_local_python_tools(*args, **kwargs):
    # Install easy_install and pip
    run('wget {} -O - | /usr/local/bin/python'.format(EZ_SETUP_URL))
    run('/usr/local/bin/easy_install pip')
    env.scow.registry.LOCAL_PYTHON_INSTALLED = True
    run('/usr/local/bin/pip install ' + ' '.join(PYTHON_SYSTEM_PACKAGES))
    venvwrapper_env_script = path.join(CONFIG_DIR, 'venvwrapper-settings.sh')
    require.files.file(
        venvwrapper_env_script,
        contents=dedent("""
            # Virtualenv wrapper settings used by django-scow
            export WORKON_HOME=/var/env
            export PROJECT_HOME=/opt
            """))

    abric.contrib.files.append(
        '/etc/profile',
        dedent("""
        # Virtualenvwrapper shim [is this a shim?? what is a shim?] installed by scow
        . {}
        . /usr/local/bin/virtualenvwrapper.sh
        """.format(venvwrapper_env_script)),
    )


@scow_task
def setup_local_python(*args, **kwargs):
    # Stop now if we've installed python and there's no `force` in kwargs
    if env.scow.registry.LOCAL_PYTHON_INSTALLED and (
            'force' not in kwargs or not kwargs['force']):
        return

    python_src_dir = PYTHON_SRC_DIR.format(version=PYTHON_VERSION)
    require.directory('$HOME/build-python')
    with cd('$HOME/build-python'):
        run('rm -Rf ./*')
        run('wget ' + PYTHON_SOURCE_URL.format(version=PYTHON_VERSION))
        run('tar -zxf ' + python_src_dir + '.tgz')
    with cd('$HOME/build-python/' + python_src_dir):
        run('./configure')
        run('make')
        run('make install')

    setup_local_python_tools()


@scow_task
def setup_postgres(name, user, password):
    require.postgres.server()
    require.postgres.user(user, password)
    require.postgres.database(name, user)


@scow_task
def setup_django_database(db):
    if db['ENGINE'] == DB_ENGINE_POSTGRES:
        setup_postgres(db['NAME'] + env.scow.project_tag, db['USER'], db['PASSWORD'])
    else:
        raise NotImplementedError("Unknown database engine: " + db['ENGINE'])


@scow_task
def setup_django_databases():
    for db in env.project.DATABASES.values():
        setup_django_database(db)


@scow_task
def setup_nginx(*args, **kwargs):
    require.nginx.server()

    #server_name = env.project.ROOT_FQDN
    #if 'server_suffix' in kwargs:
    #    server_name += '.' + kwargs['server_suffix']

    ##proxy_url = 'http://unix:/path/to/backend.socket:/uri/'

    #require.nginx.proxied_site(
    #    server_name=server_name,
    #    port=80,
    #    proxy_url=proxy_url,
    #)


#@scow_task
#def setup_uwsgi_emperor():


@scow_task
def setup_project_virtualenv(force=False, *args, **kwargs):
    run('deactivate', warn_only=True, quiet=True)
    run('rmvirtualenv ' + env.scow.project_tagged, warn_only=True, quiet=True)
    run('mkvirtualenv ' + env.scow.project_tagged)


@scow_task
def workon_venv_test(*args, **kwargs):
    with prefix('workon ' + env.scow.project_tagged):
        print run('pwd')
        print run('env | grep VIR')


@scow_task
def install_project_requirements(*args, **kwargs):
    with prefix('workon ' + env.scow.project_tagged):
        with hide('stdout'):
            # TODO: Wheel your requirements in
            run('pip install -r etc/requirements.txt')
        for lib_name, lib_url in env.project.PROJECT_LIBS.items():
            dest_path = path.join('lib', lib_name)
            if 'force' in kwargs and kwargs['force']:
                run('rm -Rf ' + dest_path, warn_only=True, quiet=True)
            with hide('stdout'):
                run('git clone {} {}'.format(lib_url, dest_path))
            if files.is_file(path.join(dest_path, 'setup.py')):
                with hide('stdout'):
                    run('pip install ' + dest_path)
            else:
                run('add2virtualenv ' + dest_path)


@scow_task
def project_post_install(*args, **kwargs):
    with prefix('workon ' + env.scow.project_tagged):
        if hasattr(env.project, 'POST_INSTALL'):
            for line in env.project.POST_INSTALL.splitlines():
                line.strip() and run(line.strip())


@scow_task
def install_project_src(*args, **kwargs):
    # TODO: from env.scow.DIRS import would be nice
    with prefix('workon ' + env.scow.project_tagged):
        prj_dir = env.scow.project_dir
        if kwargs.get('force', False):
            #run('rm -Rf ' + env.scow.PROJECT_SRC_DIR)
            run('rm -Rf ' + prj_dir)
        with hide('stdout'):
            run('git clone {} {}'.format(env.project.PROJECT_GIT_URL, prj_dir))
        with cd(prj_dir):
            run('setvirtualenvproject')
            run('add2virtualenv etc')
            run('add2virtualenv src')
    project_post_install(*args, **kwargs)
        # Install postactivate hook
    install_project_requirements(*args, **kwargs)


@scow_task
def set_project_settings_class(settings_class, *args, **kwargs):
    # TODO: Abstract something
    require.files.file(
        path.join(env.scow.dirs.VAR_DIR, 'env', 'DJANGO_SETTINGS_CLASS'),
        contents=settings_class)



@scow_task
def init_droplet(*args, **kwargs):
    create_missing_admins()
    upgrade_deb_packages()
    install_deb_packages()
    setup_local_python()
    setup_django_databases()
    setup_nginx()
    #setup_uwsgi_emperor()


@scow_task
def install_project(settings_class, *args, **kwargs):
    setup_project_virtualenv(*args, **kwargs)
    install_project_src(*args, **kwargs)
    set_project_settings_class(settings_class)

''' Fabric's fabfile for use on the devhost. Invoke this with::

    fab --list
'''

import os
import os.path

from fabric.api import env
from fabric.api import local
from fabric.api import put
from fabric.api import run
from fabric.api import sudo
from fabric.api import task
from fabric.context_managers import cd
from fabric.contrib.files import exists
from fabtools.vagrant import vagrant
from fabtools.vagrant import vagrant_settings


DEPLOY_ROOT = '/srv/councilroom'
DEPLOY_USER = 'cr_prod'
DEPLOY_GROUP = 'cr_prod'

BASE_PIP_ARGS = '--download-cache /srv/councilroom_src/pip-cache'
REQUIREMENTS = '-r requirements/common.txt -r requirements/web.txt -r requirements/background.txt'

@task
def clean():
    ''' Clean the local directory of unnecessary files
    '''
    local("find . -type f -name '*~' -print0 |xargs -0 rm -f")
    local("find . -type f -name '*.pyc' -print0 |xargs -0 rm -f")


@task
def build(buildwheelhouse=False):
    ''' Build the app within the Vagrant host

    The strategy being followed here is to use Ansible (as invoked by
    `vagrant up` or `vagrant provision`) to manage OS-level
    packages.

    Once Ansible has set up the environment, this Fabfile is
    responsible for turning the contents of the current working
    directory (typically a check out of the source code repository)
    into a "built" version of the application within the Vagrant
    host. "Building", in this case, means installing all the
    appropriate versions of the Python dependencies in a standalone
    VirtualEnv, downloading and installing JavaScript libraries that
    CouncilRoom depends upon, compiling any CoffeeScript/Less/Sass or
    related assets, minifying images and other static files, etc.

    That working version can be used for development and testing
    purposes. Ultimately, it will be converted into a Deb package for
    deployment into the production environment.
    '''
    # Create the pip-cache and wheelhouse directories they are missing
    # so so we can reduce repeated downloads and builds
    if not os.path.exists('pip-cache'):
        os.mkdir('pip-cache', 0755)
    if not os.path.exists('wheelhouse'):
        os.mkdir('wheelhouse', 0755)
        buildwheelhouse = True  # Force build

    # Do the following on the vagrant host itself
    with vagrant_settings():
        # Create the deployment directory if necessary
        if not exists(DEPLOY_ROOT):
            sudo("mkdir {0}".format(DEPLOY_ROOT))

        # Create the virtualenv in which the Council Room application
        # and its Python dependencies will be installed and run
        with cd(DEPLOY_ROOT):
            sudo("rm -rf cr-venv")
            sudo("virtualenv cr-venv")

            # Upgrade the pip, setuptools, and wheel in the virtualenv
            sudo("cr-venv/bin/pip install {pipargs} --upgrade pip setuptools".format(pipargs=BASE_PIP_ARGS))
            sudo("cr-venv/bin/pip install {pipargs} wheel".format(pipargs=BASE_PIP_ARGS))

            put(local_path='requirements', remote_path='.', use_sudo=True)

            if (buildwheelhouse):
                # Update the packages in the wheelhouse, if necessary

                # TODO: Figure out how to do this upon a change within
                # the requirements file without rebuilding the world
                # every time

                # Build and install the build-time dependencies
                sudo("cr-venv/bin/pip wheel {pipargs} --wheel-dir=/srv/councilroom_src/wheelhouse  {reqs}".format(pipargs=BASE_PIP_ARGS, reqs='-r requirements/build-deps.txt'))
                sudo("cr-venv/bin/pip install {pipargs} --no-index --use-wheel --find-links=/srv/councilroom_src/wheelhouse {reqs}".format(pipargs=BASE_PIP_ARGS, reqs='-r requirements/build-deps.txt'))

                # Build the remaining dependencies
                sudo("cr-venv/bin/pip wheel {pipargs} --wheel-dir=/srv/councilroom_src/wheelhouse  {reqs}".format(pipargs=BASE_PIP_ARGS, reqs=REQUIREMENTS))

            # Install the items in our requirements files using only the wheelhouse
            sudo("cr-venv/bin/pip install {pipargs} --no-index --use-wheel --find-links=/srv/councilroom_src/wheelhouse {reqs}".format(pipargs=BASE_PIP_ARGS, reqs=REQUIREMENTS))

            # Clear the requirements files from the deployment directory
            sudo("rm -rf requirements")

            # Copy the whole application directory
            # FIXME: This directory needs to be split up as a proper
            # module with a setup script and pieces in a better
            # organization, but that is a task for another day.

            if not exists('app'):
                sudo("mkdir app")
            sudo("rm -rf app/*")
            put(local_path='sitesrc/*', remote_path='app', use_sudo=True)

            with cd('app'):
                # Get rid of some things that don't need to be there
                sudo("rm -rf test*")

                sudo("mkdir static/output")
                sudo("mkdir static/leaderboard")
                # Fix up some permissions
                sudo("chmod +x *.sh analyze2.py analyze.py count_buys.py game_stats.py goals.py goal_stats.py indexes.py load_leaderboard.py optimal_card_ratios.py run_trueskill.py scrape_leaderboard.py update.py")
                # TODO: What are the right permissions here? 
                sudo("chmod a+rwx static/output")
                sudo("chmod a+rwx static/leaderboard")

        # Create the static directory from which Nginx will serve
        # necessary files

        # Copy our images, CSS, JavaScript, etc. into the serving
        # directory

        # Download and install Bootstrap and other external JavaScript
        # packages

        # Set the permissions appropriately
        #sudo("chown {1}:{2} {0}".format(DEPLOY_ROOT, DEPLOY_USER, DEPLOY_GROUP))
        #sudo("chmod ug=rwx,o=rx {0}".format(DEPLOY_ROOT))


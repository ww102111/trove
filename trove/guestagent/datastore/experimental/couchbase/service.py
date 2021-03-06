# Copyright (c) 2013 eBay Software Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import os
import stat
import subprocess
import tempfile

from oslo_utils import netutils
import pexpect

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import utils as utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.couchbase import system
from trove.guestagent.datastore import service
from trove.guestagent.db import models
from trove.guestagent import pkg
from trove.openstack.common import log as logging


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
packager = pkg.Package()


class CouchbaseApp(object):
    """
    Handles installation and configuration of couchbase
    on a trove instance.
    """
    def __init__(self, status, state_change_wait_time=None):
        """
        Sets default status and state_change_wait_time
        """
        if state_change_wait_time:
            self.state_change_wait_time = state_change_wait_time
        else:
            self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """
        Install couchbase if needed, do nothing if it is already installed.
        """
        LOG.info(_('Preparing Guest as Couchbase Server.'))
        if not packager.pkg_is_installed(packages):
            LOG.debug('Installing Couchbase.')
            self._install_couchbase(packages)

    def initial_setup(self):
        self.ip_address = netutils.get_my_ipv4()
        mount_point = CONF.couchbase.mount_point
        try:
            LOG.info(_('Couchbase Server change data dir path.'))
            operating_system.chown(mount_point, 'couchbase', 'couchbase',
                                   as_root=True)
            pwd = CouchbaseRootAccess.get_password()
            utils.execute_with_timeout(
                (system.cmd_node_init
                 % {'data_path': mount_point,
                    'IP': self.ip_address,
                    'PWD': pwd}), shell=True)
            operating_system.remove(system.INSTANCE_DATA_DIR, force=True,
                                    as_root=True)
            LOG.debug('Couchbase Server initialize cluster.')
            utils.execute_with_timeout(
                (system.cmd_cluster_init
                 % {'IP': self.ip_address, 'PWD': pwd}),
                shell=True)
            utils.execute_with_timeout(system.cmd_set_swappiness, shell=True)
            utils.execute_with_timeout(system.cmd_update_sysctl_conf,
                                       shell=True)
            LOG.info(_('Couchbase Server initial setup finished.'))
        except exception.ProcessExecutionError:
            LOG.exception(_('Error performing initial Couchbase setup.'))
            raise RuntimeError("Couchbase Server initial setup failed")

    def complete_install_or_restart(self):
        """
        finalize status updates for install or restart.
        """
        self.status.end_install_or_restart()

    def _install_couchbase(self, packages):
        """
        Install the Couchbase Server.
        """
        LOG.debug('Installing Couchbase Server. Creating %s' %
                  system.COUCHBASE_CONF_DIR)
        operating_system.create_directory(system.COUCHBASE_CONF_DIR,
                                          as_root=True)
        pkg_opts = {}
        packager.pkg_install(packages, pkg_opts, system.TIME_OUT)
        self.start_db()
        LOG.debug('Finished installing Couchbase Server.')

    def _enable_db_on_boot(self):
        """
        Enables Couchbase Server on boot.
        """
        LOG.info(_('Enabling Couchbase Server on boot.'))
        try:
            couchbase_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(
                couchbase_service['cmd_enable'], shell=True)
        except KeyError:
            raise RuntimeError(_(
                "Command to enable Couchbase Server on boot not found."))

    def _disable_db_on_boot(self):
        LOG.debug("Disabling Couchbase Server on boot.")
        try:
            couchbase_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(
                couchbase_service['cmd_disable'], shell=True)
        except KeyError:
            raise RuntimeError(
                "Command to disable Couchbase Server on boot not found.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        """
        Stops Couchbase Server on the trove instance.
        """
        LOG.debug('Stopping Couchbase Server.')
        if do_not_start_on_reboot:
            self._disable_db_on_boot()

        try:
            couchbase_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(
                couchbase_service['cmd_stop'], shell=True)
        except KeyError:
            raise RuntimeError("Command to stop Couchbase Server not found.")

        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_('Could not stop Couchbase Server.'))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not stop Couchbase Server."))

    def restart(self):
        LOG.info(_("Restarting Couchbase Server."))
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def start_db(self, update_db=False):
        """
        Start the Couchbase Server.
        """
        LOG.info(_("Starting Couchbase Server."))

        self._enable_db_on_boot()
        try:
            couchbase_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(
                couchbase_service['cmd_start'], shell=True)
        except exception.ProcessExecutionError:
            pass
        except KeyError:
            raise RuntimeError("Command to start Couchbase Server not found.")

        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of Couchbase Server failed."))
            try:
                utils.execute_with_timeout(system.cmd_kill)
            except exception.ProcessExecutionError:
                LOG.exception(_('Error killing Couchbase start command.'))
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start Couchbase Server")

    def enable_root(self, root_password=None):
        return CouchbaseRootAccess.enable_root(root_password)

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting Couchbase with configuration changes."))
        LOG.info(_("Configuration contents:\n %s.") % config_contents)
        if self.status.is_running:
            LOG.error(_("Cannot start Couchbase with configuration changes. "
                        "Couchbase state == %s.") % self.status)
            raise RuntimeError("Couchbase is not stopped.")
        self._write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.debug("Resetting configuration.")
        self._write_config(config_contents)

    def _write_config(self, config_contents):
        """
        Update contents of Couchbase configuration file
        """
        return


class CouchbaseAppStatus(service.BaseDbStatus):
    """
    Handles all of the status updating for the couchbase guest agent.
    """
    def _get_actual_db_status(self):
        self.ip_address = netutils.get_my_ipv4()
        pwd = None
        try:
            pwd = CouchbaseRootAccess.get_password()
            return self._get_status_from_couchbase(pwd)
        except exception.ProcessExecutionError:
            # log the exception, but continue with native config approach
            LOG.exception(_("Error getting the Couchbase status."))

        try:
            out, err = utils.execute_with_timeout(
                system.cmd_get_password_from_config, shell=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error getting the root password from the "
                            "native Couchbase config file."))
            return rd_instance.ServiceStatuses.SHUTDOWN

        config_pwd = out.strip() if out is not None else None
        if not config_pwd or config_pwd == pwd:
            LOG.debug("The root password from the native Couchbase config "
                      "file is either empty or already matches the "
                      "stored value.")
            return rd_instance.ServiceStatuses.SHUTDOWN

        try:
            status = self._get_status_from_couchbase(config_pwd)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error getting Couchbase status using the "
                            "password parsed from the native Couchbase "
                            "config file."))
            return rd_instance.ServiceStatuses.SHUTDOWN

        # if the parsed root password worked, update the stored value to
        # avoid having to consult/parse the couchbase config file again.
        LOG.debug("Updating the stored value for the Couchbase "
                  "root password.")
        CouchbaseRootAccess().write_password_to_file(config_pwd)
        return status

    def _get_status_from_couchbase(self, pwd):
        out, err = utils.execute_with_timeout(
            (system.cmd_couchbase_status %
             {'IP': self.ip_address, 'PWD': pwd}),
            shell=True)
        server_stats = json.loads(out)
        if not err and server_stats["clusterMembership"] == "active":
            return rd_instance.ServiceStatuses.RUNNING
        else:
            return rd_instance.ServiceStatuses.SHUTDOWN


class CouchbaseRootAccess(object):

    @classmethod
    def enable_root(cls, root_password=None):
        user = models.RootUser()
        user.name = "root"
        user.host = "%"
        user.password = root_password or utils.generate_random_password()

        if root_password:
            CouchbaseRootAccess().write_password_to_file(root_password)
        else:
            CouchbaseRootAccess().set_password(user.password)
        return user.serialize()

    def set_password(self, root_password):
        self.ip_address = netutils.get_my_ipv4()
        child = pexpect.spawn(system.cmd_reset_pwd % {'IP': self.ip_address})
        try:
            child.expect('.*password.*')
            child.sendline(root_password)
            child.expect('.*(yes/no).*')
            child.sendline('yes')
            child.expect('.*successfully.*')
        except pexpect.TIMEOUT:
            child.delayafterclose = 1
            child.delayafterterminate = 1
            try:
                child.close(force=True)
            except pexpect.ExceptionPexpect:
                # Close fails to terminate a sudo process on some OSes.
                subprocess.call(['sudo', 'kill', str(child.pid)])

        self.write_password_to_file(root_password)

    def write_password_to_file(self, root_password):
        operating_system.create_directory(system.COUCHBASE_CONF_DIR,
                                          as_root=True)
        try:
            tempfd, tempname = tempfile.mkstemp()
            os.fchmod(tempfd, stat.S_IRUSR | stat.S_IWUSR)
            os.write(tempfd, root_password)
            os.fchmod(tempfd, stat.S_IRUSR)
            os.close(tempfd)
        except OSError as err:
            message = _("An error occurred in saving password "
                        "(%(errno)s). %(strerror)s.") % {
                            "errno": err.errno,
                            "strerror": err.strerror}
            LOG.exception(message)
            raise RuntimeError(message)

        operating_system.move(tempname, system.pwd_file, as_root=True)

    @staticmethod
    def get_password():
        pwd = "password"
        if os.path.exists(system.pwd_file):
            with open(system.pwd_file) as file:
                pwd = file.readline().strip()
        return pwd

# Copyright 2015 Tesora Inc.
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

import itertools
import os
import stat

from mock import call, patch
from oslo_concurrency.processutils import UnknownArgumentError
from testtools import ExpectedException

from trove.common import exception
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.tests.unittests import trove_testtools


class TestOperatingSystem(trove_testtools.TestCase):

    def test_modes(self):
        self._assert_modes(None, None, None, operating_system.FileMode())
        self._assert_modes(None, None, None,
                           operating_system.FileMode([], [], []))
        self._assert_modes(0o770, 0o4, 0o3, operating_system.FileMode(
            [stat.S_IRWXU, stat.S_IRWXG],
            [stat.S_IROTH],
            [stat.S_IWOTH | stat.S_IXOTH])
        )
        self._assert_modes(0o777, None, None, operating_system.FileMode(
            [stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(0o777, None, None, operating_system.FileMode(
            reset=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(None, 0o777, None, operating_system.FileMode(
            add=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(None, None, 0o777, operating_system.FileMode(
            remove=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )

        self.assertEqual(
            operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR]),
            operating_system.FileMode(add=[stat.S_IWUSR, stat.S_IRUSR]))

        self.assertEqual(
            hash(operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR])),
            hash(operating_system.FileMode(add=[stat.S_IWUSR, stat.S_IRUSR])))

        self.assertNotEqual(
            operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR]),
            operating_system.FileMode(reset=[stat.S_IRUSR, stat.S_IWUSR]))

        self.assertNotEqual(
            hash(operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR])),
            hash(operating_system.FileMode(reset=[stat.S_IRUSR, stat.S_IWUSR]))
        )

    def _assert_modes(self, ex_reset, ex_add, ex_remove, actual):
        self.assertEqual(bool(ex_reset or ex_add or ex_remove),
                         actual.has_any())
        self.assertEqual(ex_reset, actual.get_reset_mode())
        self.assertEqual(ex_add, actual.get_add_mode())
        self.assertEqual(ex_remove, actual.get_remove_mode())

    def test_chmod(self):
        self._assert_execute_call(
            [['chmod', '-R', '=064', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.SET_GRP_RW_OTH_R,
            as_root=True)
        self._assert_execute_call(
            [['chmod', '-R', '+444', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.ADD_READ_ALL,
            as_root=True)

        self._assert_execute_call(
            [['chmod', '-R', '+060', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.ADD_GRP_RW,
            as_root=True)

        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True)

        self._assert_execute_call(
            [['chmod', '-f', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True, recursive=False, force=True)

        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'timeout': 100}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            timeout=100)

        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True, timeout=None)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "No file mode specified."),
            'path', FileMode())

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "No file mode specified."),
            'path', None)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change mode of a blank file."),
            '', FileMode.SET_FULL)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change mode of a blank file."),
            None, FileMode.SET_FULL)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', FileMode.SET_FULL, _unknown_kw=0)

    def test_remove(self):
        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.remove, None, 'path', as_root=True)

        self._assert_execute_call(
            [['rm', '-f', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.remove, None, 'path', recursive=False, force=True,
            as_root=True)

        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'timeout': 100}],
            operating_system.remove, None,
            'path', timeout=100)

        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.remove, None, 'path', timeout=None, as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot remove a blank file."), '')

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot remove a blank file."), None)

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', _unknown_kw=0)

    def test_move(self):
        self._assert_execute_call(
            [['mv', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.move, None, 'source', 'destination', as_root=True)

        self._assert_execute_call(
            [['mv', '-f', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.move, None, 'source', 'destination', force=True,
            as_root=True)

        self._assert_execute_call(
            [['mv', 'source', 'destination']],
            [{'timeout': 100}],
            operating_system.move, None, 'source', 'destination',
            timeout=100)

        self._assert_execute_call(
            [['mv', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.move, None, 'source', 'destination', timeout=None,
            as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), '', 'destination')

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), None, 'destination')

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing destination path."), 'source', '')

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing destination path."), 'source', None)

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), '', '')

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), None, None)

        self._assert_execute_call(
            None, None,
            operating_system.move,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'source', 'destination', _unknown_kw=0)

    def test_copy(self):
        self._assert_execute_call(
            [['cp', '-R', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.copy, None, 'source', 'destination', as_root=True)

        self._assert_execute_call(
            [['cp', '-f', '-p', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.copy, None, 'source', 'destination', force=True,
            preserve=True, recursive=False, as_root=True)

        self._assert_execute_call(
            [['cp', '-R', 'source', 'destination']],
            [{'timeout': 100}],
            operating_system.copy, None, 'source', 'destination',
            timeout=100)

        self._assert_execute_call(
            [['cp', '-R', 'source', 'destination']],
            [{'run_as_root': True, 'root_helper': "sudo", 'timeout': None}],
            operating_system.copy, None, 'source', 'destination', timeout=None,
            as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), '', 'destination')

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), None, 'destination')

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing destination path."), 'source', '')

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing destination path."), 'source', None)

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), '', '')

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(exception.UnprocessableEntity,
                              "Missing source path."), None, None)

        self._assert_execute_call(
            None, None,
            operating_system.copy,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'source', 'destination', _unknown_kw=0)

    def test_chown(self):
        self._assert_execute_call(
            [['chown', '-R', 'usr:grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None, 'path', 'usr', 'grp', as_root=True)

        self._assert_execute_call(
            [['chown', 'usr:grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None,
            'path', 'usr', 'grp', recursive=False, as_root=True)

        self._assert_execute_call(
            [['chown', '-f', '-R', 'usr:grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None,
            'path', 'usr', 'grp', force=True, as_root=True)

        self._assert_execute_call(
            [['chown', '-R', ':grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None, 'path', '', 'grp', as_root=True)

        self._assert_execute_call(
            [['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None, 'path', 'usr', '', as_root=True)

        self._assert_execute_call(
            [['chown', '-R', ':grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None, 'path', None, 'grp', as_root=True)

        self._assert_execute_call(
            [['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chown, None, 'path', 'usr', None, as_root=True)

        self._assert_execute_call(
            [['chown', '-R', 'usr:', 'path']],
            [{'timeout': 100}],
            operating_system.chown, None,
            'path', 'usr', None, timeout=100)

        self._assert_execute_call(
            [['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo',
              'timeout': None}],
            operating_system.chown, None,
            'path', 'usr', None, timeout=None, as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change ownership of a blank file."),
            '', 'usr', 'grp')

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change ownership of a blank file."),
            None, 'usr', 'grp')

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Please specify owner or group, or both."),
            'path', '', '')

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Please specify owner or group, or both."),
            'path', None, None)

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change ownership of a blank file."),
            None, None, None)

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change ownership of a blank file."),
            '', '', '')

        self._assert_execute_call(
            None, None,
            operating_system.chown,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', 'usr', None, _unknown_kw=0)

    def test_create_directory(self):
        self._assert_execute_call(
            [['mkdir', '-p', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None, 'path', as_root=True)

        self._assert_execute_call(
            [['mkdir', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None, 'path', force=False,
            as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', 'usr:grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'},
             {'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None,
            'path', user='usr', group='grp', as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', ':grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'},
             {'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None, 'path', group='grp',
            as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'},
             {'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None, 'path', user='usr',
            as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', 'usr:', 'path']],
            [{'timeout': 100}, {'timeout': 100}],
            operating_system.create_directory, None,
            'path', user='usr', timeout=100)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None},
             {'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.create_directory, None,
            'path', user='usr', timeout=None, as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', 'usr:', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'},
             {'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None,
            'path', user='usr', group='', as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path'], ['chown', '-R', ':grp', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'},
             {'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None,
            'path', user='', group='grp', as_root=True)

        self._assert_execute_call(
            [['mkdir', '-p', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.create_directory, None, 'path', user='', group='',
            as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.create_directory,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot create a blank directory."),
            '', user='usr', group='grp')

        self._assert_execute_call(
            None, None,
            operating_system.create_directory,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot create a blank directory."), None)

        self._assert_execute_call(
            None, None,
            operating_system.create_directory,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', _unknown_kw=0)

    def _assert_execute_call(self, exec_args, exec_kwargs,
                             fun, return_value, *args, **kwargs):
        """
        Execute a function with given arguments.
        Assert a return value and appropriate sequence of calls to the
        'utils.execute_with_timeout' interface as the result.

        :param exec_args:         Expected arguments to the execute calls.
                                  This is a list-of-list where each sub-list
                                  represent a single call to
                                  'utils.execute_with_timeout'.
        :type exec_args:          list-of-lists

        :param exec_kwargs:       Expected keywords to the execute call.
                                  This is a list-of-dicts where each dict
                                  represent a single call to
                                  'utils.execute_with_timeout'.
        :type exec_kwargs:        list-of-dicts

        :param fun:               Tested function call.
        :type fun:                callable

        :param return_value:      Expected return value or exception
                                  from the tested call if any.
        :type return_value:       object

        :param args:              Arguments passed to the tested call.
        :type args:               list

        :param kwargs:            Keywords passed to the tested call.
        :type kwargs:             dict
        """

        with patch.object(utils, 'execute_with_timeout') as exec_call:
            if isinstance(return_value, ExpectedException):
                with return_value:
                    fun(*args, **kwargs)
            else:
                actual_value = fun(*args, **kwargs)
                if return_value is not None:
                    self.assertEqual(return_value, actual_value,
                                     "Return value mismatch.")
                expected_calls = []
                for arg, kw in itertools.izip(exec_args, exec_kwargs):
                    expected_calls.append(call(*arg, **kw))

                self.assertEqual(expected_calls, exec_call.mock_calls,
                                 "Mismatch in calls to "
                                 "'execute_with_timeout'.")

    def test_get_os_redhat(self):
        with patch.object(os.path, 'isfile', side_effect=[True]):
            find_os = operating_system.get_os()
        self.assertEqual('redhat', find_os)

    def test_get_os_suse(self):
        with patch.object(os.path, 'isfile', side_effect=[False, True]):
            find_os = operating_system.get_os()
        self.assertEqual('suse', find_os)

    def test_get_os_debian(self):
        with patch.object(os.path, 'isfile', side_effect=[False, False]):
            find_os = operating_system.get_os()
        self.assertEqual('debian', find_os)

    def test_upstart_type_service_discovery(self):
        with patch.object(os.path, 'isfile', side_effect=[True]):
            mysql_service = operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_sysvinit_type_service_discovery(self):
        with patch.object(os.path, 'isfile', side_effect=[False, True, True]):
            mysql_service = operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_sysvinit_chkconfig_type_service_discovery(self):
        with patch.object(os.path, 'isfile',
                          side_effect=[False, True, False, True]):
            mysql_service = operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    @patch.object(os.path, 'islink', return_value=True)
    @patch.object(os.path, 'realpath')
    @patch.object(os.path, 'basename')
    def test_systemd_symlinked_type_service_discovery(self, mock_base,
                                                      mock_path, mock_islink):
        with patch.object(os.path, 'isfile', side_effect=[False, False, True]):
            mysql_service = operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_systemd_not_symlinked_type_service_discovery(self):
        with patch.object(os.path, 'isfile', side_effect=[False, False, True]):
            with patch.object(os.path, 'islink', return_value=False):
                mysql_service = operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_file_discovery(self):
        with patch.object(os.path, 'isfile', side_effect=[False, True]):
                config_file = operating_system.file_discovery(
                    ["/etc/mongodb.conf", "/etc/mongod.conf"])
        self.assertEqual('/etc/mongod.conf', config_file)

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import os


class AppProcessExecutor(object):
    DEPLOYMENT_BASEDIR = '/tmp/app-deployments'

    def __init__(self, broker_conn_params=None, app_tarball_path=None):
        if broker_conn_params is None:
            pass
        else:
            self.broker_conn_params = broker_conn_params
        self.app_tarball_path = app_tarball_path
        self._proc = None
        self.deployment_id = self._gen_uid()
        self.app_id = self.deployment_id
        self.__init_logger()
        atexit.register(self._cleanup)

    def start(self):
        self.deploy(self.app_tarball_path)

    def deploy(self, app_tarball_path, deployment_id=None):
        deployment_dir = os.path.join(self.DEPLOYMENT_BASEDIR,
                                      self.deployment_id)

        if not os.path.exists(deployment_dir):
            os.mkdir(deployment_dir)

        app_src_dir = os.path.join(deployment_dir, 'app')
        self._untar(app_tarball_path, app_src_dir)
        app_path = os.path.join(app_src_dir, 'app.py')
        self._run_app(app_path)

    def stop(self):
        self._kill_proc()

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(
            self.__class__.__name__ + '-' + self.deployment_id)

    def _gen_uid(self):
        return uuid.uuid4().hex[0:8]

    def _untar(self, tarball_path, dest_path):
        self.log.debug('[*] - Untar {} ...'.format(tarball_path))
        if tarball_path.endswith('tar.gz'):
            tar = tarfile.open(tarball_path)
            tar.extractall(dest_path)
            tar.close()
        else:
            self.log.debug('Not a tarball')

    def _run_app(self, app_file_path):
        _dir = os.path.dirname(app_file_path)
        app_filename = os.path.basename(app_file_path)
        command = 'cd {} && python3 -u {}'.format(_dir, app_filename)
        self._exec(command)

    def _exec(self, command):
        # args = shlex.split(command)
        self.log.info('Executing -> {}'.format(command))
        self.log.info('Starting app with id -> {}'.format(self.app_id))
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        self._proc = proc
        while True:
            out = self._proc.stdout.readline()
            err = self._proc.stderr.readline()
            if out == '' and self._proc.poll() is not None:
                break
            if out:
                self.log.info(out.strip().decode())
            if err:
                self.log.error(err.strip().decode())
        # output, error = self._proc.communicate()
        self._proc.poll()
        self.log.info('App <{}> terminated'.format(self.app_id))
        return proc

    def _kill_proc(self):
        if self._proc is not None:
            self._proc.kill()

    def _cleanup(self):
        self._kill_proc()


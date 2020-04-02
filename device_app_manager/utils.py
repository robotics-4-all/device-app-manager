from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)


def extract_tarball(tarball_path, dest_path)
    self.log.debug('[*] - Untar {} ...'.format(tarball_path))
    if tarball_path.endswith('tar.gz'):
        tar = tarfile.open(tarball_path)
        tar.extractall(dest_path)
        tar.close()
    else:
        raise ValueError('Not a tarball')

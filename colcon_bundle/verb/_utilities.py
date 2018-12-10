# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import itertools
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


from colcon_bundle.verb import logger


class Timer:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.start = time.clock()
        return self

    def __exit__(self, *args):
        self.end = time.clock()
        self.interval = self.end - self.start
        with open("timing.txt", "a") as myfile:
            myfile.write(self.name + " " + str(self.interval))


def update_shebang(path):
    """
    Search for python shebangs in path and all sub-paths.

    It then replaces them with /usr/bin/env.
    env does not support parameters so we need to so something
    else if python is invoked with parameters

    :param path: Path to file to replace shebang in
    :return: None
    """
    # TODO: We should handle scripts that have parameters in the shebang
    # TODO: We should hangle scripts that are doing other /usr/bin executables
    with Timer('update shebangs'):
        py3_shebang_regex = re.compile(r'#!\s*.+python3')
        py_shebang_regex = re.compile(r'#!\s*.+python')
        logger.info('Starting shebang update...')
        for (root, dirs, files) in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                if not os.path.islink(file_path):
                    with open(file_path, 'rb+') as file_handle:
                        contents = file_handle.read()
                        try:
                            str_contents = contents.decode()
                        except UnicodeError:
                            continue
                        py3_replacement_tuple = py3_shebang_regex.subn(
                            '#!/usr/bin/env python3', str_contents, count=1)
                        if py3_replacement_tuple[1] > 0:
                            logger.info('Found shebang in {file_path}'.format_map(
                                locals()))
                            file_handle.seek(0)
                            file_handle.truncate()
                            file_handle.write(py3_replacement_tuple[0].encode())
                            continue

                        py_replacement_tuple = py_shebang_regex.subn(
                            '#!/usr/bin/env python', str_contents, count=1)
                        if py_replacement_tuple[1] > 0:
                            logger.info('Found shebang in {file_path}'.format_map(
                                locals()))
                            file_handle.seek(0)
                            file_handle.truncate()
                            file_handle.write(py_replacement_tuple[0].encode())


def update_symlinks(base_path):
    """
    Update all symlinks inside of base_path to be relative.

    Recurse through the path and update all symlinks to be relative except
    symlinks to libc this is because we want our applications to call into
    the libraries we are bundling. We do not bundle libc and want to use the
    system's version, so we should not update those. Copy any other libraries,
    not found in the bundle, into the bundle so that relative symlinks work.
    """
    logger.info('Updating symlinks in {base_path}'.format_map(locals()))
    encoding = sys.getfilesystemencoding()
    dpkg_libc_paths = subprocess.check_output(['dpkg', '-L', 'libc6']).decode(
        encoding).strip()
    libc_paths = set(dpkg_libc_paths.split('\n'))
    with Timer('update symlinks'):
        for root, subdirs, files in os.walk(base_path):
            for name in itertools.chain(subdirs, files):
                symlink_path = os.path.join(root, name)
                if os.path.islink(symlink_path) and os.path.isabs(
                        os.readlink(symlink_path)):
                    symlink_dest_path = os.readlink(symlink_path)
                    if symlink_dest_path in libc_paths:
                        # We don't want to update symlinks which are pointing to
                        # libc
                        continue
                    else:
                        logger.info(
                            'Symlink: {symlink_path} Points to: {'
                            'symlink_dest_path}'.format_map(locals()))
                        bundle_library_path = os.path.join(base_path,
                                                           symlink_dest_path[1:])
                        if os.path.exists(bundle_library_path):
                            # Dep is already installed, update symlink
                            logger.info(
                                'Linked file is already in bundle at {}, '
                                'updating symlink...'.format(bundle_library_path))
                        else:
                            # Dep is not installed, we need to copy it...
                            logger.info(
                                'Linked file is not in bundle, copying and '
                                'updating symlink...')
                            if not os.path.exists(
                                    os.path.dirname(bundle_library_path)):
                                # Create directory (permissions?)
                                os.makedirs(os.path.dirname(bundle_library_path),
                                            exist_ok=True)
                            shutil.copy(symlink_dest_path,
                                        bundle_library_path)

                        bundle_library_path_obj = Path(bundle_library_path)
                        symlink_path_obj = Path(symlink_path)

                        relative_path = os.path.relpath(bundle_library_path,
                                                        symlink_path)
                        logger.info(
                            'bundle_library_path {} relative path {}'.format(
                                bundle_library_path, relative_path))
                        os.remove(symlink_path)
                        os.symlink(relative_path, symlink_path)

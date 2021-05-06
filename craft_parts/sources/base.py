# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2015-2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Base classes for source type handling."""

import abc
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

import requests

from craft_parts import utils
from craft_parts.dirs import ProjectDirs
from craft_parts.utils import url_utils

from . import errors
from .cache import FileCache
from .checksum import verify_checksum


class SourceHandler(abc.ABC):
    """The base class for source type handlers.

    Methods :meth:`check_if_outdated` and :meth:`update_source` can be
    overridden by subclasses to implement verification and update of
    source files.
    """

    # pylint: disable=too-many-arguments

    def __init__(
        self,
        source: Union[str, Path],
        part_src_dir: Union[str, Path],
        *,
        application_name: Optional[str] = None,
        source_tag: Optional[str] = None,
        source_commit: Optional[str] = None,
        source_branch: Optional[str] = None,
        source_depth: Optional[int] = None,
        source_checksum: Optional[str] = None,
        command: Optional[str] = None,
        project_dirs: Optional[ProjectDirs] = None,
    ):
        if not application_name:
            application_name = utils.package_name()

        if not project_dirs:
            project_dirs = ProjectDirs()

        self.source = str(source)
        self.part_src_dir = str(part_src_dir)
        self.source_tag = source_tag
        self.source_commit = source_commit
        self.source_branch = source_branch
        self.source_depth = source_depth
        self.source_checksum = source_checksum
        self.source_details = None

        self.command = command

        self._application_name = application_name
        self._dirs = project_dirs
        self._checked = False

    # pylint: enable=too-many-arguments

    @abc.abstractmethod
    def pull(self) -> None:
        """Retrieve the source file."""

    def check_if_outdated(
        self, target: str, *, ignore_files: Optional[List[str]] = None
    ) -> bool:
        """Check if pulled sources have changed since target was created.

        :param target: Path to target file.
        :param ignore_files: Files excluded from verification.

        :return: Whether the sources are outdated.

        :raise errors.SourceUpdateUnsupported: If the source handler can't check if
            files are outdated.
        """
        raise errors.SourceUpdateUnsupported(self.__class__.__name__)

    def update(self):
        """Update pulled source.

        :raise errors.SourceUpdateUnsupported: If the source can't update its files.
        """
        raise errors.SourceUpdateUnsupported(self.__class__.__name__)

    @classmethod
    def _run_output(cls, command, **kwargs) -> str:
        try:
            return (
                subprocess.check_output(command, **kwargs)
                # .decode(sys.getfilesystemencoding())
                .strip()
            )
        except subprocess.CalledProcessError as err:
            raise errors.PullError(command=command, exit_code=err.returncode)


class FileSourceHandler(SourceHandler):
    """Base class for file source types."""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        source: Union[str, Path],
        part_src_dir: Union[str, Path],
        *,
        application_name: Optional[str],
        source_tag: Optional[str] = None,
        source_commit: Optional[str] = None,
        source_branch: Optional[str] = None,
        source_depth: Optional[int] = None,
        source_checksum: Optional[str] = None,
        command: Optional[str] = None,
        project_dirs: Optional[ProjectDirs] = None,
    ):
        super().__init__(
            source,
            part_src_dir,
            application_name=application_name,
            source_tag=source_tag,
            source_commit=source_commit,
            source_branch=source_branch,
            source_depth=source_depth,
            source_checksum=source_checksum,
            command=command,
            project_dirs=project_dirs,
        )
        self._file = ""

    # pylint: enable=too-many-arguments

    @abc.abstractmethod
    def provision(
        self, dst: str, clean_target: bool = True, keep: bool = False, src: str = None
    ) -> None:
        """Process the source file to extract its payload."""

    def pull(self) -> None:
        """Retrieve this source from its origin."""
        source_file = None
        is_source_url = url_utils.is_url(self.source)

        # First check if it is a url and download and if not
        # it is probably locally referenced.
        if is_source_url:
            source_file = self.download()
        else:
            basename = os.path.basename(self.source)
            source_file = os.path.join(self.part_src_dir, basename)
            # We make this copy as the provisioning logic can delete
            # this file and we don't want that.
            try:
                shutil.copy2(self.source, source_file)
            except FileNotFoundError as err:
                raise errors.SourceNotFound(self.source) from err

        # Verify before provisioning
        if self.source_checksum:
            verify_checksum(self.source_checksum, source_file)

        # We finally provision, but we don't clean the target so override-pull
        # can actually have meaning when using these sources.
        self.provision(self.part_src_dir, src=source_file, clean_target=False)

    def download(self, filepath: str = None) -> str:
        """Download the URL from a remote location.

        :param filepath: the destination file to download to.
        """
        if filepath is None:
            self._file = os.path.join(self.part_src_dir, os.path.basename(self.source))
        else:
            self._file = filepath

        # check if we already have the source file cached
        file_cache = FileCache(self._application_name)
        if self.source_checksum:
            cache_file = file_cache.get(key=self.source_checksum)
            if cache_file:
                # We make this copy as the provisioning logic can delete
                # this file and we don't want that.
                shutil.copy2(cache_file, self._file)
                return self._file

        # if not we download and store
        if url_utils.get_url_scheme(self.source) == "ftp":
            # FIXME: handle ftp downloads
            raise NotImplementedError("ftp download not implemented")

        try:
            request = requests.get(self.source, stream=True, allow_redirects=True)
            request.raise_for_status()
        except requests.exceptions.RequestException as err:
            raise errors.NetworkRequestError(
                message=f"network request failed (request={err.request!r}, "
                "response={err.response!r}"
            )

        url_utils.download_request(request, self._file)

        # if source_checksum is defined cache the file for future reuse
        if self.source_checksum:
            verify_checksum(self.source_checksum, self._file)
            file_cache.cache(filename=self._file, key=self.source_checksum)
        return self._file

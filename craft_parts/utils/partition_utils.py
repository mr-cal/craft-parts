# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2023 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Partition helpers."""

import re
from pathlib import Path
from typing import Union

from craft_parts.features import Features


def get_partition_compatible_filepath(filepath: Union[Path, str]) -> Union[Path, str]:
    """Get a filepath compatible with the partitions feature."""
    if not Features().enable_partitions:
        return filepath

    # do not modify default globs
    if filepath == "*":
        return filepath

    match = re.match("\\((?P<partition>[a-z]+)\\)/(?P<filepath>.*)", str(filepath))
    if match:
        partition = match.group("partition")
        everything_else = match.group("filepath")
    else:
        partition = "default"
        everything_else = filepath

    if isinstance(filepath, str):
        return str(Path(partition, everything_else))
    return Path(partition, everything_else)

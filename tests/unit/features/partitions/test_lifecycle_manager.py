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
"""Unit tests for the lifecycle manager with the partitions feature."""
import sys
import textwrap
from string import ascii_lowercase
from textwrap import dedent
from typing import Any, Dict

import pytest
import pytest_check  # type: ignore[import]
import yaml
from craft_parts import errors, lifecycle_manager
from hypothesis import HealthCheck, given, settings, strategies

from tests.unit import test_lifecycle_manager

mock_available_plugins = test_lifecycle_manager.mock_available_plugins


def valid_partitions_strategy():
    """A strategy for a list of valid partitions.

    The ruleset is defined in the LifecycleManager docstrings.
    """
    strategy = strategies.lists(
        strategies.text(strategies.sampled_from(ascii_lowercase), min_size=1),
        min_size=1,
        unique=True,
    ).map(lambda lst: ["default", *lst])

    # ensure "default" is not repeated in the list
    return strategy.filter(lambda partitions: "default" not in partitions[1:])


class TestPartitionsSupport:
    """Verify LifecycleManager supports partitions."""

    @pytest.fixture()
    def partition_list(self):
        """Return a list of partitions, 'default' and 'kernel'."""
        return ["default", "kernel"]

    @pytest.fixture()
    def parts_data(self) -> Dict[str, Any]:
        return {"parts": {"foo": {"plugin": "nil"}}}

    @pytest.mark.parametrize("partitions", [["default"], ["default", "kernel"]])
    @pytest.mark.parametrize("work_dir", [".", "work_dir"])
    def test_project_info(self, check, new_dir, parts_data, partitions, work_dir):
        """Verify partitions are parsed and passed to ProjectInfo."""
        lifecycle = lifecycle_manager.LifecycleManager(
            parts_data,
            application_name="test_manager",
            project_name="project",
            cache_dir=new_dir,
            work_dir=work_dir,
            arch="aarch64",
            parallel_build_count=16,
            custom="foo",
            partitions=partitions,
        )
        info = lifecycle.project_info

        check.equal(info.application_name, "test_manager")
        check.equal(info.project_name, "project")
        check.equal(info.target_arch, "arm64")
        check.equal(info.arch_triplet, "aarch64-linux-gnu")
        check.equal(info.parallel_build_count, 16)
        check.equal(info.dirs.parts_dir, new_dir / work_dir / "parts")
        check.equal(info.dirs.stage_dir, new_dir / work_dir / "stage/default")
        check.equal(info.dirs.prime_dir, new_dir / work_dir / "prime/default")
        check.equal(info.custom_args, ["custom"])
        check.equal(info.custom, "foo")
        check.equal(info.partitions, partitions)

    @pytest.mark.parametrize("partitions", [None, []])
    def test_no_partitions(self, new_dir, parts_data, partitions):
        """Raise an error if the partitions feature is enabled but not defined."""
        with pytest.raises(errors.FeatureError) as raised:
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test_manager",
                cache_dir=new_dir,
                partitions=partitions,
            )

        assert (
            raised.value.message
            == "Partition feature is enabled but no partitions are defined."
        )

    # `new_dir` is function-scoped but does not affect the testing of partition names
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(partitions=valid_partitions_strategy())
    def test_partitions_valid(self, new_dir, parts_data, partitions):
        """Process valid partition names."""
        lifecycle = lifecycle_manager.LifecycleManager(
            parts_data,
            application_name="test_manager",
            cache_dir=new_dir,
            partitions=partitions,
        )

        info = lifecycle.project_info

        pytest_check.equal(info.partitions, partitions)

    @pytest.mark.parametrize(
        "partitions",
        [
            ["defaultbad"],
            ["kernel"],
            ["kernel", "kernel"],
            ["kernel", "default"],
        ],
    )
    def test_partitions_default_not_first(self, new_dir, parts_data, partitions):
        """Raise an error if the first partition is not 'default'."""
        with pytest.raises(errors.FeatureError) as raised:
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test_manager",
                cache_dir=new_dir,
                partitions=partitions,
            )

        assert raised.value.brief == "First partition must be 'default'."

    @pytest.mark.parametrize(
        "partitions",
        [
            ["default", ""],
            ["default", "Test"],
            ["default", "TEST"],
            ["default", "test1"],
            ["default", "te-st"],
        ],
    )
    def test_partitions_invalid(self, new_dir, parts_data, partitions):
        """Raise an error if partitions are not lowercase alphabetical characters."""
        with pytest.raises(
            errors.FeatureError,
            match=r"Partition '[\w-]*' must only contain lowercase letters.*",
        ):
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test_manager",
                cache_dir=new_dir,
                partitions=partitions,
            )

    @pytest.mark.parametrize(
        "partitions",
        [
            ["default", "default"],
            ["default", "default", "kernel"],
            ["default", "default", "kernel", "kernel"],
            ["default", "kernel", "kernel"],
        ],
    )
    def test_partitions_duplicates(self, new_dir, parts_data, partitions):
        """Raise an error if there are duplicate partitions."""
        with pytest.raises(errors.FeatureError) as raised:
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test_manager",
                cache_dir=new_dir,
                partitions=partitions,
            )

        assert raised.value.message == "Partitions must be unique."

    def test_partitions_usage_valid(self, new_dir, partition_list):
        """Verify partitions can be used in parts when creating a LifecycleManager."""
        parts_data = {
            "parts": {
                "foo": {
                    "plugin": "nil",
                    "stage": ["(default)/foo"],
                },
            }
        }

        # nothing to assert, just ensure an exception is not raised
        lifecycle_manager.LifecycleManager(
            parts_data,
            application_name="test_manager",
            cache_dir=new_dir,
            partitions=partition_list,
        )

    def test_partitions_usage_invalid(self, new_dir, partition_list):
        """Invalid uses of partitions are raised when creating a LifecycleManager."""
        parts_data = {
            "parts": {
                "foo": {
                    "plugin": "nil",
                    "stage": ["(test)/foo"],
                },
            }
        }
        with pytest.raises(errors.FeatureError) as raised:
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test_manager",
                cache_dir=new_dir,
                partitions=partition_list,
            )

        assert raised.value.message == dedent(
            """\
            Error: Invalid usage of partitions:
              parts.foo.stage
                unknown partition 'test' in '(test)/foo'
            Valid partitions are 'default' and 'kernel'."""
        )


class TestLifecycleManager(test_lifecycle_manager.TestLifecycleManager):
    """Lifecycle manager tests with partitions enabled."""

    @pytest.fixture(autouse=True)
    def setup_method_fixture(self):
        # pylint: disable=attribute-defined-outside-init
        yaml_data = textwrap.dedent(
            """
            parts:
              foo:
                plugin: nil
            """
        )
        self._data = yaml.safe_load(yaml_data)
        self._lcm_kwargs = {"partitions": ["default", "mypart", "yourpart"]}
        # pylint: enable=attribute-defined-outside-init

    @pytest.mark.parametrize("work_dir", [".", "work_dir"])
    def test_project_info(self, new_dir, work_dir):
        lf = lifecycle_manager.LifecycleManager(
            self._data,
            application_name="test_manager",
            project_name="project",
            cache_dir=new_dir,
            work_dir=work_dir,
            arch="aarch64",
            parallel_build_count=16,
            custom="foo",
            **self._lcm_kwargs,
        )
        info = lf.project_info

        pytest_check.equal(info.application_name, "test_manager")
        pytest_check.equal(info.project_name, "project")
        pytest_check.equal(info.target_arch, "arm64")
        pytest_check.equal(info.arch_triplet, "aarch64-linux-gnu")
        pytest_check.equal(info.parallel_build_count, 16)
        pytest_check.equal(info.dirs.parts_dir, new_dir / work_dir / "parts")
        pytest_check.equal(info.dirs.stage_dir, new_dir / work_dir / "stage/default")
        pytest_check.equal(info.dirs.prime_dir, new_dir / work_dir / "prime/default")
        pytest_check.equal(info.custom_args, ["custom"])
        pytest_check.equal(info.custom, "foo")


class TestOverlayDisabled(test_lifecycle_manager.TestOverlayDisabled):
    """Check that the overlay feature is still disabled."""

    def test_overlay_supported(self, mocker, new_dir, parts_data):
        mocker.patch.object(sys, "platform", "linux")
        mocker.patch("os.geteuid", return_value=0)
        with pytest.raises(errors.PartSpecificationError) as raised:
            lifecycle_manager.LifecycleManager(
                parts_data,
                application_name="test",
                cache_dir=new_dir,
                base_layer_dir=new_dir,
                base_layer_hash=b"hash",
                partitions=["default"],
            )
        assert raised.value.part_name == "foo"
        assert (
            raised.value.message == "- overlays not supported in field 'overlay-script'"
        )


class TestPluginProperties(test_lifecycle_manager.TestPluginProperties):
    """Tests for plugin properties with partitions enabled."""

    def _get_manager(self, new_dir, **kwargs):
        manager_kwargs = {
            "application_name": "test_manager",
            "cache_dir": new_dir,
            "partitions": ["default", "mypart", "yourpart"],
        }
        manager_kwargs.update(kwargs)
        return lifecycle_manager.LifecycleManager(**manager_kwargs)

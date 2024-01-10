"""Test partitions."""

from textwrap import dedent
import yaml

from craft_parts import LifecycleManager, Step


def test_partitions(new_dir):
    """Main function."""
    parts_yaml = dedent("""
    parts:
      hello:
        plugin: nil
        source: .
        override-build:
          touch ${CRAFT_PART_INSTALL}/A
          touch ${CRAFT_PART_INSTALL}/B
          craftctl default
        organize:
          (default)/A: A1
          (default)/B: (kernel)/B1
          #(default)/C: (component/bar-baz)/C1
        stage:
          - (default)/A1
          - (kernel)/B1
          #- (component/bar-baz)/C1
          #- D
     """)

    parts = yaml.safe_load(parts_yaml)

    lcm = LifecycleManager(
        parts,
        application_name="example",
        cache_dir=".",
        partitions=["default", "kernel"], #, "component/bar-baz"],
    )

    with lcm.action_executor() as aex:
        aex.execute(lcm.plan(Step.PRIME))

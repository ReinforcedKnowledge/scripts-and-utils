import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class PyarmorBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """
        This runs before the build process.
        We'll use this to run PyArmor and prepare the obfuscated files.
        """
        self.temp_dir = Path(tempfile.mkdtemp())

        src_package = Path(self.root) / "src" / "my_package"
        temp_package = self.temp_dir / "src" / "my_package"
        temp_package.parent.mkdir(parents=True)
        shutil.copytree(src_package, temp_package)

        pyarmor_build = self.temp_dir / "pyarmor_build"
        pyarmor_build.mkdir()

        try:
            subprocess.run(
                [
                    "pyarmor",
                    "gen",
                    "-O",
                    str(pyarmor_build),
                    "-r",
                    str(temp_package),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(self.temp_dir)
            raise RuntimeError(f"PyArmor failed: {e.stdout}\n{e.stderr}")

        obfuscated_package = pyarmor_build / "my_package"
        runtime_dir = next(
            d.name
            for d in pyarmor_build.iterdir()
            if d.name.startswith("pyarmor_runtime_")
        )
        runtime_path = pyarmor_build / runtime_dir

        final_package_dir = self.temp_dir / "src" / "my_package"
        if final_package_dir.exists():
            shutil.rmtree(final_package_dir)

        shutil.copytree(runtime_path, final_package_dir / runtime_dir)

        for file in obfuscated_package.iterdir():
            if file.suffix == ".py":
                dst_file = final_package_dir / file.name

                content = file.read_text()

                content = content.replace(
                    "from pyarmor_runtime_000000 import __pyarmor__",
                    "from .pyarmor_runtime_000000 import __pyarmor__",
                )

                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_text(content)

        build_data["force_include"].update(
            {
                str(f): str(f).replace(f"{self.temp_dir}/src/", "")
                for f in self._get_all_files(final_package_dir)
            }
        )

    def finalize(
        self, version: str, build_data: dict[str, Any], artifact_path: str
    ) -> None:
        """
        This runs after the build process.
        We'll use this to clean up our temporary files.
        """
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir)

    def _get_all_files(self, directory: str) -> list[str]:
        return [str(f) for f in directory.rglob("*") if f.is_file()]

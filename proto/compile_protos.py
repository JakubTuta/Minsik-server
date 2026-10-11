"""Compile every proto into the service packages that hold a generated copy.

    python proto/compile_protos.py

CI runs this and fails if it changes anything, so a .proto edit cannot be merged
without its regenerated Python (the gateway image compiles protos itself, which would
otherwise hide a stale checked-in copy).
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

DESTINATIONS: dict[str, list[str]] = {
    "ingestion": ["ingestion", "gateway"],
    "books": ["books", "gateway", "ingestion"],
    "auth": ["auth", "gateway"],
    "recommendation": ["recommendation", "gateway"],
    "user_data": ["user_data", "gateway"],
}


def compile_proto(name: str, services: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable, "-m", "grpc_tools.protoc",
                f"-I{ROOT / 'proto'}", f"--python_out={tmp}", f"--grpc_python_out={tmp}", f"--pyi_out={tmp}",
                str(ROOT / "proto" / f"{name}.proto"),
            ],
            check=True,
        )
        grpc_file = pathlib.Path(tmp) / f"{name}_pb2_grpc.py"
        content = grpc_file.read_text(encoding="utf-8")
        grpc_file.write_text(
            re.sub(rf"(?m)^import {name}_pb2", f"from . import {name}_pb2", content),
            encoding="utf-8",
            newline="",
        )

        for service in services:
            destination = ROOT / "services" / service / "app" / "proto"
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "__init__.py").touch()
            for suffix in ("_pb2.py", "_pb2_grpc.py", "_pb2.pyi"):
                shutil.copyfile(pathlib.Path(tmp) / f"{name}{suffix}", destination / f"{name}{suffix}")


if __name__ == "__main__":
    for proto_name, target_services in DESTINATIONS.items():
        compile_proto(proto_name, target_services)
        print(f"compiled {proto_name} -> {', '.join(target_services)}")

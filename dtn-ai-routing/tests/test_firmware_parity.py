"""
Test suite for Stage 6A: ESP8266 Node Firmware Foundation.

Validates:
1. Integrity and presence of all modular firmware headers and source files.
2. Memory footprint invariants (PacketWireHeader <= 48B, NodeConditionReport <= 48B).
3. Host compilation of the firmware test harness (tests/test_firmware.cpp) using g++.
4. Native execution of all 6 firmware unit tests (serialization, buffer, routing, transport, reports, coordinator).
5. ESP8266 target toolchain presence check and documentation.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = PROJECT_ROOT / "firmware" / "esp8266_node"
TESTS_DIR = PROJECT_ROOT / "tests"


def test_firmware_file_structure():
    """Confirms all required modular firmware headers and implementation files exist."""
    required_files = [
        FIRMWARE_DIR / "platformio.ini",
        FIRMWARE_DIR / "include" / "dtn_types.h",
        FIRMWARE_DIR / "include" / "node_config.h",
        FIRMWARE_DIR / "include" / "packet.h",
        FIRMWARE_DIR / "include" / "packet_buffer.h",
        FIRMWARE_DIR / "include" / "router_interface.h",
        FIRMWARE_DIR / "include" / "decision_tree_router.h",
        FIRMWARE_DIR / "include" / "direct_delivery_router.h",
        FIRMWARE_DIR / "include" / "transport_interface.h",
        FIRMWARE_DIR / "include" / "fake_transport.h",
        FIRMWARE_DIR / "include" / "display_interface.h",
        FIRMWARE_DIR / "include" / "null_display.h",
        FIRMWARE_DIR / "include" / "storage_interface.h",
        FIRMWARE_DIR / "include" / "ram_storage.h",
        FIRMWARE_DIR / "include" / "condition_report.h",
        FIRMWARE_DIR / "include" / "event_logger.h",
        FIRMWARE_DIR / "include" / "node_app.h",
        FIRMWARE_DIR / "include" / "self_test.h",
        FIRMWARE_DIR / "src" / "packet.cpp",
        FIRMWARE_DIR / "src" / "packet_buffer.cpp",
        FIRMWARE_DIR / "src" / "condition_report.cpp",
        FIRMWARE_DIR / "src" / "node_app.cpp",
        FIRMWARE_DIR / "src" / "main.cpp",
    ]

    for f in required_files:
        assert f.exists(), f"Missing firmware file: {f}"
        assert f.stat().st_size > 50, f"Firmware file is empty or too small: {f}"


def test_firmware_cxx_test_harness_compilation_and_execution():
    """
    Compiles and executes the native host test harness tests/test_firmware.cpp,
    verifying 100% pass across all 6 firmware foundation unit tests.
    """
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler and Path("C:/msys64/ucrt64/bin/g++.exe").exists():
        compiler = "C:/msys64/ucrt64/bin/g++.exe"

    assert compiler is not None, "Host C++ compiler required for firmware tests"

    src_file = TESTS_DIR / "test_firmware.cpp"
    exe_file = TESTS_DIR / "test_firmware.exe"
    inc_dir = FIRMWARE_DIR / "include"

    # Compile
    cmd_build = [
        str(compiler),
        "-O2",
        "-std=c++17",
        "-Wall",
        "-Wextra",
        f"-I{inc_dir}",
        str(src_file),
        "-o",
        str(exe_file),
    ]
    res_build = subprocess.run(cmd_build, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res_build.returncode == 0, f"Firmware test compilation failed:\n{res_build.stderr}"
    assert exe_file.exists(), "Binary executable not produced"

    # Run
    res_run = subprocess.run([str(exe_file)], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res_run.returncode == 0, f"Firmware tests failed:\n{res_run.stdout}\n{res_run.stderr}"
    assert "Results: 10 / 10 passed." in res_run.stdout, f"Not all tests passed:\n{res_run.stdout}"


def test_esp8266_toolchain_presence():
    """
    Checks for the cross-compilation toolchain for ESP8266.
    Documents whether native cross-compilation to Xtensa elf is available or absent.
    """
    user_scripts = os.path.expanduser("~\\AppData\\Roaming\\Python\\Python312\\Scripts")
    pio = shutil.which("pio") or shutil.which("platformio") or shutil.which("pio.exe", path=user_scripts)
    xtensa_gcc = shutil.which("xtensa-lx106-elf-g++") or shutil.which("xtensa-lx106-elf-gcc")
    arduino_cli = shutil.which("arduino-cli")

    toolchain_status = {
        "platformio": pio,
        "xtensa_lx106_gcc": xtensa_gcc,
        "arduino_cli": arduino_cli,
    }

    has_toolchain = any(v is not None for v in toolchain_status.values())
    assert has_toolchain, "PlatformIO or cross-compilation toolchain should be detected"


def test_platformio_target_compilation():
    """
    Executes PlatformIO cross-compilation for ESP8266 NodeMCU v2 target,
    confirming firmware.elf and firmware.bin build with 0 errors.
    """
    res = subprocess.run(
        [sys.executable, "-m", "platformio", "run", "-d", str(FIRMWARE_DIR)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT)
    )
    assert res.returncode == 0, f"PlatformIO compilation failed:\n{res.stderr}\n{res.stdout}"
    assert "SUCCESS" in res.stdout, f"PlatformIO output did not indicate SUCCESS:\n{res.stdout}"
    elf_file = FIRMWARE_DIR / ".pio" / "build" / "nodemcuv2" / "firmware.elf"
    bin_file = FIRMWARE_DIR / ".pio" / "build" / "nodemcuv2" / "firmware.bin"
    assert elf_file.exists(), "Target firmware.elf does not exist"
    assert bin_file.exists(), "Target firmware.bin does not exist"



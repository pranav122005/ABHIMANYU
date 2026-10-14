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
        FIRMWARE_DIR / "include" / "esp_now_transport.h",
        FIRMWARE_DIR / "include" / "oled_display.h",
        FIRMWARE_DIR / "src" / "packet.cpp",
        FIRMWARE_DIR / "src" / "packet_buffer.cpp",
        FIRMWARE_DIR / "src" / "condition_report.cpp",
        FIRMWARE_DIR / "src" / "node_app.cpp",
        FIRMWARE_DIR / "src" / "esp_now_transport.cpp",
        FIRMWARE_DIR / "src" / "oled_display.cpp",
        FIRMWARE_DIR / "src" / "main.cpp",
    ]

    for f in required_files:
        assert f.exists(), f"Missing firmware file: {f}"
        assert f.stat().st_size > 50, f"Firmware file is empty or too small: {f}"


def test_firmware_cxx_test_harness_compilation_and_execution():
    """
    Compiles and executes the native host test harness tests/test_firmware.cpp,
    verifying 100% pass across all firmware foundation and hardware unit tests.
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
    assert "Results: 27 / 27 passed." in res_run.stdout, f"Not all tests passed:\n{res_run.stdout}"


def test_esp8266_toolchain_presence():
    """
    Checks for the cross-compilation toolchain for ESP8266.
    Documents whether native cross-compilation to Xtensa elf is available or absent.
    """
    custom_pio = Path(os.path.expanduser("~/.platformio/penv/Scripts/pio.exe"))
    pio = shutil.which("pio") or shutil.which("platformio") or (str(custom_pio) if custom_pio.exists() else None)
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
    Executes PlatformIO cross-compilation for Node A (OLED) and Node B (headless) targets,
    confirming firmware.bin builds with 0 errors.
    """
    pio_exe = shutil.which("pio") or shutil.which("platformio")
    if not pio_exe:
        custom_pio = Path(os.path.expanduser("~/.platformio/penv/Scripts/pio.exe"))
        if custom_pio.exists():
            pio_exe = str(custom_pio)

    if not pio_exe:
        pytest.skip("PlatformIO executable not found in PATH or default virtualenv")

    res = subprocess.run(
        [pio_exe, "run", "-d", str(FIRMWARE_DIR), "-e", "node_a", "-e", "node_b"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT)
    )
    assert res.returncode == 0, f"PlatformIO compilation failed:\n{res.stderr}\n{res.stdout}"
    assert "SUCCESS" in res.stdout, f"PlatformIO output did not indicate SUCCESS:\n{res.stdout}"

    bin_a = FIRMWARE_DIR / ".pio" / "build" / "node_a" / "firmware.bin"
    bin_b = FIRMWARE_DIR / ".pio" / "build" / "node_b" / "firmware.bin"
    assert bin_a.exists(), "Target node_a firmware.bin does not exist"
    assert bin_b.exists(), "Target node_b firmware.bin does not exist"


def test_firmware_realistic_scenarios_validation():
    """
    Verifies that all 17 realistic host DTN lifecycle scenarios execute and pass:
    - Scenarios 1-12: Core DTN packet buffering, duplicate suppression, TTL expiry, retries
    - Scenarios 13-17: ESP-NOW frame limits, 2-node exchange, duplicates, AI routing, OLED updates
    """
    exe_file = TESTS_DIR / "test_firmware.exe"
    assert exe_file.exists(), "Binary executable not found; must compile first"

    res_run = subprocess.run([str(exe_file)], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res_run.returncode == 0, f"Host test runner returned error code: {res_run.returncode}"

    scenarios = [
        "test_scenario_1_buffered_for_later_forwarding",
        "test_scenario_2_no_peer_available_packet_remains_queued",
        "test_scenario_3_send_fails_eligible_for_later_retry",
        "test_scenario_4_duplicate_packet_suppression",
        "test_scenario_5_packet_expires_while_buffered",
        "test_scenario_6_destination_reachable_delivery_completes",
        "test_scenario_7_relayed_through_intermediate_node",
        "test_scenario_8_buffer_slot_limit_enforced",
        "test_scenario_9_buffer_byte_limit_enforced",
        "test_scenario_10_concurrent_transmission_protection",
        "test_scenario_11_missing_acknowledgement_handling",
        "test_scenario_12_timer_rollover_lifecycle",
        "test_esp_now_frame_size_and_truncation_safety",
        "test_2node_bidirectional_espnow_exchange_and_ack",
        "test_2node_duplicate_packet_suppression",
        "test_2node_ai_relay_decision_behavior",
        "test_oled_display_formatting_and_status_update",
    ]

    for sc in scenarios:
        assert f"[RUNNING] {sc}... PASSED" in res_run.stdout, f"Scenario failed or missing: {sc}"




# This file is part of Snagboot
# Copyright (C) 2025 Renesas Electronics Corporation
#
# Written by Show Liu <show.liu.yj@renesas.com> in 2025.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Renesas RZ Series MPU Recovery Implementation

This module implements the recovery flow for Renesas RZ series MPUs,
including RZ/G and RZ/V and others.

Recovery Flow:
1. Wait for SCIF Download Mode
2. Load Flash Writer to SRAM
3. (Optional) Negotiate UART speed up

The recovery leverages Renesas Flash Writer, which initializes DDR
and provides commands for memory operations and firmware programming.
"""

import time
import logging
from snagrecover.protocols.renesas_scif import RenesasSCIF
from snagrecover.config import recovery_config

logger = logging.getLogger("snagrecover")


def main():
	"""
	Main recovery function for Renesas RZ series devices.

	This function is called by snagrecover CLI and performs the
	complete recovery sequence based on the configuration.

	Raises:
		Exception: If recovery fails at any stage
	"""
	# Get configuration
	soc_model = recovery_config["soc_model"]
	serial_port = recovery_config.get("serial_port", "/dev/ttyUSB0")
	baudrate = recovery_config.get("baudrate", 115200)
	enable_speed_up = recovery_config.get("enable_speed_up", True)

	logger.info(f"Starting Renesas RZ recovery for {soc_model}")
	logger.info(f"Serial port: {serial_port}, baudrate: {baudrate}")

	# Initialize SCIF connection
	scif = RenesasSCIF(serial_port, baudrate)

	try:
		# Open serial port
		scif.open()
		logger.info("Serial port opened successfully")

		# Stage 1: Wait for SCIF Download Mode
		logger.info("=" * 60)
		logger.info("Stage 1: Waiting for SCIF Download Mode")
		logger.info("=" * 60)
		logger.info("Please reset the board or power cycle it now...")

		if not scif.wait_for_keyword(
			RenesasSCIF.SCIF_DOWNLOAD_MODE,
			timeout=30.0,
			echo=True
		):
			raise Exception(
				"Failed to detect SCIF Download Mode. "
				"Please check:\n"
				"  1. Board is in correct boot mode (SCIF Download Mode)\n"
				"  2. Serial cable is properly connected\n"
				"  3. Serial port device is correct"
			)

		logger.info("✓ SCIF Download Mode detected")

		# Stage 2: Load Flash Writer
		logger.info("=" * 60)
		logger.info("Stage 2: Loading Flash Writer")
		logger.info("=" * 60)

		if "flash_writer" not in recovery_config["firmware"]:
			raise Exception("Flash Writer firmware not specified in configuration")

		flash_writer_path = recovery_config["firmware"]["flash_writer"]["path"]
		logger.info(f"Flash Writer: {flash_writer_path}")

		# Note: "please send !" is already displayed after SCIF Download Mode detection
		# The keyword match consumes it, so we can proceed directly to file transfer
		logger.info("ROM is ready for Flash Writer transfer...")

		# Send Flash Writer
		logger.info("Transferring Flash Writer to device...")
		if not scif.send_file(flash_writer_path, show_progress=True):
			raise Exception("Failed to transfer Flash Writer")

		logger.info("✓ Flash Writer transferred successfully")

		# Wait for Flash Writer initialization
		# Flash Writer outputs version info and prompt after loading
		logger.info("Waiting for Flash Writer initialization...")
		if not scif.wait_for_keyword(
			b"Flash writer for",
			timeout=30.0,
			echo=True
		):
			logger.warning("Flash Writer banner not detected, but continuing...")

		logger.info("✓ Flash Writer loaded successfully")

		# Wait for prompt
		if not scif.wait_for_keyword(RenesasSCIF.PROMPT, timeout=10.0, echo=True):
			logger.warning("Flash Writer prompt not detected after initialization")

		# Stage 3: UART Speed Up (Optional)
		if enable_speed_up:
			logger.info("=" * 60)
			logger.info("Stage 3: UART Speed Negotiation")
			logger.info("=" * 60)

			if scif.speed_up(921600):
				logger.info("✓ UART speed increased to 921600 bps")
			else:
				logger.warning(
					"UART speed up failed or not supported, "
					"continuing at 115200 bps"
				)

		# Stage 6: Auto-flash firmware (Optional)
		# Check both top-level and under firmware for firmware_to_flash
		firmware_to_flash = None
		if "firmware_to_flash" in recovery_config:
			firmware_to_flash = recovery_config["firmware_to_flash"]
		elif "firmware" in recovery_config and "firmware_to_flash" in recovery_config["firmware"]:
			firmware_to_flash = recovery_config["firmware"]["firmware_to_flash"]

		if firmware_to_flash is not None:
			logger.info("=" * 60)
			logger.info("Stage 4: Auto-flashing Firmware")
			logger.info("=" * 60)

			if not isinstance(firmware_to_flash, list):
				logger.warning("firmware_to_flash must be a list, skipping auto-flash")
			else:
				flash_firmware_list(scif, firmware_to_flash)

		else:
			logger.info("=" * 60)
			logger.info("Recovery Complete")
			logger.info("=" * 60)
			logger.info(
				"Flash Writer is now running on the device.\n"
				"You can use Flash Writer commands for firmware programming:\n"
				"  - XLS2: Write S-record to QSPI Flash\n"
				"  - XLS3: Write binary to QSPI Flash\n"
				"  - EM_WB: Write binary to eMMC\n"
				"  - H: Show help\n"
			)

		logger.info("=" * 60)
		logger.info("Renesas RZ recovery completed successfully!")
		logger.info("=" * 60)

	except KeyboardInterrupt:
		logger.warning("Recovery interrupted by user")
		raise

	except Exception as e:
		logger.error(f"Recovery failed: {e}")
		raise

	finally:
		# Note: We keep the serial port open for potential snagflash usage
		# or manual interaction. The SCIF object will be cleaned up when
		# the program exits.
		if scif.is_open():
			logger.debug("Serial port remains open for further operations")


def flash_firmware_list(scif: RenesasSCIF, firmware_list: list) -> None:
	"""
	Flash a list of firmware files to the device.

	Args:
		scif: SCIF connection object
		firmware_list: List of firmware configurations

	Raises:
		Exception: If flashing fails
	"""
	import os

	total_items = len(firmware_list)
	logger.info(f"Flashing {total_items} firmware file(s)...")

	for idx, firmware in enumerate(firmware_list, start=1):
		logger.info("")
		logger.info(f"[{idx}/{total_items}] Processing: {firmware.get('name', 'unnamed')}")
		logger.info("-" * 60)

		# Validate firmware configuration
		if "path" not in firmware:
			logger.error("Firmware path not specified, skipping")
			continue

		if "target" not in firmware:
			logger.error("Firmware target (qspi/emmc) not specified, skipping")
			continue

		file_path = firmware["path"]
		target = firmware["target"].lower()
		file_format = firmware.get("format", "bin").lower()

		# Check file exists
		if not os.path.isfile(file_path):
			logger.error(f"Firmware file not found: {file_path}")
			raise Exception(f"File not found: {file_path}")

		file_size = os.path.getsize(file_path)
		logger.info(f"File: {file_path} ({file_size} bytes)")
		logger.info(f"Target: {target.upper()}, Format: {file_format.upper()}")

		# Flash to QSPI
		if target == "qspi":
			flash_address = firmware.get("address", "0")
			# Remove 0x prefix if present
			if isinstance(flash_address, str) and flash_address.startswith("0x"):
				flash_address = flash_address[2:]
			elif isinstance(flash_address, int):
				flash_address = f"{flash_address:X}"

			if file_format == "srec":
				# Use XLS2 for S-record format
				program_address = firmware.get("program_address", "0")
				if isinstance(program_address, str) and program_address.startswith("0x"):
					program_address = program_address[2:]
				elif isinstance(program_address, int):
					program_address = f"{program_address:X}"

				logger.info(f"Using XLS2 command (S-record)")
				logger.info(f"Program address: 0x{program_address}")
				logger.info(f"Flash address: 0x{flash_address}")

				if not scif.execute_xls2_command(file_path, program_address, flash_address):
					raise Exception(f"Failed to flash {file_path} to QSPI")

			elif file_format == "bin":
				# Use XLS3 for binary format
				logger.info(f"Using XLS3 command (Binary)")
				logger.info(f"Flash address: 0x{flash_address}")

				if not scif.execute_xls3_command(file_path, file_size, flash_address):
					raise Exception(f"Failed to flash {file_path} to QSPI")

			else:
				logger.error(f"Unsupported format '{file_format}' for QSPI, skipping")
				continue

		# Flash to eMMC
		elif target == "emmc":
			partition = firmware.get("partition", 1)  # Default to boot partition 1
			start_sector = firmware.get("start_sector", "1")
			program_address = firmware.get("program_address", "0")

			# Format addresses
			if isinstance(start_sector, int):
				start_sector = f"{start_sector:X}"
			elif isinstance(start_sector, str) and start_sector.startswith("0x"):
				start_sector = start_sector[2:]

			if isinstance(program_address, str) and program_address.startswith("0x"):
				program_address = program_address[2:]
			elif isinstance(program_address, int):
				program_address = f"{program_address:X}"

			# Choose command based on file format
			if file_format == "srec":
				logger.info(f"Using EM_W command (eMMC S-record)")
				logger.info(f"Partition: {partition}, Start sector: 0x{start_sector}")
				logger.info(f"Program address: 0x{program_address}")
				if not scif.execute_em_w_command(file_path, partition, start_sector, program_address):
					raise Exception(f"Failed to flash {file_path} to eMMC")
			elif file_format == "bin":
				logger.info(f"Using EM_WB command (eMMC Binary)")
				logger.info(f"Partition: {partition}, Start sector: 0x{start_sector}")
				logger.info(f"Program address: 0x{program_address}")
				if not scif.execute_em_wb_command(file_path, partition, start_sector, program_address):
					raise Exception(f"Failed to flash {file_path} to eMMC")
			else:
				raise Exception(f"Unsupported file format '{file_format}' for eMMC target")

		else:
			logger.error(f"Unknown target '{target}', skipping")
			continue

		logger.info(f"✓ Successfully flashed: {firmware.get('name', file_path)}")

		# Wait between files to ensure Flash Writer is ready
		if idx < total_items:
			logger.info("Waiting for Flash Writer to be ready for next file...")
			time.sleep(3.0)
			# Send a help command to ensure Flash Writer is responsive
			scif.send_command("H")
			time.sleep(1.0)
			# Flush any residual output
			scif.flush_input()

	logger.info("")
	logger.info("=" * 60)
	logger.info(f"✓ All firmware files flashed successfully ({total_items}/{total_items})")
	logger.info("=" * 60)


def verify_config():
	"""
	Verify that required configuration is present.

	Raises:
		Exception: If required configuration is missing
	"""
	required_keys = ["soc_model", "serial_port", "firmware"]

	for key in required_keys:
		if key not in recovery_config:
			raise Exception(f"Required configuration key missing: {key}")

	if "flash_writer" not in recovery_config["firmware"]:
		raise Exception("Flash Writer firmware configuration missing")

	flash_writer = recovery_config["firmware"]["flash_writer"]
	if "path" not in flash_writer:
		raise Exception("Flash Writer path not specified")


# Perform configuration validation when module is loaded
try:
	verify_config()
except Exception as e:
	logger.warning(f"Configuration validation: {e}")
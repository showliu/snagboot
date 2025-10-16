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
Renesas RZ Flash Writer SCIF (Serial Communication Interface with FIFO) Protocol

This module communicate with the Renesas RZ Flash Writer command prompt via
SCIF Download Mode Renesas RZ series MPUs for recovery and firmware loading via
UART.

This protocol supports:
- Flash Writer loading to SRAM
- Speed up the UART baudrate (115200 -> 921600 bps)
- Memory read/write operations
- Command-based interaction with Flash Writer command prompt
"""

import serial
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger("snagrecover")


class RenesasSCIF:
	"""
	Renesas SCIF Download Mode Protocol Implementation

	This class handles UART communication with Renesas RZ series devices
	in SCIF Download Mode, supporting Flash Writer operations and speed
	negotiation.
	"""

	# SCIF Protocol Keywords
	SCIF_DOWNLOAD_MODE = b"SCIF Download mode"
	PROMPT = b">"
	PLEASE_SEND = b"please send ! ('.' & CR stop load)"
	COMPLETE = b"Complete!"
	SPEED_UP_PROMPT = b"Please change to 921.6Kbps baud rate"
	SPEED_DOWN_PROMPT = b"Please change to 115.2Kbps baud rate"

	# Supported baudrates
	SUPPORTED_SPEEDS = [115200, 921600]

	# Default timeouts
	DEFAULT_TIMEOUT = 3.0
	SPEED_CHANGE_TIMEOUT = 3.0
	FILE_TRANSFER_TIMEOUT = 5.0

	def __init__(
		self,
		port: str,
		baudrate: int = 115200,
		timeout: float = DEFAULT_TIMEOUT
	):
		"""
		Initialize SCIF connection.

		Args:
			port: Serial port device (e.g., /dev/ttyUSB0)
			baudrate: Initial baudrate (default: 115200)
			timeout: Default timeout in seconds (default: 5.0)
		"""
		self.port = port
		self.baudrate = baudrate
		self.timeout = timeout
		self.serial: Optional[serial.Serial] = None
		self._is_open = False

	def open(self) -> None:
		"""
		Open the serial port connection.

		Raises:
			serial.SerialException: If port cannot be opened
		"""
		logger.info(f"Opening SCIF connection on {self.port} at {self.baudrate} bps")

		try:
			self.serial = serial.Serial(
				port=self.port,
				baudrate=self.baudrate,
				timeout=self.timeout,
				parity=serial.PARITY_NONE,
				stopbits=serial.STOPBITS_ONE,
				bytesize=serial.EIGHTBITS,
				xonxoff=False,
				rtscts=False,
				dsrdtr=False
			)
			self._is_open = True
			logger.info("SCIF connection opened successfully")

		except serial.SerialException as e:
			logger.error(f"Failed to open serial port {self.port}: {e}")
			raise

	def close(self) -> None:
		"""Close the serial port connection."""
		if self.serial and self._is_open:
			self.serial.close()
			self._is_open = False
			logger.info("SCIF connection closed")

	def is_open(self) -> bool:
		"""Check if serial port is open."""
		return self._is_open and self.serial is not None and self.serial.is_open

	def wait_for_keyword(
		self,
		keyword: bytes,
		timeout: Optional[float] = None,
		echo: bool = True
	) -> bool:
		"""
		Wait for a specific keyword from the device.

		Args:
			keyword: Keyword bytes to wait for
			timeout: Timeout in seconds (default: use instance timeout)
			echo: Whether to echo received data to log (default: True)

		Returns:
			True if keyword found, False if timeout
		"""
		if timeout is None:
			timeout = self.timeout

		logger.debug(f"Waiting for keyword: {keyword[:30]}... (timeout: {timeout}s)")

		start_time = time.time()
		buffer = b""

		while (time.time() - start_time) < timeout:
			if self.serial.in_waiting > 0:
				data = self.serial.read(self.serial.in_waiting)
				buffer += data

				if echo:
					try:
						decoded = data.decode('utf-8', errors='ignore')
						if decoded.strip():
							logger.debug(f"RX: {decoded.strip()}")
					except Exception:
						pass

				if keyword in buffer:
					logger.debug(f"Found keyword: {keyword[:30]}")
					return True

			time.sleep(0.1)

		logger.warning(f"Timeout waiting for keyword: {keyword[:30]}")
		return False

	def send_command(self, command: str, wait_prompt: bool = False) -> bool:
		"""
		Send a command to the device.

		Args:
			command: Command string to send
			wait_prompt: Whether to wait for prompt after command (default: False)

		Returns:
			True if successful, False otherwise
		"""
		logger.debug(f"Sending command: {command}")

		try:
			cmd_bytes = f"{command}\r\n".encode('utf-8')
			self.serial.write(cmd_bytes)
			self.serial.flush()

			if wait_prompt:
				return self.wait_for_keyword(self.PROMPT, timeout=3.0)

			return True

		except Exception as e:
			logger.error(f"Failed to send command '{command}': {e}")
			return False

	def send_file(
		self,
		file_path: str,
		chunk_size: int = 4096,
		show_progress: bool = True
	) -> bool:
		"""
		Send a file to the device using SCIF protocol.

		Args:
			file_path: Path to file to send
			chunk_size: Size of each chunk in bytes (default: 4096)
			show_progress: Whether to log progress (default: True)

		Returns:
			True if successful, False otherwise
		"""
		logger.info(f"Sending file: {file_path}")

		try:
			with open(file_path, 'rb') as f:
				total_bytes = 0
				start_time = time.time()

				while True:
					chunk = f.read(chunk_size)
					if not chunk:
						break

					self.serial.write(chunk)
					total_bytes += len(chunk)

					if show_progress and total_bytes % (chunk_size * 10) == 0:
						elapsed = time.time() - start_time
						speed = total_bytes / elapsed if elapsed > 0 else 0
						logger.info(
							f"Transferred: {total_bytes} bytes "
							f"({speed:.0f} bytes/s)"
						)

			# Send end marker
			self.serial.write(b'.\r\n')
			self.serial.flush()

			elapsed = time.time() - start_time
			speed = total_bytes / elapsed if elapsed > 0 else 0
			logger.info(
				f"File transfer complete: {total_bytes} bytes in {elapsed:.2f}s "
				f"({speed:.0f} bytes/s)"
			)

			return True

		except FileNotFoundError:
			logger.error(f"File not found: {file_path}")
			return False
		except Exception as e:
			logger.error(f"File transfer failed: {e}")
			return False

	def speed_up(self, target_speed: int = 921600) -> bool:
		"""
		Perform UART speed negotiation to higher baudrate.

		Args:
			target_speed: Target baudrate (default: 921600)

		Returns:
			True if successful, False if failed (will revert to original speed)
		"""
		if target_speed not in self.SUPPORTED_SPEEDS:
			logger.error(f"Unsupported baudrate: {target_speed}")
			return False

		if target_speed == self.baudrate:
			logger.info(f"Already at target speed: {target_speed} bps")
			return True

		original_speed = self.baudrate
		logger.info(
			f"Initiating UART speed change: {original_speed} -> {target_speed} bps"
		)

		try:
			# Send speed up command
			self.send_command("SUP")

			# Wait for speed change notification
			if not self.wait_for_keyword(
				self.SPEED_UP_PROMPT,
				timeout=self.SPEED_CHANGE_TIMEOUT
			):
				logger.error("Device did not confirm speed change readiness")
				return False

			# Give device time to prepare
			logger.debug("Waiting for device to stabilize...")
			time.sleep(2.0)

			# Change host baudrate
			logger.debug(f"Changing host baudrate to {target_speed} bps")
			self.serial.baudrate = target_speed
			self.baudrate = target_speed

			# Brief delay after speed change
			time.sleep(0.5)

			# Test new speed with help command
			logger.debug("Testing new baudrate...")
			self.send_command("H")

			if self.wait_for_keyword(self.PROMPT, timeout=3.0):
				logger.info(
					f"Speed change successful: {original_speed} -> {target_speed} bps"
				)
				return True
			else:
				# Speed verification failed, revert
				logger.warning("Speed change verification failed")
				raise Exception("Verification failed")

		except Exception as e:
			logger.warning(f"Speed change failed, reverting to {original_speed} bps: {e}")
			self.serial.baudrate = original_speed
			self.baudrate = original_speed
			time.sleep(0.5)
			return False

	def read_response(self, timeout: Optional[float] = None) -> bytes:
		"""
		Read response from device until timeout.

		Args:
			timeout: Timeout in seconds (default: use instance timeout)

		Returns:
			Received bytes
		"""
		if timeout is None:
			timeout = self.timeout

		start_time = time.time()
		response = b""

		while (time.time() - start_time) < timeout:
			if self.serial.in_waiting > 0:
				response += self.serial.read(self.serial.in_waiting)
			time.sleep(0.1)

		return response

	def flush_input(self) -> None:
		"""Flush serial input buffer."""
		if self.serial:
			self.serial.reset_input_buffer()
			logger.debug("Input buffer flushed")

	def __enter__(self):
		"""Context manager entry."""
		self.open()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit."""
		self.close()
		return False

	def send_input(self, data: str, wait_for_echo: bool = True) -> bool:
		"""
		Send input data in response to a prompt.

		Args:
			data: Data to send
			wait_for_echo: Whether to wait for echo (default: True)

		Returns:
			True if successful, False otherwise
		"""
		try:
			input_bytes = f"{data}\r\n".encode('utf-8')
			self.serial.write(input_bytes)
			self.serial.flush()

			if wait_for_echo:
				time.sleep(0.1)

			return True

		except Exception as e:
			logger.error(f"Failed to send input '{data}': {e}")
			return False

	def execute_xls2_command(
		self,
		file_path: str,
		program_address: str,
		flash_address: str
	) -> bool:
		"""
		Execute XLS2 command to write S-record file to QSPI Flash.

		Args:
			file_path: Path to S-record file
			program_address: Program top address (hex string, e.g., "11E00")
			flash_address: QSPI save address (hex string, e.g., "0")

		Returns:
			True if successful, False otherwise
		"""
		logger.info(f"Executing XLS2 command for {file_path}")
		logger.info(f"Program address: 0x{program_address}, Flash address: 0x{flash_address}")

		try:
			# Send XLS2 command
			self.send_command("XLS2")

			# Wait for program address prompt and input
			if not self.wait_for_keyword(b"Program Top Address", timeout=5.0):
				logger.error("Did not receive program address prompt")
				return False

			# Give Flash Writer time to output full prompt
			time.sleep(0.5)

			# Send program address
			logger.debug(f"Sending program address: {program_address}")
			self.send_input(program_address)

			# Wait for flash address prompt
			if not self.wait_for_keyword(b"Qspi Save Address", timeout=5.0):
				logger.error("Did not receive flash address prompt")
				return False

			# Give Flash Writer time to output full prompt
			time.sleep(0.5)

			# Send flash address
			logger.debug(f"Sending flash address: {flash_address}")
			self.send_input(flash_address)

			# Wait for "please send" prompt
			if not self.wait_for_keyword(self.PLEASE_SEND, timeout=10.0):
				logger.error("Device not ready for file transfer")
				return False

			# Send S-record file
			logger.info(f"Transferring S-record file: {file_path}")
			if not self.send_file(file_path, show_progress=True):
				return False

			# After file transfer, check if clear/erase confirmation is needed
			logger.info("File transfer complete, checking for erase confirmation...")
			time.sleep(1.0)
			if not self.wait_for_keyword(b"Clear OK?(y/n)", timeout=10.0):
				logger.warning("Did not receive erase confirmation prompt, this may be normal for some operations")
			else:
				logger.info("Flash erase required, confirming...")
				self.send_input("y")
				# Wait for erase completion
				if not self.wait_for_keyword(b"Erase Completed", timeout=30.0):
					logger.warning("Erase completion not detected, continuing...")
				time.sleep(1.0)

			# Wait for save completion
			# Flash erase and programming can take a long time
			logger.info("Waiting for Flash programming to complete (this may take up to 1 minute)...")
			if not self.wait_for_keyword(b"SAVE", timeout=60.0):
				logger.warning("Save completion message not detected clearly, but continuing...")

			# Wait for prompt to confirm completion
			if not self.wait_for_keyword(self.PROMPT, timeout=10.0):
				logger.warning("Prompt not detected after save, but continuing...")

			logger.info("✓ XLS2 command completed successfully")
			return True

		except Exception as e:
			logger.error(f"XLS2 command failed: {e}")
			return False

	def execute_xls3_command(
		self,
		file_path: str,
		file_size: int,
		flash_address: str
	) -> bool:
		"""
		Execute XLS3 command to write binary file to QSPI Flash.

		Args:
			file_path: Path to binary file
			file_size: Size of binary file in bytes
			flash_address: QSPI save address (hex string, e.g., "0")

		Returns:
			True if successful, False otherwise
		"""
		logger.info(f"Executing XLS3 command for {file_path}")
		logger.info(f"File size: {file_size} bytes, Flash address: 0x{flash_address}")

		try:
			# Send XLS3 command
			self.send_command("XLS3")

			# Wait for program size prompt
			if not self.wait_for_keyword(b"Program size", timeout=5.0):
				logger.error("Did not receive program size prompt")
				return False

			# Give Flash Writer time to output full prompt
			time.sleep(0.5)

			# Send file size in hex
			size_hex = f"{file_size:X}"
			logger.debug(f"Sending program size: 0x{size_hex} ({file_size} bytes)")
			self.send_input(size_hex)

			# Wait for flash address prompt
			if not self.wait_for_keyword(b"Qspi Save Address", timeout=5.0):
				logger.error("Did not receive flash address prompt")
				return False

			# Give Flash Writer time to output full prompt
			time.sleep(0.5)

			# Send flash address
			logger.debug(f"Sending flash address: {flash_address}")
			self.send_input(flash_address)

			# Wait for "please send" prompt
			if not self.wait_for_keyword(b"please send ! (binary)", timeout=10.0):
				logger.error("Device not ready for file transfer")
				return False

			# Send binary file (no end marker for XLS3)
			logger.info(f"Transferring binary file: {file_path}")
			with open(file_path, 'rb') as f:
				data = f.read()
				self.serial.write(data)
				self.serial.flush()

			logger.info(f"Transferred {len(data)} bytes")

			# After file transfer, check if clear/erase confirmation is needed
			logger.info("File transfer complete, checking for erase confirmation...")
			time.sleep(1.0)
			if not self.wait_for_keyword(b"Clear OK?(y/n)", timeout=10.0):
				logger.warning("Did not receive erase confirmation prompt, this may be normal for some operations")
			else:
				logger.info("Flash erase required, confirming...")
				self.send_input("y")
				# Wait for erase completion
				if not self.wait_for_keyword(b"Erase Completed", timeout=60.0):
					logger.warning("Erase completion not detected, continuing...")
				time.sleep(1.0)

			# Wait for save completion
			# Flash erase and programming can take a long time
			logger.info("Waiting for Flash programming to complete (this may take up to 1 minute)...")
			if not self.wait_for_keyword(b"SAVE SPI-FLASH.", timeout=60.0):
				logger.warning("Save completion message not detected clearly, but continuing...")

			# Wait for prompt to confirm completion
			if not self.wait_for_keyword(self.PROMPT, timeout=10.0):
				logger.warning("Prompt not detected after save, but continuing...")

			logger.info("✓ XLS3 command completed successfully")
			return True

		except Exception as e:
			logger.error(f"XLS3 command failed: {e}")
			return False

	def execute_em_wb_command(
		self,
		file_path: str,
		partition: int,
		start_sector: str,
		program_address: str
	) -> bool:
		"""
		Execute EM_WB command to write binary file to eMMC.

		Args:
			file_path: Path to binary file
			partition: Partition number (0=User, 1=Boot1, 2=Boot2)
			start_sector: Start sector in hex (e.g., "1")
			program_address: Program start address in hex (e.g., "11E00")

		Returns:
			True if successful, False otherwise
		"""
		logger.info(f"Executing EM_WB command for {file_path}")
		logger.info(f"Partition: {partition}, Start sector: 0x{start_sector}, Address: 0x{program_address}")

		try:
			# Send EM_WB command
			self.send_command("EM_WB")

			# Wait for partition selection prompt (use shorter keyword to match Flash Writer output)
			if not self.wait_for_keyword(b"Select area", timeout=5.0):
				logger.error("Did not receive partition selection prompt")
				return False

			# Send partition number
			logger.debug(f"Selecting partition: {partition}")
			self.send_input(str(partition))

			# Wait for start address prompt
			if not self.wait_for_keyword(b"Please Input Start Address in sector", timeout=5.0):
				logger.error("Did not receive start address prompt")
				return False

			# Send start sector
			logger.debug(f"Sending start sector: {start_sector}")
			self.send_input(start_sector)

			# Wait for program address prompt
			if not self.wait_for_keyword(b"Please Input Program Start Address", timeout=5.0):
				logger.error("Did not receive program address prompt")
				return False

			# Send program address
			logger.debug(f"Sending program address: {program_address}")
			self.send_input(program_address)

			# Wait for "please send" prompt
			if not self.wait_for_keyword(self.PLEASE_SEND, timeout=10.0):
				logger.error("Device not ready for file transfer")
				return False

			# Send binary file
			logger.info(f"Transferring binary file: {file_path}")
			if not self.send_file(file_path, show_progress=True):
				return False

			# Wait for completion (use exact keyword from Flash Writer: "Complete!")
			if not self.wait_for_keyword(b"Complete!", timeout=30.0):
				logger.error("eMMC write completion not received")
				return False

			# Wait for prompt
			if not self.wait_for_keyword(self.PROMPT, timeout=5.0):
				logger.warning("Prompt not detected after save")

			logger.info("✓ EM_WB command completed successfully")
			return True

		except Exception as e:
			logger.error(f"EM_WB command failed: {e}")
			return False

	def execute_em_w_command(
		self,
		file_path: str,
		partition: int,
		start_sector: str,
		program_address: str
	) -> bool:
		"""
		Execute EM_W command to write S-record file to eMMC.

		This follows the exact keyword sequence from rzflash-tool.sh emmc mode:
		1. Send EM_W command, wait for "Select area"
		2. Send partition number, wait for "Please Input Start Address in sector"
		3. Send start sector, wait for "Please Input Program Start Address"
		4. Send program address, wait for "please send !"
		5. Transfer file, wait for "Complete!"

		Args:
			file_path: Path to S-record file
			partition: Partition number (0=User, 1=Boot1, 2=Boot2)
			start_sector: Start sector in hex (e.g., "1")
			program_address: Program start address in hex (e.g., "11E00")

		Returns:
			True if successful, False otherwise
		"""
		logger.info(f"Executing EM_W command for {file_path}")
		logger.info(f"Partition: {partition}, Start sector: 0x{start_sector}, Address: 0x{program_address}")

		try:
			# Step 1: Send EM_W command, wait for "Select area"
			self.send_command("EM_W")

			# Step 2: Wait for partition selection prompt (use shorter keyword)
			if not self.wait_for_keyword(b"Select area", timeout=5.0):
				logger.error("Did not receive partition selection prompt")
				return False

			# Send partition number
			logger.debug(f"Selecting partition: {partition}")
			self.send_input(str(partition))

			# Step 3: Wait for start address prompt
			if not self.wait_for_keyword(b"Please Input Start Address in sector", timeout=5.0):
				logger.error("Did not receive start address prompt")
				return False

			# Send start sector
			logger.debug(f"Sending start sector: {start_sector}")
			self.send_input(start_sector)

			# Step 4: Wait for program address prompt
			if not self.wait_for_keyword(b"Please Input Program Start Address", timeout=5.0):
				logger.error("Did not receive program address prompt")
				return False

			# Send program address
			logger.debug(f"Sending program address: {program_address}")
			self.send_input(program_address)

			# Step 5: Wait for "please send" prompt
			if not self.wait_for_keyword(self.PLEASE_SEND, timeout=10.0):
				logger.error("Device not ready for file transfer")
				return False

			# Step 6: Send S-record file
			logger.info(f"Transferring S-record file: {file_path}")
			if not self.send_file(file_path, show_progress=True):
				return False

			# Step 7: Wait for completion (use exact keyword from Flash Writer)
			if not self.wait_for_keyword(b"Complete!", timeout=30.0):
				logger.error("eMMC write completion not received")
				return False

			# Wait for prompt to return
			if not self.wait_for_keyword(self.PROMPT, timeout=5.0):
				logger.warning("Prompt not detected after eMMC write")

			logger.info("✓ EM_W command completed successfully")
			return True

		except Exception as e:
			logger.error(f"EM_W command failed: {e}")
			return False
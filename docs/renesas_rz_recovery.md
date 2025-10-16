# Renesas RZ Series MPU Recovery Guide

This guide explains how to use snagboot to recover Renesas RZ series MPUs via SCIF Download Mode.

## Supported Devices

Currently supported Renesas RZ series SoCs:

- **RZ/G2L** - Initial target platform (tested)
- **RZ/G Family** - Planned support (untested)
- **RZ/V Family** - Planned support (untested)

Additional RZ series devices can be added following the same recovery flow.

## Prerequisites

### Hardware Requirements

1. **Renesas RZ Evaluation Board** (e.g., RZ/G2L SMARC EVK)
2. **USB-to-UART Converter** (e.g., CP2102, FT232)
3. **Serial Cable** connecting board's debug UART to USB converter
4. **Power Supply** for the board

### Software Requirements

- **Snagboot** with Renesas RZ support
- **Flash Writer** binary for your specific RZ device
  - Download from Renesas website or build from source
  - Example: `Flash_Writer_SCIF_RZG2L_SMARC_DDR4_2GB.mot`


### Boot Mode Configuration

Configure the board for **SCIF Download Mode**:

For RZ/G2L SMARC:
- Set boot mode switches to SCIF Download Mode
- Refer to board documentation for exact switch settings
- Typically: SW11[1:4] = OFF-ON-ON-OFF (check your board manual)

## Basic Recovery

### Quick Start

1. **Connect Hardware**
   ```bash
   # Find your serial port
   ls /dev/ttyUSB*
   # Should show /dev/ttyUSB0 or similar
   ```

2. **Prepare Firmware Configuration**
   ```yaml
   # rzg2l-config.yaml
   flash_writer:
       path: Flash_Writer_SCIF_RZG2L_SMARC_DDR4_2GB.mot
   ```

3. **Run Recovery**
   ```bash
   snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
     -f rzg2l-config.yaml
   ```

4. **Power On Board**
   - After running snagrecover, power on or reset the board
   - Snagboot will detect SCIF Download Mode and load Flash Writer

### Using Template

Snagboot provides a template configuration:

```bash
# List available templates
snagrecover --list-socs | grep rzg2l

# Get template
snagrecover -t rzg2l-smarc > my-rzg2l-config.yaml

# Edit paths in my-rzg2l-config.yaml
vim my-rzg2l-config.yaml

# Run recovery
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  -f my-rzg2l-config.yaml
```

## Advanced Usage
### UART Speed Negotiation

By default, snagboot attempts to increase UART speed from 115200 to 921600 bps for faster transfers.

```bash
# Enable speed up (default)
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  --enable-speed-up \
  -f rzg2l-config.yaml

# Disable speed up (if experiencing issues)
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  --no-speed-up \
  -f rzg2l-config.yaml
```

### Inline Firmware Configuration

Instead of YAML file, use inline Python dict:

```bash
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  -F "{'flash_writer': {'path': 'Flash_Writer.mot'}}"
```

## Recovery Flow

The Renesas RZ recovery follows these stages:

### Stage 1: SCIF Download Mode Detection
- Snagboot waits for "SCIF Download mode" message
- Power on or reset the board when prompted
- Timeout: 30 seconds

### Stage 2: Flash Writer Loading
- Flash Writer binary is transferred to SRAM via UART
- Transfer includes progress reporting
- DDR initialization happens automatically in Flash Writer

### Stage 3: UART Speed Up (Optional)
- Negotiates speed increase to 921600 bps
- Falls back to 115200 if negotiation fails
- Can be disabled with `--no-speed-up`

## Automatic Firmware Flashing

Snagboot can automatically flash firmware to QSPI or eMMC after loading Flash Writer.

### Configuration Example

```yaml
# rzg2l-autoflash.yaml
flash_writer:
    path: Flash_Writer_SCIF_RZG2L_SMARC_DDR4_2GB.mot

firmware_to_flash:
    # BL2 to QSPI Flash (S-record format)
    - name: bl2
      path: bl2_bp-rzg2l.srec
      target: qspi
      format: srec
      address: 0x00000000
      program_address: 0x11E00

    # FIP to QSPI Flash (S-record format)
    - name: fip
      path: fip-rzg2l.srec
      target: qspi
      format: srec
      address: 0x0001D200
      program_address: 0x00000000

    # Bootloader to eMMC (binary format)
    - name: bootloader
      path: bl2.bin
      target: emmc
      format: srec
      partition: 1
      start_sector: 0x1
      program_address: 0x11E00

    # Bootloader to eMMC (binary format)
    - name: bootloader
      path: bl2.bin
      target: emmc
      format: bin
      partition: 1
      start_sector: 0x1
      program_address: 0x11E00
```

### Usage

```bash
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  -f rzg2l-autoflash.yaml
```

### Configuration Parameters

#### Common Parameters
- **name**: Descriptive name for logging
- **path**: Path to firmware file (relative or absolute)
- **target**: `qspi` or `emmc`
- **format**: `srec` (S-record) or `bin` (binary)

#### QSPI Flash Parameters
- **address**: Flash save address in hex (e.g., `0x0` or `"0x1D200"`)
- **program_address**: Program top address for S-record files (required for `srec` format)

#### eMMC Parameters
- **partition**: Partition number
  - `0`: User data partition
  - `1`: Boot partition 1
  - `2`: Boot partition 2
- **start_sector**: Start sector in hex (e.g., `0x1`)
- **program_address**: Program start address in hex

### Flash Writer Commands Reference

The automatic flashing feature uses these Flash Writer commands(ex RZ/G2L SMARC EVK board):

#### XLS2 - Write S-record to QSPI Flash
```
> XLS2
Please Input Program Top Address: H'11E00
Please Input Qspi Save Address: H'0
please send ! ('.' & CR stop load)
[S-record data transfer]
SAVE SPI-FLASH.......
```

#### XLS3 - Write Binary to QSPI Flash
```
> XLS3
Please Input Program size: H'A000
Please Input Qspi Save Address: H'100000
please send ! (binary)
[Binary data transfer]
```
#### EM_W - Write Binary to eMMC
```
> EM_W
Select area(0-2)> 1
Please Input Start Address in sector: 1
Please Input Program Start Address: 11E00
please send ! ('.' & CR stop load)
[Binary data transfer]
EM_W Complete!
```

#### EM_WB - Write Binary to eMMC
```
> EM_WB
Select area(0-2)> 1
Please Input Start Address in sector: 1
Please Input Program Start Address: 11E00
please send ! ('.' & CR stop load)
[Binary data transfer]
EM_WB Complete!
```


### Performance Tips

1. **Use UART speed negotiation** (enabled by default)
   - 115200 bps: ~25 seconds for 2MB Flash Writer
   - 921600 bps: ~3 seconds for 2MB Flash Writer

2. **Binary format is faster than S-record**
   - Binary: direct transfer
   - S-record: ASCII encoding overhead

3. **Flash multiple files in one session**
   - Flash Writer stays loaded
   - No need to repeat recovery steps

## Troubleshooting

### Board Not Detected

**Symptom:** "Failed to detect SCIF Download Mode"

**Solutions:**
1. Check boot mode switches (must be in SCIF Download Mode)
2. Verify serial cable connection
3. Ensure correct serial port device
4. Try different USB port

### Serial Port Permission

**Symptom:** "Permission denied" on /dev/ttyUSB0

**Solution:**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER
# Log out and back in

# Or use sudo (not recommended)
sudo snagrecover -s rzg2l --serial-port /dev/ttyUSB0 ...
```

### Speed Negotiation Fails

**Symptom:** "Speed change verification failed, reverting to 115200 bps"

**Solutions:**
1. This is usually harmless - recovery continues at 115200
2. Check USB-UART converter quality
3. Try shorter or better shielded cable
4. Use `--no-speed-up` to disable negotiation

### Transfer Timeout

**Symptom:** File transfer times out

**Solutions:**
1. Verify file path is correct
2. Check file is not corrupted
3. Increase timeout in recovery code (development)
4. Try disabling speed up

### Flash Writer Doesn't Respond

**Symptom:** No prompt after Flash Writer loads

**Solutions:**
1. DDR initialization may be failing
2. Check Flash Writer binary matches your board variant
3. Verify board DDR configuration
4. Try different Flash Writer version

### Firmware Flashing Fails

**Symptom:** "Failed to flash [filename] to QSPI/eMMC"

**Solutions:**
1. **File not found**
   - Verify firmware file path is correct (relative or absolute)
   - Check file exists: `ls -l path/to/firmware.bin`

2. **Flash erase timeout**
   - First-time erase can take up to 120 seconds
   - Wait for "Erase Completed" message
   - If persistent, Flash may be defective

3. **Address conflicts**
   - Check addresses don't overlap with existing data
   - Verify address format (hex string or integer)
   - Use Flash Writer manual for recommended addresses

4. **Format mismatch**
   - S-record files must use `format: srec`
   - Binary files must use `format: bin`

5. **Wrong partition for eMMC**
   - Boot partition 1: `partition: 1`
   - Boot partition 2: `partition: 2`
   - User partition: `partition: 0`

### Configuration Errors

**Symptom:** "firmware_to_flash must be a list"

**Solution:** Ensure YAML syntax is correct with list format:
```yaml
firmware_to_flash:
    - name: item1    # Note the dash!
      path: ...
    - name: item2
      path: ...
```

## Flash Writer Commands

After successful recovery, Flash Writer provides commands for firmware programming:

```
> H              # Show help
> XLS            # Read QSPI Flash
> XCS            # Erase QSPI Flash
> EM_W           # Write to eMMC
> EM_DCID        # Read eMMC device ID
> SUP            # Speed up UART to 921600
> SDP            # Speed down UART to 115200
```

Refer to Renesas Flash Writer github repository for complete command reference.

```

## Performance

Typical recovery times (RZ/G2L with 2MB Flash Writer):

- At 115200 bps: ~25 seconds for Flash Writer transfer
- At 921600 bps: ~3 seconds for Flash Writer transfer
- Total recovery (with speed up): ~30-40 seconds
- Total recovery (without speed up): ~50-60 seconds

## Examples

### Example 1: Basic Flash Writer Load

```bash
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  -F "{'flash_writer': {'path': '/path/to/Flash_Writer.mot'}}"
```

### Example 2: Recovery Without Speed Up

```bash
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  --no-speed-up \
  --baudrate 115200 \
  -f rzg2l-config.yaml
```

## Logging

Enable detailed logging for debugging:

```bash
snagrecover -s rzg2l --serial-port /dev/ttyUSB0 \
  --loglevel debug \
  --logfile rzg2l-recovery.log \
  -f rzg2l-config.yaml
```

Log file will contain:
- All UART communication
- Timing information
- Error details
- Recovery stage progression

## Future Enhancements(TODO list)

Planned improvements for Renesas RZ support:

- Testing with more RZ series devices (RZ/G, RZ/V)
- snagflash integration for complete workflow
- Automated board detection
- snagfactory integration for product manufactureing
- **U-Boot** binary support for firmware update by DFU or Fastboot mode
- Flash Writer or SoC side function enhancement
- Auto enable the boot from EMMC CSD register setup if recover to EMMC device
- Windows support

## Resources

- [Renesas RZ Family 32&64 MPUs Product Page](https://www.renesas.com/en/products/microcontrollers-microprocessors/rz-mpus)
- [RZ/G2L Flash Writer github repository](https://github.com/renesas-rz/rzg2_flash_writer/tree/rz_g2l)
- [RZ/G2L Module Board User's Manual: Hardware](https://www.renesas.com/en/document/mat/rzg2l-rzv2l-smarc-module-board-users-manual-hardware?r=1518686)
- [Snagboot Documentation](https://github.com/bootlin/snagboot/tree/main/docs)

## Support

For issues or questions:
- Open issue on snagboot GitHub
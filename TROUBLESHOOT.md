# ESP32-CAM + ESP32-CAM-MB on Ubuntu 24.04 — Complete Troubleshooting Guide

This document records the complete setup, problems encountered, symptoms, fixes, verification commands, and the recommended step-by-step workflow for programming and testing an AI-Thinker ESP32-CAM using an ESP32-CAM-MB USB programmer on Ubuntu 24.04.

---

## 1. Hardware/software setup

### Hardware

- AI-Thinker ESP32-CAM (assumed camera board model used in this session)
- ESP32-CAM-MB Micro-USB programming/download board
- Micro-USB cable
- Ubuntu laptop

### Software

- Ubuntu 24.04.x LTS (`noble`)
- Arduino IDE 2.3.10 AppImage
- ESP32 board package by Espressif Systems
- Python 3 with `pyserial` available for optional serial testing

### Expected connection

```text
Laptop
  │
  │ USB data cable
  ▼
ESP32-CAM-MB
  │
  │ board-to-board connection
  ▼
AI-Thinker ESP32-CAM
```

The ESP32-CAM-MB contains a USB-to-serial converter. In this session the converter was identified as a CH340/CH341-family device with USB ID:

```text
1a86:7523
```

Ubuntu loaded the kernel driver:

```text
ch341
```

and created:

```text
/dev/ttyUSB0
```

---

# 2. Arduino IDE installation on Ubuntu

## 2.1 Recommended location for the AppImage

A convenient location is:

```text
~/Applications/
```

Create it with:

```bash
mkdir -p ~/Applications
```

Move the downloaded AppImage into it:

```bash
mv ~/Downloads/arduino-ide_2.3.10_Linux_64bit.AppImage ~/Applications/
```

Make it executable:

```bash
chmod +x ~/Applications/arduino-ide_2.3.10_Linux_64bit.AppImage
```

Run it with:

```bash
~/Applications/arduino-ide_2.3.10_Linux_64bit.AppImage
```

Do not use `sudo` to run Arduino IDE.

---

# 3. Problem: `libfuse.so.2` missing

## Symptom

The AppImage initially failed with:

```text
dlopen(): error loading libfuse.so.2
AppImages require FUSE to run.
```

## Cause

The AppImage expected the FUSE 2 compatibility library. Ubuntu 24.04 uses the newer package naming/transition and selected `libfuse2t64` when installing `libfuse2`.

## Fix

First update package metadata:

```bash
sudo apt update
```

Then install:

```bash
sudo apt install libfuse2
```

On Ubuntu 24.04 this selected:

```text
libfuse2t64
```

After installation, try:

```bash
~/Applications/arduino-ide_2.3.10_Linux_64bit.AppImage
```

### Verification

The FUSE error should disappear. If a different Arduino/Electron error appears, continue troubleshooting that new error instead of reinstalling FUSE.

---

# 4. Problem: Electron/Chromium `chrome-sandbox` / SUID sandbox error

## Symptom

After FUSE was fixed, Arduino IDE failed with:

```text
FATAL:setuid_sandbox_host.cc(158)
The SUID sandbox helper binary was found, but is not configured correctly.
You need to make sure that .../chrome-sandbox is owned by root and has mode 4755.
```

An example path from the extracted AppImage was:

```text
/home/gk/Applications/squashfs-root/chrome-sandbox
```

## Recommended workaround options

### Option A — launch with `--no-sandbox`

A quick workaround is:

```bash
~/Applications/arduino-ide_2.3.10_Linux_64bit.AppImage --no-sandbox
```

This reduces Chromium sandboxing, so it is best treated as a workaround rather than the ideal long-term configuration.

### Option B — extract the AppImage and fix `chrome-sandbox`

Extract:

```bash
cd ~/Applications
./arduino-ide_2.3.10_Linux_64bit.AppImage --appimage-extract
```

This creates:

```text
~/Applications/squashfs-root/
```

Run:

```bash
~/Applications/squashfs-root/AppRun
```

If it reports the `chrome-sandbox` permission problem, fix only that helper:

```bash
cd ~/Applications/squashfs-root
sudo chown root:root chrome-sandbox
sudo chmod 4755 chrome-sandbox
```

Verify:

```bash
ls -l chrome-sandbox
```

Expected permissions should include the SUID bit and root ownership, for example:

```text
-rwsr-xr-x 1 root root ... chrome-sandbox
```

Do **not** run the entire Arduino IDE as root.

---

# 5. Install ESP32 board support

In Arduino IDE:

1. Open **File → Preferences**.
2. Find **Additional Boards Manager URLs**.
3. Add the official Espressif Arduino-ESP32 package URL:

```text
https://espressif.github.io/arduino-esp32/package_esp32_index.json
```

Then:

1. Open **Tools → Board → Boards Manager**.
2. Search for `esp32`.
3. Install **esp32 by Espressif Systems**.

---

# 6. Correct board selection for the AI-Thinker ESP32-CAM

In Arduino IDE select:

```text
Tools → Board → esp32 → AI Thinker ESP32-CAM
```

This board selection was confirmed to be correct during the session.

A typical initial configuration used in the session was:

```text
Board:            AI Thinker ESP32-CAM
Upload Speed:     115200
Flash Frequency:  80MHz
Flash Mode:       QIO
Port:             /dev/ttyUSB0
```

The exact partition scheme may be changed later depending on the sketch. Do not assume that every camera project requires the same partition scheme.

---

# 7. Problem: Port menu empty in Arduino IDE

## Symptom

The **Tools → Port** menu was empty even though the ESP32-CAM board was selected correctly.

## Diagnosis

Board selection and serial-port detection are separate things.

Selecting:

```text
AI Thinker ESP32-CAM
```

does not create a serial port. Ubuntu must first detect the USB-to-serial converter on the ESP32-CAM-MB.

## Useful commands

Check USB devices:

```bash
lsusb
```

Check serial devices:

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Initially there was no `/dev/ttyUSB0` and `lsusb` did not show the programmer's USB serial converter.

---

# 8. How to identify a working ESP32-CAM-MB connection

When the programmer was correctly detected, `lsusb` showed:

```text
Bus ... Device ...: ID 1a86:7523 QinHeng Electronics CH340 serial converter
```

The kernel then reported:

```text
ch341-uart converter detected
ch341-uart converter now attached to ttyUSB0
```

and:

```text
/dev/ttyUSB0
```

appeared.

### This proves

- USB data connection exists.
- The programmer's USB serial chip is detected.
- Ubuntu has the correct serial driver.
- `/dev/ttyUSB0` is the serial device Arduino IDE should use.

No additional CH340/CH341 driver installation was required in this session.

---

# 9. Problem: uncertainty about whether the Micro-USB cable is data-capable

A charge-only cable can power a board while providing no USB data connection.

There was initially no separate phone/device available to test the cable.

## Best tests

### Test with the ESP32-CAM-MB itself

Run:

```bash
sudo dmesg -w
```

Then plug the programmer in.

A data-capable cable plus a working programmer should produce USB messages and eventually `/dev/ttyUSB0`.

### Test a different known-good cable

A known data-capable Micro-USB cable from an old phone, power bank, USB device, Arduino-related equipment, or other data device is useful.

The cable's physical appearance alone is not a reliable way to determine whether it supports data.

### Important distinction

A board LED turning on only proves that power is reaching the board. It does **not** prove that USB data lines are working.

---

# 10. Problem: serial-port permission denied / `dialout`

## Symptom

The serial device had permissions similar to:

```text
crw-rw---- 1 root dialout ... /dev/ttyUSB0
```

but the user was not in the `dialout` group.

The `groups` command initially showed:

```text
gk adm cdrom sudo dip plugdev users lpadmin ollama
```

There was no `dialout`.

## Correct fix

Run:

```bash
sudo usermod -aG dialout $USER
```

Then **log out and log back in**, or reboot:

```bash
reboot
```

Verify:

```bash
groups
```

`dialout` should now appear.

The correct approach is to add the user to `dialout`; do not permanently change `/dev/ttyUSB0` to broad permissions and do not run Arduino IDE as root.

---

# 11. Problem: `ttyUSB0` is busy

## Symptom

When trying to open the port with Python:

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

the error was:

```text
[Errno 16] Device or resource busy: '/dev/ttyUSB0'
```

## Cause

Another program was already using the serial port, most commonly Arduino IDE's Serial Monitor or an upload operation.

## Fix

Close Arduino IDE's **Serial Monitor** before starting `miniterm`, or close `miniterm` before starting Arduino's Serial Monitor.

Only one process should normally have the serial port open at a time.

## Identify the process using the port

```bash
sudo lsof /dev/ttyUSB0
```

or:

```bash
sudo fuser -v /dev/ttyUSB0
```

Do not kill processes blindly. First identify which application owns the port.

---

# 12. Problem: `/dev/ttyUSB0` sometimes disappears

This was one of the most important issues encountered.

The sequence was:

1. `/dev/ttyUSB0` existed.
2. Serial communication worked.
3. At other times `/dev/ttyUSB0` disappeared.
4. `lsusb` also stopped showing the CH340 device.
5. Reconnecting the ESP32-CAM-MB caused it to reappear.

## Important interpretation

If both of these disappear:

```text
1a86:7523 CH340/CH341 USB serial converter
/dev/ttyUSB0
```

this is **not an Arduino board-selection problem** and usually not a normal permissions problem. The USB device itself is dropping off the system.

Potential causes include:

- Loose Micro-USB connection
- Bad or marginal USB cable
- USB port issue
- ESP32-CAM-MB connection issue
- USB power/connection instability
- Hardware fault on the programmer

## Recovery sequence

Unplug the ESP32-CAM-MB.

Wait a few seconds.

Plug it back in.

Then check:

```bash
lsusb
ls /dev/ttyUSB*
```

A healthy state should show the CH340/CH341 and `/dev/ttyUSB0`.

---

# 13. Best Linux USB diagnostic procedure

Use this whenever the port disappears.

Start with:

```bash
sudo dmesg -w
```

Then reconnect the ESP32-CAM-MB.

A healthy connection may show messages similar to:

```text
usb ...: new full-speed USB device
usb ...: New USB device found, idVendor=1a86, idProduct=7523
Product: USB Serial
ch341 ...: ch341-uart converter detected
usb ...: ch341-uart converter now attached to ttyUSB0
```

If the device is unstable you may instead see a connect sequence followed by a disconnect sequence.

The exact kernel messages are more useful than repeatedly changing Arduino IDE settings.

Stop `dmesg -w` with:

```text
Ctrl+C
```

---

# 14. First functional test: WiFiScan

Do not jump straight to the camera web server when setting up a new board. First prove the MCU and serial link work.

In Arduino IDE open:

```text
File → Examples → WiFi → WiFiScan
```

Select:

```text
Board: AI Thinker ESP32-CAM
Port: /dev/ttyUSB0
```

Click **Upload**.

---

# 15. Upload completed successfully

A successful upload in this session ended with messages similar to:

```text
Writing at ... 100.0%
Wrote 889888 bytes ...
Verifying written data...
Hash of data verified.
Hard resetting via RTS pin...
```

The important line is:

```text
Hash of data verified.
```

This means the firmware was successfully written and verified.

The line:

```text
Hard resetting via RTS pin...
```

is normally the automatic reset Arduino performs after a successful upload. It is **not by itself an error** and does not mean the board is stuck in a reboot loop.

---

# 16. Do I need to press RESET after upload?

Usually Arduino/esptool automatically resets the board at the end of the upload.

For serial debugging, pressing the ESP32-CAM-MB's **EN/RESET** button once is reasonable after opening the Serial Monitor.

Do not continuously press RESET.

Do not assume every `Hard resetting via RTS pin...` message is a fault.

---

# 17. WiFiScan succeeded

The WiFiScan output eventually showed:

```text
Scan start
Scan done
3 networks found
Nr | SSID | RSSI | CH | Encryption
...
```

This was a successful functional test.

It proved:

- Firmware upload works.
- ESP32 boot works.
- Serial output works.
- ESP32 Wi-Fi hardware works.
- The board can scan and detect nearby networks.

---

# 18. Important misconception: WiFiScan does NOT create a hotspot

A successful WiFiScan sketch does **not** make the ESP32 appear as a new Wi-Fi network on a phone.

WiFiScan only scans for existing access points.

Therefore, not seeing the ESP32 in the phone's Wi-Fi network list after running WiFiScan is normal.

For a camera web server, the ESP32 normally joins an existing Wi-Fi network and receives an IP address from that network.

---

# 19. Camera test: CameraWebServer

After WiFiScan works, move to the camera example.

Open:

```text
File → Examples → ESP32 → Camera → CameraWebServer
```

For an AI-Thinker ESP32-CAM, ensure the correct camera model is selected:

```cpp
#define CAMERA_MODEL_AI_THINKER
```

Make sure other camera model definitions are not also enabled.

Set your Wi-Fi credentials in the sketch:

```cpp
const char *ssid = "YOUR_WIFI_NAME";
const char *password = "YOUR_WIFI_PASSWORD";
```

Do not share your Wi-Fi password in troubleshooting messages.

---

# 20. CameraWebServer connection model

The expected network arrangement is:

```text
                 Wi-Fi router/access point
                  /         |         \
                 /          |          \
                ▼           ▼           ▼
        ESP32-CAM       Laptop         Phone
        192.168.x.x
```

The ESP32-CAM usually connects to the existing Wi-Fi network.

The phone does **not** need to see an ESP32 hotspot.

The laptop/phone should normally be on the same LAN/Wi-Fi network as the ESP32-CAM.

---

# 21. After CameraWebServer upload

Close the Serial Monitor before uploading if it is holding `/dev/ttyUSB0`.

Upload the CameraWebServer sketch.

After successful upload, open Serial Monitor at:

```text
115200 baud
```

The sketch should eventually print a URL similar to:

```text
Camera Ready! Use 'http://192.168.x.x' to connect
```

Use the exact URL printed by your board.

---

# 22. Problem: confusion about `<ESP32-IP>` in `ping`

This command is only an example placeholder:

```bash
ping <ESP32-IP>
```

Do **not** type the angle brackets.

If the ESP32 reports:

```text
http://192.168.1.123
```

run:

```bash
ping 192.168.1.123
```

Similarly, open:

```text
http://192.168.1.123
```

in Firefox or another browser.

---

# 23. What to expect from the camera webpage

When the URL works, the CameraWebServer page should provide camera controls and a stream option.

Use the stream controls to start the camera feed.

If the page loads but the video does not, capture the Serial Monitor output and check whether the camera initialized successfully.

---

# 24. Problem: upload failed because `/dev/ttyUSB0` disappeared

An important failure in the session looked like:

```text
Sketch uses 1059629 bytes (33%) of program storage space.
Global variables use 69528 bytes (21%) of dynamic memory, leaving 258152 bytes for local variables.
esptool v5.3.1
Serial port /dev/ttyUSB0:

A fatal error occurred: Could not open /dev/ttyUSB0, the port is busy or doesn't exist.
([Errno 2] could not open port /dev/ttyUSB0: [Errno 2] No such file or directory: '/dev/ttyUSB0')

Failed uploading: uploading error: exit status 2
```

## What this means

The sketch compiled successfully. The failure happened **before the new firmware was uploaded**, because the selected serial port was no longer present.

The key clue is:

```text
Errno 2: No such file or directory
```

This is different from `Errno 16`.

### Errno 2

```text
No such file or directory
```

Usually means `/dev/ttyUSB0` disappeared.

### Errno 16

```text
Device or resource busy
```

Usually means another process already owns the serial port.

---

# 25. Recovery from an upload failure caused by missing `/dev/ttyUSB0`

First check:

```bash
lsusb
```

Look for:

```text
1a86:7523 QinHeng Electronics CH340 serial converter
```

Then:

```bash
ls /dev/ttyUSB*
```

Look for:

```text
/dev/ttyUSB0
```

If the USB device is missing, unplug/reconnect the ESP32-CAM-MB and repeat the checks.

If it keeps disappearing, use:

```bash
sudo dmesg -w
```

while reconnecting it.

---

# 26. Problem: Serial Monitor and upload fighting over the same port

Do not upload while another process is actively using `/dev/ttyUSB0`.

Recommended sequence:

```text
Camera/serial test
     ↓
Close Serial Monitor
     ↓
Check /dev/ttyUSB0
     ↓
Upload
     ↓
Upload completes
     ↓
Reopen Serial Monitor
```

For command-line serial testing:

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

close miniterm before using Arduino IDE's Serial Monitor or uploading.

---

# 27. Optional Python serial monitor

Use the normal Ubuntu terminal, not an Arduino IDE editor/terminal.

Command:

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

If `pyserial` is unavailable:

```bash
python3 -m pip install pyserial
```

A successful connection looks similar to:

```text
--- Miniterm on /dev/ttyUSB0  115200,8,N,1 ---
```

Then press EN/RESET once to observe boot messages.

Exit miniterm using its displayed exit shortcut, normally:

```text
Ctrl+]
```

### Important

If Arduino Serial Monitor is open, miniterm may report:

```text
Device or resource busy
```

Close the other serial application first.

---

# 28. If there is no serial output after reset

Do not immediately assume the sketch failed.

Check in this order:

1. Is `/dev/ttyUSB0` present?
2. Is the CH340/CH341 present in `lsusb`?
3. Is another application holding the port?
4. Is Serial Monitor set to 115200 baud?
5. Press EN/RESET once.
6. If still blank, use `miniterm` after closing Arduino Serial Monitor.
7. Check `dmesg` for USB disconnects or resets.

---

# 29. If the board repeatedly resets

There are two very different situations.

### Normal post-upload reset

```text
Hard resetting via RTS pin...
```

This is normally expected after upload.

### Actual reboot loop

Serial Monitor may repeatedly show ESP32 boot/reset information such as:

```text
rst:0x...
```

or a power-related message such as:

```text
Brownout detector was triggered
```

If this happens, save the complete boot log before changing settings.

A brownout message points toward a power problem rather than a programming problem.

---

# 30. USB troubleshooting decision tree

```text
Is ESP32-CAM-MB connected?
        │
        ▼
      lsusb
        │
        ├── CH340/CH341 1a86:7523 present
        │        │
        │        ▼
        │   ls /dev/ttyUSB*
        │        │
        │        ├── /dev/ttyUSB0 present
        │        │       │
        │        │       ├── Port busy?
        │        │       │       └── close Serial Monitor/miniterm
        │        │       │
        │        │       └── Port usable
        │        │
        │        └── no ttyUSB0
        │                └── inspect dmesg
        │
        └── CH340/CH341 absent
                 │
                 ├── try another USB cable
                 ├── try another USB port
                 ├── reseat ESP32-CAM and MB board
                 └── inspect dmesg
```

---

# 31. Recommended complete setup procedure from a clean start

Use this order for future ESP32-CAM installations.

## Phase A — Arduino IDE

```bash
mkdir -p ~/Applications
chmod +x ~/Applications/arduino-ide_2.3.10_Linux_64bit.AppImage
sudo apt update
sudo apt install libfuse2
```

Launch Arduino IDE. If the Electron sandbox fails, use either the `--no-sandbox` workaround or the extracted-AppImage `chrome-sandbox` ownership/permission fix.

## Phase B — ESP32 board package

Install Espressif's ESP32 board package and select:

```text
AI Thinker ESP32-CAM
```

## Phase C — Linux serial permissions

```bash
sudo usermod -aG dialout $USER
```

Log out and back in.

Verify:

```bash
groups
```

## Phase D — USB detection

Connect ESP32-CAM → ESP32-CAM-MB → laptop.

Check:

```bash
lsusb
ls /dev/ttyUSB*
```

Expected:

```text
1a86:7523 QinHeng Electronics CH340 serial converter
/dev/ttyUSB0
```

## Phase E — Arduino IDE port

Select:

```text
Tools → Port → /dev/ttyUSB0
```

## Phase F — WiFiScan

Upload:

```text
File → Examples → WiFi → WiFiScan
```

Open Serial Monitor at 115200.

Expected:

```text
Scan start
Scan done
... networks found
```

## Phase G — CameraWebServer

Open:

```text
File → Examples → ESP32 → Camera → CameraWebServer
```

Enable:

```cpp
#define CAMERA_MODEL_AI_THINKER
```

Enter Wi-Fi credentials.

Close Serial Monitor before upload.

Upload.

Reopen Serial Monitor at 115200.

Wait for:

```text
Camera Ready! Use 'http://<actual-ip>' to connect
```

Open that URL on a device connected to the same network.

---

# 32. What each important command is for

### USB hardware detection

```bash
lsusb
```

Shows USB devices detected by Linux.

### Serial device detection

```bash
ls /dev/ttyUSB*
```

Shows USB serial devices such as `/dev/ttyUSB0`.

### Serial permissions

```bash
ls -l /dev/ttyUSB0
```

Typical healthy permissions:

```text
crw-rw---- 1 root dialout ... /dev/ttyUSB0
```

### User group membership

```bash
groups
```

Check for `dialout`.

### USB kernel debugging

```bash
sudo dmesg -w
```

Use while plugging/replugging the board.

### Port ownership

```bash
sudo lsof /dev/ttyUSB0
```

or:

```bash
sudo fuser -v /dev/ttyUSB0
```

### Serial terminal

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Useful for raw ESP32 boot logs.

### Network reachability

```bash
ping 192.168.x.x
```

Replace the address with the actual IP printed by CameraWebServer.

---

# 33. Problems encountered in this session — quick reference

| Problem | Symptom | Fix / diagnosis |
|---|---|---|
| FUSE missing | `libfuse.so.2` error | Install `libfuse2` on Ubuntu 24.04; it selects `libfuse2t64` |
| Electron sandbox | `chrome-sandbox` SUID error | `chown root:root` + `chmod 4755`, or launch with `--no-sandbox` |
| Board/port confusion | Port menu empty | Check `lsusb` and `/dev/ttyUSB*`; board selection does not create a port |
| USB cable uncertainty | CH340 not detected | Test/reconnect with known-good data cable and inspect `dmesg` |
| Missing serial permissions | `/dev/ttyUSB0` owned by `root:dialout` | Add user to `dialout`, log out/in |
| Port busy | `Errno 16 Device or resource busy` | Close Serial Monitor/miniterm; identify owner with `lsof`/`fuser` |
| Port disappears | `Errno 2 No such file or directory` | CH340 USB device disappeared; reconnect and inspect `dmesg` |
| WiFiScan not visible on phone | No ESP32 hotspot | Normal; WiFiScan only scans existing networks |
| Camera URL test | Need web access | Open the printed `http://192.168.x.x` URL on same LAN |
| Repeated `Hard resetting via RTS pin` | Looks like a reset problem | Normally just the normal post-upload reset message |
| No serial output | Blank Serial Monitor | Check port, baud, port ownership, then use miniterm after closing Serial Monitor |
| `<ESP32-IP>` ping syntax error | Bash syntax error | Use the actual IP without `<` or `>` |
| Camera upload failed | esptool cannot open `/dev/ttyUSB0` | Verify CH340 and `/dev/ttyUSB0`; close serial tools; reconnect if missing |

---

# 34. Final known-good state reached during the session

The following milestones were successfully achieved:

- Arduino IDE 2.3.10 was running.
- Ubuntu 24.04 recognized the ESP32-CAM-MB's CH340 USB serial converter.
- `/dev/ttyUSB0` was successfully created.
- The user was added to `dialout`.
- ESP32 board package was installed.
- `AI Thinker ESP32-CAM` was selected correctly.
- WiFiScan compiled and uploaded successfully.
- Upload verification succeeded with `Hash of data verified.`
- ESP32 WiFi scanning worked and detected nearby networks.
- CameraWebServer was subsequently configured sufficiently to produce a camera URL, showing that the board successfully connected to Wi-Fi and initialized far enough to provide its network endpoint.

Intermittent USB disconnects remained the main recurring host-side issue when the programmer stopped appearing in `lsusb` and `/dev/ttyUSB0`.

---

# 35. Best practice checklist for future sessions

- Keep Arduino IDE and serial terminals mutually exclusive when using `/dev/ttyUSB0`.
- Prefer a known-good USB data cable.
- Do not run Arduino IDE as root.
- Do not install random CH340 drivers when Ubuntu already detects `1a86:7523` and loads `ch341`.
- Do not treat `Hard resetting via RTS pin...` as an upload failure.
- Check `lsusb` and `/dev/ttyUSB0` before changing Arduino settings.
- Use `sudo dmesg -w` when the USB serial device unexpectedly disappears.
- Use WiFiScan as the first functional test, then CameraWebServer.
- Keep the CameraWebServer URL and IP address handy while testing network access.
- Never paste Wi-Fi passwords into support logs.

---

# 36. Minimal emergency recovery sequence

When something suddenly stops working:

```bash
# 1. Check USB hardware
lsusb

# 2. Check serial port
ls /dev/ttyUSB*

# 3. If missing, reconnect the board and inspect kernel logs
sudo dmesg -w

# 4. Verify permissions
ls -l /dev/ttyUSB0
groups

# 5. If port is busy, find its owner
sudo lsof /dev/ttyUSB0

# 6. Once available, select /dev/ttyUSB0 in Arduino IDE
# 7. Close Serial Monitor before uploading
# 8. Upload WiFiScan or CameraWebServer
# 9. Reopen Serial Monitor at 115200 after upload
```

This sequence should solve or localize most setup failures without reinstalling Arduino IDE or ESP32 support.

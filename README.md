# PaleBlue Linux
**A basic Linux distribution for the Amazon Echo Dot**  
by Christopher R. Curzio

## Introduction 
Welcome to the PaleBlue Linux project. PaleBlue is a small Linux distribution for use with the 2nd Generation Amazon Echo Dot ("biscuit"). No Amazon services, no integrations, no voice assistant, no cloud nonsense, no tracking or data collection. Just Linux. (Plus a few useful utilities.)

PaleBlue is based on Alpine Linux and builds on the very excellent work by [HuskerMinion](https://github.com/HuskerMinion), namely [TECHO5](https://github.com/HuskerMinion/techo5) and [TECHO5 Dot](https://github.com/HuskerMinion/techo5-dot). Where TECHO5 Dot and its ilk are engineered specifically around Home Assistant integration, PaleBlue is designed to be more of a generic and usable Linux operating system.

## What's Included? 
In addition to busybox and standard core system utilities, PaleBlue also includes:

- **Sound**: Audio support via the Advanced Linux Sound Architecture (ALSA)
- **Networking**: Bluetooth support via BlueZ as well as full Wi-Fi support
- **Dropbear**: A lightweight SSH server
- **Perl**: Larry Wall's Practical Extraction and Report Language
- **GNU Nano**: The friendly console text editor, based on the PIne COmposer (or "pico")

## Requirements 
- A 2nd Generation Amazon Echo Dot (RS03QR) running Fire OS 6 (tested with 6.5.6.4)
- A computer running macOS, Linux, or Windows
- The Android Debug Bridge ("adb") utility installed on the computer
- Git installed on the computer (not strictly required but makes downloading easier)
- Python installed on the computer (should already be there on Mac or Linux)
- A micro USB cable to connect the Echo Dot to the computer

## Installation 
If your Dot is not already unlocked, you will first need to unlock it using the amonet package. On Windows this will also require installing the appropriate device drivers to communicate with the Echo Dot. Full instructions for this process can be found [here](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/). 

Once unlocked, unplug the Dot and then start it in recovery mode by plugging it in while holding the + button. Continue holding the button down until the device completes startup in recovery mode. When recovery mode is active, the LED ring on the device will glow white. Go ahead and grab the Dot's serial number with `adb devices`. This may come in handy. 

1. Download the project files: `git clone https://github.com/ccurzio/PaleBlue`
2. Move into the project directory: `cd PaleBlue`
3. Execute a dry run of the installer: `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork" --dry-run`; this will create a backup of your Dot's boot and recovery partitions, fetch all of the required packages, and build the system image. We do a dry run first to create the backup and make sure everything builds successfully without writing to the Dot.
4. If everything looks good, burn the image to the Dot for real: `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork"`
5. A successful boot will show `PaleBlue Linux 1.0, address 169.254.0.27, SSH running`. You may see a message on the computer that says SSH on port 22 did not answer, but this isn't always indicative of a problem. Go ahead and connecting with SSH anyway. It'll probably work. 

**<ins>Installation Notes</ins>**
- On Windows, you'll probably need to use `python` instead of `python3`. If it's not in your path, just replace `python3` in all of the commands with the full path to the `python` binary.
- If you have only one Echo Dot connected to your computer, the installer should automatically detect it. If it doesn't (or if you have multiple Dots connected), specify the device by using `--serial "SERIALNUMBER"` in the installer command line. (You did remember to make a note of the serial number after running `adb devices`, right?)
- By default, the device will try to configure the network interface with DHCP after connecting to the network. If you instead want to give the device a static IP, use the correct values with `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork" --ip 169.254.0.18/24 --gateway 169.254.0.1` and optionally `--dns 1.1.1.1,2.2.2.2`
- You will be prompted to set the passphrase for the wireless network during the installation process.
- The LED ring will display a spinning animation while the device boots. Once booted, the ring should stop spinning and settle into a medium blue.
- After the device has started up you can log into it as `root` using SSH. (The default password is "password" so change it ffs)
- A wide-open root shell is available over the serial port connected through USB. On Windows you can access it through PuTTY. Open Device Manager, find "Ports," and make note of the COM port associated with the Dot. Then in PuTTY select "Serial" and enter that COM port. (You may have to hit enter after connecting to see the command prompt.) On macOS or Linux you can use a terminal emulator such as minicom. Find the port with `ls /dev/tty.*`; on macOS it'll be something like `/dev/tty.usbmodem14301`
- If you want to restart the device in recovery mode, as root you can use `to-twrp --yes`
- If you're in recovery mode and you want to boot normally without making any further changes, use `adb shell sh /cache/paleblue/back-to-linux.sh`
- Once you've confirmed the device boots properly and that you can get in via SSH, you can and probably should go ahead and disable that serial root shell: `sed -i 's|^::respawn:/usr/local/sbin/paleblue-console|#&|' /etc/inittab` and then reboot.
- If you don't like nano, don't worry. vi is included as well. 

## Special Thanks
- The TECHO5 Team
- Yuri Gelfand
- The Alpine Linux Team
- Carl Sagan

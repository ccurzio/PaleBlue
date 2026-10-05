# PaleBlue Linux
**A basic Linux distribution for the Amazon Echo Dot**  
by Christopher R. Curzio

## Introduction 
Welcome to the PaleBlue Linux project. PaleBlue is a small Linux distribution for use with the 2nd Generation Amazon Echo Dot ("biscuit"). No Amazon services, no integrations, no Alexa voice assistant, no cloud nonsense, no tracking or data collection. Just Linux. (Plus a few useful utilities.)

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

The `adb` utility is included as part of the Android SDK Platform Tools. Downloads for Mac, Linux, and Windows can be found [here](https://developer.android.com/tools/releases/platform-tools).

Once unlocked, unplug the Dot and then start it in recovery mode by plugging it in while holding the + button. Continue holding the button down until the device completes startup in recovery mode. When recovery mode is active, the LED ring on the device will glow white. Go ahead and grab the Dot's serial number with `adb devices`. This may come in handy. 

1. Download the project files: `git clone https://github.com/ccurzio/PaleBlue`
2. Move into the project directory: `cd PaleBlue`
3. Execute a dry run of the installer: `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork" --dry-run`; this will create a backup of your Dot's boot and recovery partitions, fetch all of the required packages, and build the system image. We do a dry run first to create the backup and make sure everything builds successfully without writing to the Dot.
4. If everything looks good, burn the image to the Dot for real: `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork"`
5. **BE PATIENT!** The install can take a few minutes. Don't interrupt the install process and don't unplug the device while the installation is running.
6. A successful boot will show `PaleBlue Linux 0.1, address 169.254.0.27, SSH running`. You may see a message on the computer that says SSH on port 22 did not answer, but this isn't always indicative of a problem. Go ahead and try connecting with SSH anyway. It'll probably work. 

**<ins>Installation Notes</ins>**
- On Windows, you'll probably need to use `python` instead of `python3`. If it's not in your path, just replace `python3` in all of the commands with the full path to the `python` binary.
- If you have only one Echo Dot connected to your computer, the installer should automatically detect it. If it doesn't (or if you have multiple Dots connected), specify the device by using `--serial "SERIALNUMBER"` in the installer command line. (You did remember to make a note of the serial number after running `adb devices`, right?)
- By default, the device will try to configure the network interface with DHCP after connecting to the network. If you instead want to give the device a static IP, use the correct values with `python3 tools/install-dot.py --hostname "DotHostname" --wifi "YourNetwork" --ip 169.254.0.18/24 --gateway 169.254.0.1` and optionally `--dns 1.1.1.1,2.2.2.2`
- You will be prompted to set the passphrase for the wireless network during the installation process.
- The LED ring will display a spinning animation while the device boots. Once booted, the ring should stop spinning and settle into a medium blue.
- After the device has started up you can log into it as root using SSH. (The default password is "password" so change it ffs)
- A wide-open root shell is available over the serial port connected through USB. On Windows you can access it through PuTTY. Open Device Manager, find "Ports," and make note of the COM port associated with the Dot. Then in PuTTY select "Serial" and enter that COM port. (You may have to hit enter after connecting to see the command prompt.) On macOS or Linux you can use a terminal emulator such as minicom. Find the port with `ls /dev/tty*`; on macOS it'll be something like `/dev/tty.usbmodem14301`
- If you want to restart the device in recovery mode, logged into the Dot as root you can use `to-twrp --yes`
- If you're in recovery mode and you want to boot normally without making any further changes, on the computer connected to the Dot use `adb shell sh /cache/paleblue/back-to-linux.sh`
- Once you've confirmed the device boots properly and you can get in via SSH, you can and probably should go ahead and disable that serial root shell. Edit `/etc/inittab` and comment out the `paleblue-console` entry. (Or just use: `sed -i 's|^::respawn:/usr/local/sbin/paleblue-console|#&|' /etc/inittab`.) Once the change is saved, the serial console will be disabled on the next reboot.
- If you don't like nano, don't worry. vi is included as well.

## PaleBlue Dot Hardware Manager 
Included with PaleBlue Linux is `dotctl`, a Perl script used for managing the hardware of the Echo Dot. With this tool you can manage the LEDs, the hardware buttons, Bluetooth, audio, the mute function, and the light sensor.

**<ins>LED Ring</ins>**  
The LED ring consists of 12 segments, numbered clockwise starting from the one between the mic and volume-down buttons.

`dotctl led [off|all COLOR|seg N COLOR|frame HEX72|bar PERCENT COLOR|get|current N]`  
`dotctl led anim [on|off]`  
`dotctl led [spin COLOR|pulse COLOR SECS]`  
`dotctl mute led [bright|dim]`  

`COLOR` is RRGGBB or #RRGGBB, or one of: red green blue white yellow cyan magenta orange

- Control of an individual segment is defined by `seg N COLOR` where `N` is the segment number (0-11).
- A `frame` is one complete picture of the ring; the color of all 12 LEDs at one moment. On the device the current value is exposed at `/sys/bus/i2c/devices/0-003f/frame`, such as `0000a00000a00000a00000a00000a00000a00000a00000a00000a00000a00000a00000a0` showing the standard blue ring after booting.
- You can use `led bar PERCENT COLOR` to define a progress bar based on percentage starting at the first segment.
- `led get` reads the current frame and returns the values as one line per segment, showing the segment number followed by its color.
- `led current` returns the ring's current brightness, which can be set using `led current N` where `N` is a number between 0 and 3. (Lower is brighter.)
- You can animate a single color spinner using `led spin COLOR`
- To make the entire ring "breathe" use `led pulse COLOR SECS` where `SECS` defines the number of seconds per-breath. (Decimals work. To an extent.)
- The LED driver's built-in spinner animation can be controlled using `led anim on` or `off`
- When mute is on and the mute button is lit, you can control its brightness with `mute led bright` or `dim`

**<ins>Audio</ins>**  
The Dot's audio device is actually fairly decent for the form factor it's crammed into. That said, it's not amazing so don't expect miracles. It's fine for playing beeps and boops and voice audio now and again. You can play music through it but I'm not sure you'd want to.

`dotctl audio [on|off|status|volume [0-100]|tone SECS HZ|play FILE.wav]`  
`dotctl mute [on|off|status|toggle]`  

- You can turn audio on and off with `audio on` or `off`
- `audio status` returns the current audio state and volume level.
- You can set volume with `audio volume [0-100]` (Higher is louder.)
- You can play an audio tone using `audio tone SECS HZ` where `SECS` is the number of seconds the tone should last and `HZ` is the tone frequency in hertz.
- Play an audio file with `audio play FILE.wav`. (Only WAV files are supported right now.)
- The current microphone state can be retrieved with `mute status`. Cut the device's microphone with `mute on` and re-enable it with `off`. `mute toggle` simply reads the current state and flips it.

**<ins>Buttons</ins>**  
`dotctl buttons [--hold SECS|--hooks DIR]`  

For actions involving the hardware buttons, you can read the current values with `dotctl buttons`. Until interrupted, each time a button is pressed you will see one of `volume-up`, `volume-down`, `action`, and `mute` along with a state of `press`, `hold`, or `release`. If you want to register a button hold after a specific amount of seconds, use `buttons --hold N` where `N` is the number of seconds until a hold is registered.

If you want the buttons to trigger actions in the background, use `buttons --hooks DIR` where `DIR` is the path to where you've stashed some scripts to run (set with +x) based on what's happening with the buttons. For example, if you want something in `/scripts` to run when the action button is pressed, create `/scripts/action-press` and make it executable.

**<ins>Bluetooth</ins>**  
`dotctl bt [status|on|off|scan SECS]`  
`dotctl bt devices [paired|connected|trusted|bonded]`  
`dotctl bt [pair|connect|disconnect|trust|remove] MAC`  
`dotctl bt discoverable [on|off]`  
`dotctl bt name TEXT`  
`dotctl bt accept SECS`  

- You can turn Bluetooth on and off with `bt on` or `off`
- Set the Dot's discoverability via Bluetooth with `bt discoverable on` or `off`
- `bt status` returns the current state and details of the Bluetooth controller.
- `bt scan SECS` turns on discovery and listens for nearby devices for the specified number of seconds, then stops scanning.
- `bt devices` lists devices currently `paired` with the Dot, `connected` to the Dot, `trusted` by the Dot indicating a device can (re)connect without authorization, or `bonded` indicating a device has been paired with its link key stored allowing for reconnecting without re-pairing.
- Pair with a detected device with `bt pair MAC` where `MAC` is the hardware address of the device you want to pair.
- Connect to a detected device with `bt connect MAC`. You can disconnect with `bt disconnect MAC`
- Set a device as trusted with `bt trust MAC`
- Completely remove an associated device with `bt remove MAC`
- `bt name TEXT` sets the name other devices see when they scan for the Dot. Names can contain spaces, just wrap it in quotes for readability.

You can also temporarily set the Dot to act as an open Bluetooth speaker using `bt accept SECS` where `SECS` is the number of seconds it should be available. No PIN or confirmation is asked, so any pairing request is accepted. After `SECS` expires, discoverability is turned off and the device is disconnected. This allows for a phone to connect and become trusted without needing to futz with settings or have login access to the device.

**<ins>Light Sensor</ins>**  
`dotctl lux` returns the current value of the Dot's ambient light sensor.

## To-Do List
This project is brand new so this list is short, but I imagine I will add things as I think of them. 

- Expanded audio support through `dotctl audio play`
- A native Windows installer that doesn't need Python (PowerShell?)
- Fix/improve SSH service detection in the installer
- More advanced setup (create ad-hoc wireless network and configure over HTTP?)
- Maybe add some manner of Python? (BEGRUDGINGLY)

## Special Thanks
- The TECHO5 Team
- Yuri Gelfand
- The Alpine Linux Team
- Carl Sagan

<sub>Neither myself nor PaleBlue Linux are in any way affiliated with Amazon. "Echo," "Echo Dot," and "Alexa" are registered trademarks of Amazon.com, Inc.</sub>

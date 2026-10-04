# PaleBlue
**A basic Linux distribution for the Amazon Echo Dot**  
by Christopher R. Curzio

## Introduction 
Welcome to the PaleBlue Linux project. PaleBlue is a small Linux distribution for use with the 2nd Generation Amazon Echo Dot ("biscuit"). It's based on Alpine Linux and builds on the very excellent work by [HuskerMinion](https://github.com/HuskerMinion), namely [TECHO5](https://github.com/HuskerMinion/techo5) and [TECHO5 Dot](https://github.com/HuskerMinion/techo5-dot). Where TECHO5 Dot and its ilk are engineered specifically around Home Assistant integration, PaleBlue is designed to be a more generic and usable Linux operating system.

## What's Included? 
In addition to busybox and standard core system utilities, PaleBlue also includes:

- **Networking**: Full Wi-Fi support as well as Bluetooth support via BlueZ
- **Dropbear**: A lightweight SSH server
- **PERL**: Larry Wall's Practical Extraction and Report Language
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

**<ins>Windows</ins>**  
1. 

# SimosHighSpeedLogger

This is a series of scripts used for making a UDS connection to a Simos19 ECU (assuming it has a compatible ASW).
This was developed around the Eurodyne Maestro ECU in the MQB chassis VW/Audi

## Installation

Installation is relatively straightforward.  Assuming you have a working pi with piCan hat, drivers, etc:

clone the repository into the home directory of your pi user

```bash
pi@raspberrypi:~/SimosHighSpeedLogger $ whoami
pi
pi@raspberrypi:~/SimosHighSpeedLogger $ cd
pi@raspberrypi:~ $ whoami
pi
pi@raspberrypi:~ $ pwd
/home/pi
pi@raspberrypi:~ $ git clone https://github.com/joeFischetti/SimosHighSpeedLogger.git
Cloning into 'SimosHighSpeedLogger'...
remote: Enumerating objects: 58, done.
remote: Counting objects: 100% (58/58), done.
remote: Compressing objects: 100% (35/35), done.
remote: Total 58 (delta 23), reused 49 (delta 14), pack-reused 0
Unpacking objects: 100% (58/58), done.
pi@raspberrypi:~ $ cd SimosHighSpeedLogger/
pi@raspberrypi:~/SimosHighSpeedLogger $ 
```

At this point, you'll have a basic, working, logger.

## Usage

### Basic
Using the logger with a front end is relatively straightforward.  With network connectivity to your pi and it plugged into the car, you can ssh in and run the logger with a TUI gague cluster:
```bash
pi@raspberrypi:~/SimosHighSpeedLogger $ python3 pyLog.py
```

You'll need to press "enter" to tell it to connect to the car, and when it does, you should get live display on the gauges.
Pressing the enter key will toggle logging on and off.

If, instead, you want to run it headless:

```bash
pi@raspberrypi:~/SimosHighSpeedLogger $ python3 pyLog.py --headless
```

Headless mode will enable "WOT logging".  The pi will auto-start the logger at >80% throttle, and will stop logging 5 seconds after you've let off.

### Advanced
Since the logger has the capability of running headless, I've included a few scripts that can be used to trigger it when USB sticks are inserted.
systemd udev has the capability of triggering scripts based on specific events.  The following files within the repo are notable:
```
etc/systemd/system/usb-mount@.service
etc/systemd/system/pyLog@.service
etc/udev/rules.d/50-usbstick_test.rules
etc/udev/rules.d/50-usbstick.rules

usr/local/bin/usb-mount.sh
```

These files can be moved to their respective locations on the root filesystem.  Once you've done that:
```bash
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```

Descriptions of each file:
<pre>
etc/udev/rules.d/50-usbstick_test.rules
etc/udev/rules.d/50-usbstick.rules
These files are used to trigger events within udev.  They trigger the systemd file (which launches the mount script in /usr/local/bin)
</pre>

<pre>
etc/systemd/system/usb-mount@.service
This systemd file will mount the usb stick that was passed in the argument.  A script called via udev directly doesn't have the proper permissions to handle the mount operation
</pre>

<pre>
usr/local/bin/usb-mount.sh
This script is used to automatically mount the flash drive that was called, check the contents of it, and if there's a 'parameters.yaml' file, launch the pi in headless logging mode
</pre>

<pre>
etc/systemd/system/pyLog@.service
This is a systemd unit file that takes the USB mounted stick as a parameter.  It'll set that as both the output location for logs and as the parameter file to be used for reading logging parameters
</pre>

Argparse also does a great job displaying a basic help menu:
```bash
pi@raspberrypi:~/SimosHighSpeedLogger $ python3 pyLog.py --help
usage: pyLog.py [-h] [--headless] [--params PARAMS]

Simos18 High Speed Logger

optional arguments:
  -h, --help       show this help message and exit
  --headless
  --params PARAMS  location of a parameter file to use for parameters, specify
                   full path
```

## Notes
Huge thanks to Brian for helping me out along the way: https://github.com/bri3d/
UDEV/Systemd stuff adapted from: https://www.andreafortuna.org/2019/06/26/automount-usb-devices-on-linux-using-udev-and-systemd/


## TODO
Do a better job documenting the way the udev rules work (mainly - how to identify the sticks, and how to set them up)
Stop/Kill the logger when another USB stick is inserted into the pi.


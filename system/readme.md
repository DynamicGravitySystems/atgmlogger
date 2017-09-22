###Prerequisites:
Python 3.5 or Python 3.6 on Raspbian Linux (Debian Based)

######Debian Packages:
- ntfs-3g
- exfat-fuse
- exfat-utils

######Python Packages:
- pyserial >= 3.3
- jinja2 >= 2.9.6
- MarkupSafe == 1.0
- PyYAML == 3.12
- RPi.GPIO == 0.6.3


Automated Installation with (GNU) Make:
---------------------------------------
Execute the following in the package directory:
```
make install
systemctl start SerialLogger
```

#####Issues:

- Depending on the version of Raspberry Pi, the serial port name (symlink) may vary between /dev/ttyS0 and /dev/ttyAMA0
  - Raspberry Pi Zero - /dev/ttyAMA0
  - Raspberry Pi Zero W (Wireless) - /dev/ttyS0


Manual Installation:
--------------------

Installation Directories (copy the following files to the specified destinations):
  - 90-removable-usb.rules -> /etc/udev/rules.d/90-removable-usb.rules
  - media-removable.mount -> /etc/systemd/system/media-removable.mount
  - SerialLogger.service -> /etc/systemd/system/SerialLogger.service

After installing .mount and .service files run the following commands:
```commandline
sudo systemctl daemon-reload
sudo systemctl enable media-removable.mount
sudo systemctl enable SerialLogger.service
```

Explanation:
- 90-removable-usb.rules creates a UDEV rule that adds a symbolic link to /dev/usbstick when a usb block device (hdd)
is inserted. This symlink is used by the following mount file to mount the filesystem.
- media-removable.mount is a systemd mount unit which instructs systemd to mount /dev/usbstick to /media/removable when
it detects the device 'dev-usbstick.device'. The unit will also dismount the device when it becomes unavailable.
- SerialLogger.service is a systemd service unit which executes the Serial Logging python script. When this unit is
enabled (see above command - systemctl enable SerialLogger.service) the program will be executed upon system startup.
Automated Installation with (GNU) Make:
---------------------------------------
run:
```
make install
systemctl start SerialLogger
```



Manual Installation:
--------------------

Installation Directories:
90-removable-usb.rules -> /etc/udev/rules.d/90-removable-usb.rules
media-removable.mount -> /etc/systemd/system/media-removable.mount
SerialLogger.service -> /etc/systemd/system/SerialLogger.service

After installing .mount and .service files run the following commands:
sudo systemctl daemon-reload
sudo systemctl enable media-removable.mount
sudo systemctl enable SerialLogger.service

Explanation:
- 90-removable-usb.rules creates a UDEV rule that adds a symbolic link to /dev/usbstick when a usb block device (hdd)
is inserted. This symlink is used by the following mount file to mount the filesystem.
- media-removable.mount is a systemd mount unit which instructs systemd to mount /dev/usbstick to /media/removable when
it detects the device 'dev-usbstick.device'. The unit will also dismount the device when it becomes unavailable.
- SerialLogger.service is a systemd service unit which executes the Serial Logging python script. When this unit is
enabled (see above command - systemctl enable SerialLogger.service) the program will be executed upon system startup.
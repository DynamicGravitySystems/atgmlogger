Dynamic Gravity Systems - Serial Data Recorder
==============================================

 1. Installation:
	Use the provided makefile to install the Serial Data Recorder program on a Raspberry PI microcomputer. (See the code snippet below)
 2. Dependencies:
	The following system packages are required for full functionality of the USB data copying.
	  - ntfs-3g
	  - exfat-fuse
	  - exfat-utils

```
$> tar -xzf serial_logger-1.0.tar.gz 
$> cd serial_logger
$> sudo make install
$> sudo systemctl status SerialLogger
  ```
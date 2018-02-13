SHELL = /bin/sh
PREFIX = /opt
PYTHON = $(shell which python3.6)
PIP = $(shell which pip3.6)
SYSTEMD = /lib/systemd/system
UDEV = /etc/udev/rules.d
USB = /media/removable

SRCDIR = .
INSTALL = /usr/bin/install -m644
MKDIR = /usr/bin/install -d

# Installation Path for Systemd unit files
UNIT_PATH = $(DESTDIR)$(SYSTEMD)
# Installation Path for UDEV rules
UDEV_PATH = $(DESTDIR)$(UDEV)

### Define files to be installed ###
SYSTEMD_FILES = $(UNIT_PATH)/SerialLogger.service $(UNIT_PATH)/media-removable.mount
UDEV_FILES = $(UDEV_PATH)/90-removable-storage.rules

### Begin Target Defs ###

.PHONY: all
all: ;

$(UNIT_PATH)/atgmlogger.service: $(SRCDIR)/atgmlogger.service
$(UNIT_PATH)/media-removable.mount: $(SRCDIR)/system/media-removable.mount
$(UDEV_PATH)/90-removable-storage.rules: $(SRCDIR)/system/90-removable-storage.rules

.PHONY: install
install: $(SYSTEMD_FILES) $(UDEV_FILES) $(USB)
	@if [ -z "$(DESTDIR)" ]; then \
		if ! grep -q ^enable_uart=1 '/boot/config.txt'; then \
			echo "enable_uart=1" >> '/boot/config.txt'; \
			echo "UART enabled, REBOOT Required." ;\
		fi; \
		sed -i -r 's/console=serial0,115200 //' /boot/cmdline.txt; \
		systemctl daemon-reload; \
		systemctl disable media-removable.mount; \
		systemctl enable media-removable.mount; \
		echo "Start SerialLogger with sudo systemctl start atgmlogger.service"; \
	fi; \

$(UNIT_PATH):
	$(MKDIR) $(UNIT_PATH)

$(USB):
	$(MKDIR) $(USB)

$(UNIT_PATH)/%: | $(UNIT_PATH)
	$(INSTALL) $< $@

$(UDEV_PATH):
	$(MKDIR) $(UDEV_PATH)

$(UDEV_PATH)/%: | $(UDEV_PATH)
	$(INSTALL) $< $@

.PHONY: uninstall
uninstall:
	systemctl stop SerialLogger.service && systemctl disable SerialLogger.service
	systemctl disable media-removable.mount
	systemctl daemon-reload
	rm -f $(SYSTEMD_FILES)
	rm -f $(UDEV_FILES)
	rm -rf $(BUILD_PATH)

.PHONY: clean
clean:
	rm -f $(SRCDIR)/system/SerialLogger.service

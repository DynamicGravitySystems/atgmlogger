SHELL = /bin/sh
PREFIX = /opt
SYSTEMD = /usr/lib/systemd/system
UDEV = /etc/udev/rules.d

SRCDIR = .
INSTALL = /usr/bin/install -m644
MKDIR = /usr/bin/install -d

BUILD_PATH = $(DESTDIR)$(PREFIX)/SerialLogger
UNIT_PATH = $(DESTDIR)$(SYSTEMD)
UDEV_PATH = $(DESTDIR)$(UDEV)

### Define files to be installed ###
INSTALL_FILES = $(BUILD_PATH)/SerialLogger.py $(BUILD_PATH)/logging.yaml
SYSTEMD_FILES = $(UNIT_PATH)/SerialLogger.service $(UNIT_PATH)/media-removable.mount
UDEV_FILES = $(UDEV_PATH)/90-removable-storage.rules

.PHONY: all
all: sys/SerialLogger.service

sys/SerialLogger.service:
        sed 's=@BINDIR@=$(abspath $(BUILD_PATH))=g' $(SRCDIR)/SerialLogger.in > $(SRCDIR)/SerialLogger.service

.PHONY: install
install: $(INSTALL_FILES) $(SYSTEMD_FILES) $(UDEV_FILES)
        systemctl daemon-reload
        systemctl enable media-removable.mount
        systemctl enable SerialLogger.service

$(BUILD_PATH):
        install -d $(BUILD_PATH)

$(BUILD_PATH)/SerialLogger.py: $(SRCDIR)/SerialLogger.py
$(BUILD_PATH)/logging.yaml: $(SRCDIR)/logging.yaml
$(BUILD_PATH)/%: | $(BUILD_PATH)
        $(INSTALL) $< $@

$(UNIT_PATH):
        $(MKDIR) $(UNIT_PATH)


$(UNIT_PATH)/SerialLogger.service: $(SRCDIR)/SerialLogger.service
$(UNIT_PATH)/media-removable.mount: $(SRCDIR)/media-removable.mount
$(UNIT_PATH)/%: | $(UNIT_PATH)
        $(INSTALL) $< $@

$(UDEV_PATH):
        $(MKDIR) $(UDEV_PATH)

$(UDEV_PATH)/90-removable-storage.rules: $(SRCDIR)/90-removable-storage.rules
$(UDEV_PATH)/%: | $(UDEV_PATH)
        $(INSTALL) $< $@

.PHONY: clean
clean:
        rm -f $(SRCDIR)/SerialLogger.service

# System install for distribution packages (RPM spec, AUR PKGBUILD):
#   make install DESTDIR=<package root> PREFIX=/usr
# The app goes to $(PREFIX)/share/shiftray and runs on the system's Python and PySide6.
# The udev rule ships with the package, so Setup has no key step to do.

PREFIX ?= /usr
DESTDIR ?=
PYTHON ?= /usr/bin/python3
UDEVDIR ?= $(PREFIX)/lib/udev/rules.d

APP = shiftray
SHARE = $(PREFIX)/share/$(APP)
ASSETS = shiftray/assets

.PHONY: install uninstall

install:
	install -d $(DESTDIR)$(SHARE) $(DESTDIR)$(PREFIX)/bin $(DESTDIR)$(PREFIX)/share/applications \
		$(DESTDIR)$(PREFIX)/share/icons/hicolor/256x256/apps $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps \
		$(DESTDIR)$(UDEVDIR)
	cp -r shiftray $(DESTDIR)$(SHARE)/
	find $(DESTDIR)$(SHARE) -name __pycache__ -prune -exec rm -rf {} +
	install -D -m 755 bin/$(APP) $(DESTDIR)$(SHARE)/bin/$(APP)
	printf '#!/bin/sh\nexec %s %s/bin/%s "$$@"\n' '$(PYTHON)' '$(SHARE)' '$(APP)' > $(DESTDIR)$(PREFIX)/bin/$(APP)
	chmod 755 $(DESTDIR)$(PREFIX)/bin/$(APP)
	sed -e 's|@EXEC@|$(APP)|; s|@ICON@|$(APP)|' $(ASSETS)/$(APP).desktop \
		> $(DESTDIR)$(PREFIX)/share/applications/$(APP).desktop
	install -m 644 $(ASSETS)/$(APP).png $(DESTDIR)$(PREFIX)/share/icons/hicolor/256x256/apps/$(APP).png
	install -m 644 $(ASSETS)/app-icon.svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP).svg
	install -m 644 $(ASSETS)/70-$(APP).rules $(DESTDIR)$(UDEVDIR)/70-$(APP).rules

uninstall:
	rm -rf $(DESTDIR)$(SHARE)
	rm -f $(DESTDIR)$(PREFIX)/bin/$(APP) $(DESTDIR)$(PREFIX)/share/applications/$(APP).desktop \
		$(DESTDIR)$(PREFIX)/share/icons/hicolor/256x256/apps/$(APP).png \
		$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP).svg $(DESTDIR)$(UDEVDIR)/70-$(APP).rules

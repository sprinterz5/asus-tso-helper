# COPR's "make srpm" method: on each tag (GitHub webhook) COPR runs
#   make -f .copr/Makefile srpm outdir=<dir> spec=<spec>
# The source archive comes from the release tag, as in a local rpmbuild.
SPEC = packaging/rpm/asus-tso-helper.spec

srpm:
	dnf -y install rpmdevtools
	spectool -g -C $(outdir) $(SPEC)
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" $(SPEC)

# Distribution packages

Run `sh packaging/arch/build.sh` from the project root on Arch Linux. It produces a
`termrec-0.4.0-1-any.pkg.tar.*` package in `packaging/arch/`. Install it with
`sudo pacman -U packaging/arch/termrec-0.4.0-1-any.pkg.tar.*`.

Run `python3 packaging/debian/build_deb.py` on any system with Python 3.10 or newer.
It produces `packaging/debian/dist/termrec_0.4.0-1_all.deb`. On Debian or Ubuntu,
install it with `sudo apt install ./packaging/debian/dist/termrec_0.4.0-1_all.deb`.
The builder uses only the Python standard library.

The Arch source archive is local and its PKGBUILD uses `SKIP` for its checksum.
Before publishing the Arch build recipe in AUR, replace the local archive with a
fixed release source and checksum. The Debian package uses the GitHub noreply address
for maintainer contact; replace it with your preferred public address if needed.
Repository hosting and signing are separate from building installable files.

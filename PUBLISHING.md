# Manual release

The project is prepared for GitHub account `lekasnet`. Run these commands yourself
so the commit and release are attributed only to your account.

1. On GitHub, create an empty **public** repository named `termrec` under `lekasnet`.
   Do not initialize it with a README, license, or `.gitignore`; they are already here.
2. Configure Git in this repository with your preferred display name and an email
   verified by GitHub (or your exact GitHub noreply email shown under Settings → Emails):

   ```bash
   cd /home/lek4s/Documents/termrec
   git config user.name "lekasnet"
   git config user.email "YOUR_GITHUB_EMAIL"
   git add .
   git commit -m "Release termrec 0.4.0"
   git remote add origin https://github.com/lekasnet/termrec.git
   git push -u origin main
   ```

3. Verify the **Check** workflow succeeds on GitHub.
4. Open **Releases → Draft a new release**. Create tag `v0.4.0` on `main`, use the
   notes in `CHANGELOG.md`, and upload these two files:

   - `packaging/arch/termrec-0.4.0-1-any.pkg.tar.*`
   - `packaging/debian/dist/termrec_0.4.0-1_all.deb`

5. Test the download links and install the released files on Arch and Debian/Ubuntu.
   Use `sudo pacman -U ./termrec-0.4.0-1-any.pkg.tar.*` or
   `sudo apt install ./termrec_0.4.0-1_all.deb`.

GitHub Releases distributes downloadable packages. To make `pacman -S termrec` or
`apt-get install termrec` work by name, publish signed package indexes and give users
repository configuration instructions. An AUR package supports AUR helpers, not
plain `pacman -S`; it also needs a separate AUR Git repository and a PKGBUILD that
fetches a fixed GitHub release with a verified checksum. The local PKGBUILD here
uses a generated local source archive and is not ready to submit unchanged to AUR.

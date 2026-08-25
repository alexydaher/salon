# Publishing Salon

Tagged releases publish two Flatpak bundles, one architecture-independent
Debian package, checksums, and a signed Flatpak repository. The repository is
deployed to GitHub Pages and its `.flatpakref` is attached to the GitHub
release.

## One-time repository setup

Create a dedicated, signing-only OpenPGP key. It must not have a passphrase,
because release jobs are unattended. Keep an offline backup: existing Flatpak
installations trust this key, so losing it requires a repository-key migration.

```sh
key_home=$(mktemp -d)
chmod 0700 "$key_home"
gpg --homedir "$key_home" --batch --passphrase '' \
  --quick-generate-key 'Salon Flatpak Repository <alexydaher@users.noreply.github.com>' \
  ed25519 sign 2y
gpg --homedir "$key_home" --with-colons --list-secret-keys
```

Copy the primary fingerprint from the `fpr` row, export the secret key, and
store the resulting single line as the GitHub Actions repository secret
`FLATPAK_GPG_PRIVATE_KEY`:

```sh
gpg --homedir "$key_home" --export-secret-keys FINGERPRINT | base64 -w0
```

Back up the key home securely, then remove the temporary copy. Do not commit
the private key or its encoded form.

In the GitHub repository settings, open **Pages**, set **Source** to **GitHub
Actions**, and save. The release workflow publishes the site at
`https://alexydaher.github.io/salon/`.

## Cutting a release

Update the version in all locations checked by
`scripts/prepare-flatpak-release.py`, including `debian/changelog`, then run:

```sh
scripts/check.sh
python3 scripts/prepare-flatpak-release.py
git tag -a vVERSION -m 'Salon VERSION'
git push origin main vVERSION
```

The tag workflow performs these release gates:

1. Verify Meson, Python, AppStream, Flatpak, changelog, screenshot, and Debian
   versions agree.
2. Build and smoke-test AMD64 and ARM64 Flatpak bundles on native runners.
3. Build `salon_VERSION-1_all.deb` on Ubuntu 26.04 and reject Lintian errors.
4. Import both Flatpak bundles into one repository, sign the commits and
   repository summary with the dedicated key, and deploy it to GitHub Pages.
5. Attach both bundles, the Debian package, Flatpak installer metadata,
   exported public key, pinned manifest, and `SHA256SUMS` to the GitHub
   release.

The Flatpak ref deliberately remains on the historical `master` branch used
by the existing standalone bundles. Changing it to `stable` would install a
second branch beside existing copies instead of updating them.

The Debian package is `Architecture: all` because Salon contains Python and
data rather than architecture-specific machine code. One package is therefore
correct for both AMD64 and ARM64; its dependencies select the matching native
GTK libraries.

## Recovery

If the Pages deployment fails, the GitHub release remains blocked rather than
advertising installer metadata for a repository that was not published. Fix
the Pages setting or signing-key secret and re-run the failed jobs.

If the GitHub release upload fails after Pages succeeds, re-running the
release job is safe: existing assets are uploaded with `--clobber`.

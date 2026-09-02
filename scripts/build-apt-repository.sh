#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the signed APT archive that ships beside the Flatpak repository in
# the GitHub Pages artifact, then prove it works by pointing a real apt at it.
#
#   site/apt/
#   ├── salon-archive-keyring.gpg
#   ├── pool/main/s/salon/salon_VERSION-1_all.deb
#   └── dists/stable/
#       ├── InRelease, Release, Release.gpg
#       └── main/binary-all/{Packages,Packages.gz}
#
# The archive holds exactly one version, the one being released. The Pages
# site is rebuilt from nothing on every tag, so the pool is not a history —
# it is the current download, the same promise the Flatpak repository makes.
#
# Deliberately no Valid-Until: releases here are irregular, and an expired
# Release file breaks `apt update` for everyone until the next tag is cut.

set -euo pipefail

ORIGIN='Salon'
LABEL='Salon'
SUITE='stable'
CODENAME='stable'
COMPONENT='main'
ARCHITECTURE='all'
DESCRIPTION='Signed Debian packages of the Salon living-room launcher'

deb=
output=
gpg_homedir=
fingerprint=
verify=1

usage() {
    cat >&2 <<'USAGE'
usage: build-apt-repository.sh --deb FILE --output DIR
                              --gpg-homedir DIR --fingerprint FINGERPRINT
                              [--no-verify]
USAGE
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --deb) deb="${2-}"; shift 2 ;;
        --output) output="${2-}"; shift 2 ;;
        --gpg-homedir) gpg_homedir="${2-}"; shift 2 ;;
        --fingerprint) fingerprint="${2-}"; shift 2 ;;
        --no-verify) verify=0; shift ;;
        *) usage ;;
    esac
done

[ -n "$deb" ] && [ -n "$output" ] || usage
[ -n "$gpg_homedir" ] && [ -n "$fingerprint" ] || usage
[ -f "$deb" ] || { echo "no such package: $deb" >&2; exit 1; }
[ -d "$gpg_homedir" ] || { echo "no such GnuPG home: $gpg_homedir" >&2; exit 1; }

# Resolved now: the archive is built from inside its own directory, so a
# relative path to either of these would stop meaning what it meant.
deb="$(readlink -f "$deb")"
gpg_homedir="$(readlink -f "$gpg_homedir")"

package="$(dpkg-deb -f "$deb" Package)"
version="$(dpkg-deb -f "$deb" Version)"
[ "$(dpkg-deb -f "$deb" Architecture)" = "$ARCHITECTURE" ] || {
    echo "expected an Architecture: $ARCHITECTURE package" >&2
    exit 1
}

pool="pool/$COMPONENT/${package:0:1}/$package"
binary="dists/$SUITE/$COMPONENT/binary-$ARCHITECTURE"

rm -rf "$output"
mkdir -p "$output/$pool" "$output/$binary"
install -m 0644 "$deb" "$output/$pool/"

cd "$output"

# Filename: in Packages is relative to the archive root, which is why this
# runs from there and scans `pool` rather than an absolute path. The trailing
# override argument other guides pass is deprecated; there is no override.
dpkg-scanpackages --arch "$ARCHITECTURE" pool > "$binary/Packages"
gzip -9 --keep --force "$binary/Packages"
grep -qx "Filename: $pool/$(basename "$deb")" "$binary/Packages"

# Written to a temporary file and moved into place: a redirect would truncate
# the previous Release before apt-ftparchive walks the tree, so the empty file
# would be hashed into its own checksum lists.
release="$(mktemp)"
apt-ftparchive \
    -o "APT::FTPArchive::Release::Origin=$ORIGIN" \
    -o "APT::FTPArchive::Release::Label=$LABEL" \
    -o "APT::FTPArchive::Release::Suite=$SUITE" \
    -o "APT::FTPArchive::Release::Codename=$CODENAME" \
    -o "APT::FTPArchive::Release::Architectures=$ARCHITECTURE" \
    -o "APT::FTPArchive::Release::Components=$COMPONENT" \
    -o "APT::FTPArchive::Release::Description=$DESCRIPTION" \
    release "dists/$SUITE" > "$release"
mv "$release" "dists/$SUITE/Release"
chmod 0644 "dists/$SUITE/Release"

# InRelease is what current apt fetches; Release.gpg is kept for clients that
# still ask for the detached form.
gpg --homedir "$gpg_homedir" --batch --yes --local-user "$fingerprint" \
    --clearsign --output "dists/$SUITE/InRelease" "dists/$SUITE/Release"
gpg --homedir "$gpg_homedir" --batch --yes --local-user "$fingerprint" \
    --armor --detach-sign --output "dists/$SUITE/Release.gpg" "dists/$SUITE/Release"

# Binary keyring, the format /etc/apt/keyrings/ and Signed-By: want.
gpg --homedir "$gpg_homedir" --batch --yes \
    --output salon-archive-keyring.gpg --export "$fingerprint"
[ -s salon-archive-keyring.gpg ]

archive="$PWD"
cd - > /dev/null

[ "$verify" -eq 1 ] || exit 0

# Everything above is metadata generation that looks right whether or not it
# is. So run the client: a private apt tree, trusting this keyring alone,
# updating from the archive over file: and resolving the package it should.
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/etc/apt/sources.list.d" "$root/etc/apt/trusted.gpg.d" \
    "$root/var/lib/apt/lists/partial" "$root/var/lib/dpkg" \
    "$root/var/cache/apt/archives/partial" "$root/var/log/apt"
: > "$root/etc/apt/sources.list"
: > "$root/var/lib/dpkg/status"
cat > "$root/etc/apt/sources.list.d/salon.sources" <<EOF
Types: deb
URIs: file:$archive
Suites: $SUITE
Components: $COMPONENT
Signed-By: $archive/salon-archive-keyring.gpg
EOF

apt_options=(
    -o "Dir::Etc::sourcelist=$root/etc/apt/sources.list"
    -o "Dir::Etc::sourceparts=$root/etc/apt/sources.list.d"
    -o "Dir::Etc::trustedparts=$root/etc/apt/trusted.gpg.d"
    -o "Dir::State=$root/var/lib/apt"
    -o "Dir::State::status=$root/var/lib/dpkg/status"
    -o "Dir::Cache=$root/var/cache/apt"
    -o "Dir::Log=$root/var/log/apt"
    -o "Acquire::Languages=none"
    -o "APT::Sandbox::User=root"
)

apt-get "${apt_options[@]}" update
resolved="$(apt-cache "${apt_options[@]}" policy "$package" | awk '/Candidate:/ { print $2 }')"
[ "$resolved" = "$version" ] || {
    echo "apt resolved $package $resolved, expected $version" >&2
    exit 1
}
apt-cache "${apt_options[@]}" show "$package=$version" \
    | grep -qx "Filename: $pool/$(basename "$deb")"
echo "verified: apt trusts the archive and resolves $package $version"

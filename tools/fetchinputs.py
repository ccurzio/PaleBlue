"""The Alpine packages the image is built from, fetched from Alpine's mirror and checked against its index.

    packages = fetch_packages(workdir)    # -> {'rescue': dir, 'bt': dir, 'rootfs': dir}

tools/linux/packages-*.txt name the packages. A line is either a file name (name-version-rN.apk: that
version, or the newest when the mirror has dropped it) or just a name (the newest, with whatever it
depends on that nothing else in the lists already brings). Add perl, mosquitto-clients or anything else to
packages-rootfs.txt as a bare name and it is in the next image.
"""
import base64
import hashlib
import io
import os
import re
import tarfile
import zlib

from palebluelib import download, fail, fetch, note

MIRROR = 'https://dl-cdn.alpinelinux.org/alpine'
BRANCH = 'v3.24'
ARCH = 'armv7'
LISTS = (('rescue', 'packages-rescue.txt'), ('bt', 'packages-bt.txt'), ('rootfs', 'packages-rootfs.txt'))
# What the Alpine minirootfs and the boot image already carry: never fetched as a dependency.
BASE = {'musl', 'busybox', 'busybox-binsh', 'alpine-baselayout', 'alpine-baselayout-data', 'musl-utils',
        'scanelf', 'ssl_client', 'apk-tools', 'libc-utils', 'alpine-keys', 'alpine-release', 'libapk'}

_indexes = {}


def index(repo):
    """name -> {'v': version, 'c': checksum, 'd': [dependencies], 'p': [what it provides]} for one repository."""
    if repo not in _indexes:
        data = fetch('%s/%s/%s/%s/APKINDEX.tar.gz' % (MIRROR, BRANCH, repo, ARCH))
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
            text = t.extractfile('APKINDEX').read().decode('utf-8')
        found = {}
        for block in text.split('\n\n'):
            f = {}
            for line in block.split('\n'):
                if len(line) > 2 and line[1] == ':':
                    f[line[0]] = line[2:]
            if 'P' in f and 'V' in f:
                found[f['P']] = {'v': f['V'], 'c': f.get('C'), 'd': f.get('D', '').split(),
                                 'p': f.get('p', '').split()}
        _indexes[repo] = found
    return _indexes[repo]


def apk_segments(data):
    """An apk is three gzip streams one after another: signature, control data, files."""
    out = []
    off = 0
    while off < len(data):
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        d.decompress(data[off:])
        end = len(data) - len(d.unused_data)
        if end <= off:
            break
        out.append(data[off:end])
        off = end
    return out


def apk_mismatch(path, csum):
    """Why a package is not the one the index describes, or None. Checks the control segment against the
    index's checksum and the files against the datahash in the control segment; the signature is apk's to
    check and nothing here can."""
    if not csum:
        return 'the package index carries no checksum for it'
    algo = {'Q1': 'sha1', 'Q2': 'sha256'}.get(csum[:2])
    if not algo:
        return 'the index checksum %s is in a form this script does not know' % csum
    with open(path, 'rb') as f:
        data = f.read()
    try:
        segments = apk_segments(data)
        if len(segments) < 3:
            return 'not an apk: %d gzip streams, wanted 3' % len(segments)
        want = base64.b64decode(csum[2:])
        got = hashlib.new(algo, segments[1]).digest()
        if got != want:
            return 'its control data is %s, the index says %s' % (got.hex(), want.hex())
        with tarfile.open(fileobj=io.BytesIO(segments[1]), mode='r:gz') as t:
            info = t.extractfile('.PKGINFO').read().decode('utf-8', 'replace')
    except Exception as e:
        return 'it does not read as an apk: %s' % e
    m = re.search(r'^datahash = (\w+)$', info, re.M)
    if not m:
        return 'its control data names no datahash'
    got = hashlib.sha256(segments[2]).hexdigest()
    if got != m.group(1):
        return 'its files hash to %s, its own control data says %s' % (got, m.group(1))
    return None


def lookup(name):
    for repo in ('main', 'community'):
        entry = index(repo).get(name)
        if entry:
            return repo, entry
    return None, None


def get_apk(name, want, dest):
    """One package into dest: version want when the mirror has it, else the newest. Returns its path."""
    repo, entry = lookup(name)
    if not entry:
        fail('%s is in neither main nor community of Alpine %s' % (name, BRANCH))
    have = entry['v']
    if want and have != want:
        note('%s %s is gone from Alpine %s; taking %s' % (name, want, BRANCH, have))
    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, '%s-%s.apk' % (name, have))
    if os.path.exists(out):
        bad = apk_mismatch(out, entry['c'])
        if bad:
            fail('%s does not match Alpine %s: %s. Delete it and run this again.' % (out, BRANCH, bad))
        return out
    url = '%s/%s/%s/%s/%s-%s.apk' % (MIRROR, BRANCH, repo, ARCH, name, have)
    unchecked = out + '.unchecked'
    download(url, unchecked)
    bad = apk_mismatch(unchecked, entry['c'])
    if bad:
        os.remove(unchecked)
        fail('%s does not match the package index: %s' % (url, bad))
    os.replace(unchecked, out)
    return out


def read_list(path):
    """[(name, version or None)] from a package list; a line is name-version-rN.apk or a bare name."""
    out = []
    with open(path) as f:
        for line in f:
            a = line.split('#', 1)[0].strip()
            if not a or a.startswith('busybox-static-'):
                continue
            m = re.match(r'^(.+?)-(\d[^-]*-r\d+)\.apk$', a)
            out.append((m.group(1), m.group(2)) if m else (a, None))
    return out


def providers():
    """What provides each so:/cmd:/pc: name, and each package under its own name."""
    out = {}
    for repo in ('main', 'community'):
        for name, e in index(repo).items():
            out.setdefault(name, name)
            for p in e['p']:
                out.setdefault(re.split(r'[=<>~]', p)[0], name)
    return out


def dependencies(names, have):
    """The packages `names` need that are not in `have` or BASE, found through the index's D: lines."""
    prov = providers()
    need = []
    seen = set(have) | BASE
    todo = list(names)
    while todo:
        n = todo.pop()
        _, e = lookup(n)
        if not e:
            continue
        for d in e['d']:
            if d.startswith('!'):
                continue
            who = prov.get(re.split(r'[=<>~]', d)[0])
            if who and who not in seen:
                seen.add(who)
                need.append(who)
                todo.append(who)
    return need


def fetch_packages(workdir):
    """Fetch every package the lists name, and what the bare names need, into workdir/apks-*; returns the directories."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'linux')
    dirs = {}
    listed = {}
    for key, fname in LISTS:
        dirs[key] = os.path.join(workdir, 'apks-' + key)
        listed[key] = read_list(os.path.join(root, fname))
    everything = {n for items in listed.values() for n, _ in items}
    for key, _ in LISTS:
        for name, want in listed[key]:
            get_apk(name, want, dirs[key])
    bare = [n for n, v in listed['rootfs'] if v is None]
    for name in dependencies(bare, everything):
        note('%s: needed by %s' % (name, ', '.join(bare)))
        get_apk(name, None, dirs['rootfs'])
    return dirs

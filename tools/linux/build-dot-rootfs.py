#!/usr/bin/env python3
"""Build the Echo Dot's root filesystem tarball, to inspect it or to hand to the installer.

    python3 tools/linux/build-dot-rootfs.py --out build/rootfs.tar.gz
    python3 tools/install-dot.py --rootfs build/rootfs.tar.gz

install-dot.py builds the same thing itself when it is not given one, so this is only for when you want
the tarball on its own. Every package comes from Alpine (tools/linux/packages-*.txt); wmtup, btbridge,
bluealsa and busybox come out of the signed release (tools/dotimage.py); everything else is
tools/linux/rootfs, copied in as it stands. Nothing of any one unit goes in: no firmware (each unit
adopts its own), no Wi-Fi, no keys. Windows, Linux and macOS alike; needs Python 3.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dotimage import Inputs, build_rootfs  # noqa: E402
from palebluelib import default_dir  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(default_dir('PALEBLUE_WORK', 'build'), 'rootfs.tar.gz'))
    a = ap.parse_args()
    work = default_dir('PALEBLUE_WORK', 'build')
    inp = Inputs(work)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    build_rootfs(inp, a.out)
    print('rootfs -> %s' % a.out)


if __name__ == '__main__':
    main()

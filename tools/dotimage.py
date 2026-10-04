"""The Dot's image, built here: the root filesystem and the boot image, shared by install-dot.py,
update-boot.py and linux/build-dot-rootfs.py.

What comes from where:
  Alpine's mirror   every package (tools/linux/packages-*.txt), checked against Alpine's index
  TECHO5's release  the Bluetooth kernel, the Wi-Fi bring-up (wmtup), btbridge, bluealsa and a static
                    busybox, checked against the release's signed manifest. Only those files are taken
                    out of the release; nothing else in it is used or installed.
  this repository   the rest: tools/linux/rootfs and tools/linux/init
"""
import os
import subprocess
import sys

from fetchinputs import fetch_packages
from palebluelib import Release, alpine, fail, repo_root, tar_read

RELEASE_REPO = 'HuskerMinion/techo5-dot'
RELEASE_TAG = 'dot-v0.5.55'
KERNEL_ASSET = 'techo5-dot-kernel-bt.zImage-dtb'
# member of the release's root filesystem -> file name here
BINARIES = (('usr/local/bin/wmtup', 'wmtup'), ('usr/local/bin/btbridge', 'btbridge'),
            ('usr/bin/bluealsa', 'bluealsa'), ('bin/busybox.static', 'busybox.static'))
LINUX = os.path.join(repo_root(), 'tools', 'linux')


def version():
    """PaleBlue Linux's version: VERSION_ID in the image's own /etc/os-release, the one place it is written."""
    with open(os.path.join(LINUX, 'rootfs', 'etc', 'os-release')) as f:
        for line in f:
            if line.startswith('VERSION_ID='):
                return line.split('=', 1)[1].strip().strip('"')
    fail('tools/linux/rootfs/etc/os-release has no VERSION_ID')


class Inputs:
    """Everything an image is made of, downloaded into workdir."""

    def __init__(self, workdir):
        os.makedirs(workdir, exist_ok=True)
        rel = Release(RELEASE_REPO, RELEASE_TAG, workdir)
        self.version = rel.version
        # PALEBLUE_KERNEL: a kernel you built (tools/linux/build-kernel.sh) instead of the release's.
        self.kernel = os.environ.get('PALEBLUE_KERNEL') or rel.asset(KERNEL_ASSET)
        if not os.path.exists(self.kernel):
            fail('no kernel at %s' % self.kernel)
        tarball = rel.rootfs('arm-dot')
        for member, name in BINARIES:
            data = tar_read(tarball, member)
            if data is None:
                fail('the release root filesystem has no %s' % member)
            setattr(self, name.replace('.', '_'), os.path.join(rel.dir, name))
            with open(os.path.join(rel.dir, name), 'wb') as f:
                f.write(data)
        self.alpine = alpine(workdir)
        self.apks = fetch_packages(workdir)


def build_rootfs(inp, out):
    """The root filesystem tarball a slot is unpacked from."""
    j = os.path.join
    cmd = [sys.executable, j(LINUX, 'mkrootfs.py'), '--rootfs', inp.alpine,
           '--apkdir', inp.apks['rescue'], '--apkdir', inp.apks['bt'], '--apkdir', inp.apks['rootfs'],
           '--add', inp.busybox_static + '=/bin/busybox.static', '--add', inp.wmtup + '=/usr/local/bin/wmtup',
           '--add', inp.btbridge + '=/usr/local/bin/btbridge', '--add', inp.bluealsa + '=/usr/bin/bluealsa',
           '--overlay', j(LINUX, 'rootfs'), '--release', 'PaleBlue Linux ' + version(), '-o', out]
    if subprocess.run(cmd).returncode != 0:
        fail('building the root filesystem failed')


def build_boot_image(recovery, out, inp, kernel=True):
    """A unit's boot image: its own recovery backup's header (and kernel, unless kernel is False), the
    rescue initramfs on Alpine's base, and the slot, network and TWRP tools."""
    j = os.path.join
    mk = [sys.executable, j(LINUX, 'mkimage.py'), '--kernel-image', recovery, '--rootfs', inp.alpine,
          '--init', j(LINUX, 'init'), '--add', inp.busybox_static + '=/bin/busybox.static',
          '--add', inp.wmtup + '=/usr/local/bin/wmtup',
          '--cmdline-drop', 'skip_initramfs', '--cmdline-drop', 'root=', '--cmdline-drop', 'dm=',
          '--cmdline-append', 'paleblue.stay_minutes=15', '-o', out]
    if kernel:
        mk += ['--kernel', inp.kernel]
    for apk in sorted(os.listdir(inp.apks['rescue'])):
        if apk.endswith('.apk'):
            mk += ['--apk', j(inp.apks['rescue'], apk)]
    for t in ('slotctl', 'paleblue-net', 'wifi-set', 'to-twrp', 'paleblue-firewall', 'paleblue-rootpw'):
        mk += ['--script', j(LINUX, 'rootfs', 'usr', 'local', 'sbin', t) + '=/usr/local/sbin/' + t]
    if subprocess.run(mk).returncode != 0:
        fail('building the boot image failed')

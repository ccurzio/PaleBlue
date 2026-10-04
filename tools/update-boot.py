#!/usr/bin/env python3
"""Rebuild a Dot's boot image (kernel + initramfs) and put it in the recovery partition of a unit already
running this Linux, over SSH.

    python3 tools/update-boot.py --serial <serial> --address <address>

The root filesystem is the slot and the boot image is the recovery partition: the image is built per unit
from its own recovery backup (kept by the installer) and is never published. Use this after changing
tools/linux/init or the rescue packages, so the change reaches a unit without going back through TWRP.

The previous image stays in the store as linux-prev.img, and linux.img (what back-to-linux.sh and to-twrp
use) is only replaced once the new image has booted healthy. Needs SSH to the unit (root, password
"password" unless you changed it). Windows, Linux and macOS alike; needs Python 3 and ssh.

If the new image does not come up: when its kernel boots but the system does not, the unit stays in the
new image's rescue environment after five tries (USB console, SSH). When the kernel itself does not boot
there is no rescue, because the rescue environment is in the same image. The way back is then the unit's
own TWRP: hold Volume-Down while powering on for fastboot, `fastboot flash recovery
backups/<serial>/recovery.img`, let it boot TWRP, and `adb shell sh /cache/paleblue/back-to-linux.sh` puts
back the last image that booted healthy.
"""
import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palebluelib import default_dir, fail, md5, need, note, run_main, step  # noqa: E402
from dotimage import Inputs, build_boot_image  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--address', required=True, help="the unit's address on your network")
    ap.add_argument('--backups', default=default_dir('PALEBLUE_BACKUPS', 'backups'))
    ap.add_argument('--work', default=default_dir('PALEBLUE_WORK', 'build'))
    ap.add_argument('--ssh', default='ssh')
    a = ap.parse_args()
    need(a.ssh, 'an OpenSSH client (built into Windows 10 and later, Linux and macOS)')

    unit = os.path.join(a.backups, a.serial)
    recovery = os.path.join(unit, 'recovery.img')
    if not os.path.exists(recovery):
        fail('no recovery backup for %s at %s (the installer keeps one; --backups points elsewhere)' % (a.serial, recovery))
    os.makedirs(a.work, exist_ok=True)
    image = os.path.join(unit, 'paleblue-linux-next.img')

    step('boot image')
    inp = Inputs(a.work)
    build_boot_image(recovery, image, inp)
    want = md5(image)
    size = os.path.getsize(image)

    target = 'root@' + a.address
    ssh = [a.ssh, '-o', 'ConnectTimeout=10', target]

    def remote(command):
        r = subprocess.run(ssh + [command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return r.returncode, r.stdout.decode('utf-8', 'replace').strip()

    # A boot is told apart from the one before it by the kernel's boot id, so the healthy mark the old boot
    # left in MISC is never mistaken for the new one's. Read before anything is written: an empty id would
    # be "in" every later reply, and the wait below could never see the new boot as healthy.
    rc, out = remote('cat /proc/sys/kernel/random/boot_id')
    m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', out)
    if rc != 0 or not m:
        fail("could not read the running boot's id over SSH from %s (%s); nothing was flashed" % (a.address, out or 'no output'))
    boot_id = m.group(0)

    step('flashing %s' % a.address)
    with open(image, 'rb') as f:
        if subprocess.run(ssh + ['cat > /store/paleblue/linux-next.img'], stdin=f).returncode != 0:
            fail('sending the image failed')
    flash = ('set -e\nS=/store/paleblue\n'
             '[ "$(md5sum < $S/linux-next.img | cut -d" " -f1)" = %(w)s ] || { echo "transfer mismatch"; exit 1; }\n'
             'cp -f $S/linux.img $S/linux-prev.img\n'
             'dd if=$S/linux-next.img of=/dev/mmcblk0p12 bs=1048576 2>/dev/null\nsync\n'
             'got=$(head -c %(n)d /dev/mmcblk0p12 | md5sum | cut -d" " -f1)\n'
             '[ "$got" = %(w)s ] || { dd if=$S/linux-prev.img of=/dev/mmcblk0p12 bs=1048576 2>/dev/null; sync; echo "read back $got; previous image restored"; exit 1; }\n'
             'echo "flashed $got"\n') % {'w': want, 'n': size}
    _, out = remote(flash)
    note(out)
    if 'flashed ' + want not in out:
        fail('flashing failed')

    remote('sync; (sleep 2; reboot) >/dev/null 2>&1 &')
    note('rebooting into the new image; waiting for a healthy boot')
    time.sleep(40)
    healthy = False
    deadline = time.time() + 6 * 60
    while time.time() < deadline:
        r = subprocess.run([a.ssh, '-o', 'ConnectTimeout=4', '-o', 'BatchMode=yes', target,
                            'cat /proc/sys/kernel/random/boot_id; dd if=/dev/mmcblk0p8 bs=512 skip=14 count=1 2>/dev/null | tr -d "\\000"'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        text = r.stdout.decode('utf-8', 'replace')
        if 'healthy' in text and boot_id not in text:
            healthy = True
            break
        time.sleep(10)
    if not healthy:
        fail('the unit did not report a healthy boot.\n'
             '   If the new kernel boots, the unit stays in its rescue environment after five tries: reach it on\n'
             '   the USB console or over SSH.\n'
             '   If the new kernel does not boot at all (no console, no SSH), there is no rescue to reach, since it\n'
             '   is in the same image. Go back through TWRP: hold Volume-Down while powering on for fastboot, then\n'
             '     fastboot flash recovery %s\n'
             '   let it boot TWRP, and run: adb shell sh /cache/paleblue/back-to-linux.sh\n'
             '   That puts back the last Linux image that booted healthy (linux.img in the store was not replaced).'
             % recovery)
    _, out = remote('mv -f /store/paleblue/linux-next.img /store/paleblue/linux.img; sync; uname -r')
    note('kernel %s' % out)
    print("Done: %s booted the new image healthy; it is now the unit's linux.img." % a.serial)


if __name__ == '__main__':
    run_main(main)

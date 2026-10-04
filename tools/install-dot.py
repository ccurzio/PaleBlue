#!/usr/bin/env python3
"""Put PaleBlue Linux on an unlocked Echo Dot 2 (biscuit), from Fire OS or TWRP, in one run.

    python3 tools/install-dot.py --hostname kitchen
    python3 tools/install-dot.py --hostname kitchen --ip 192.168.1.50/24 --gateway 192.168.1.1
    python3 tools/install-dot.py --hostname kitchen --serial <serial> --dry-run
    python3 tools/install-dot.py --hostname kitchen --wifi MyNetwork

Windows, Linux and macOS alike; needs Python 3 and adb. Stops at the first thing not right:

  1. checks the device: biscuit, Fire OS 6, adb as root, a saved Wi-Fi network (or asks for one)
  2. backs up every partition that boots the unit into backups/<serial>/, each checked by md5
  3. fetches Alpine's packages and the few files taken from the signed release (tools/dotimage.py),
     builds the root filesystem (or takes yours, --rootfs) and this unit's boot image
  4. writes the boot image to the recovery partition and reads it back
  5. unpacks the root filesystem into slot a of the store on the cache partition
  6. arms the Linux boot, reboots, and waits on the unit's USB console for a healthy boot

The result: Alpine with SSH (root, password "password"), Wi-Fi, Bluetooth and your own service
(docs/paleblue.md). Prerequisites: unlocked with amonet, Fire OS 6 in the system slots, and either in
TWRP or in Fire OS with adb as root.
"""
import argparse
import glob
import ipaddress
import os
import re
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palebluelib import wifi_conf as paleblue_wifi_conf  # noqa: E402
from palebluelib import (CONSOLE_DOT, Adb, Console, ask, ask_wifi, check_serial_access, console_hint,  # noqa: E402
                       default_dir, fail, head_is_android, interactive, md5, need, note, pick_unit,
                       repo_root, run_main, step)
from dotimage import Inputs, build_boot_image, build_rootfs  # noqa: E402

PARTS = ['preloader', 'kb', 'dkb', 'lk_a', 'lk_b', 'tee1', 'tee2', 'expdb', 'misc', 'persist', 'boot_a', 'boot_b', 'recovery']

SLOT_SCRIPT = r'''set -e
T=$1
B=$T/busybox
S=/cache/paleblue
mkdir -p $S/slots
# A slot a from an earlier install is set aside until the new one has unpacked, then removed.
rm -rf $S/slots/a.old $S/slots/b.old
if [ -d $S/slots/a ]; then mv $S/slots/a $S/slots/a.old; fi
mkdir -p $S/slots/a
cd $S/slots/a
$B tar xzf $T/rootfs.tar.gz
[ -x $S/slots/a/sbin/init ] || { echo "unpacked slot has no /sbin/init"; exit 1; }
# The unit's firmware moves from the old slot into the store, where both slots find it.
if [ ! -e $S/firmware/WIFI_RAM_CODE_8163 ] && [ -e $S/slots/a.old/etc/firmware/WIFI_RAM_CODE_8163 ]; then
	mkdir -p $S/firmware; cp $S/slots/a.old/etc/firmware/* $S/firmware/
fi
rm -rf $S/slots/a.old
# Installed and checked from here, so it starts good rather than on trial. A slot b is left as it is.
: > $S/.paleblue-store
echo good > $S/slots/a.state
echo a > $S/active
rm -f $S/rescue
sync
echo "slot a: $(cat $S/slots/a/etc/paleblue-release), $(ls $S/slots/a/bin | wc -l) commands in /bin"
'''


def is_paleblue_image(path):
    """A boot image built here: every one carries paleblue.* words in its header's command line (techo5.* before
    this was renamed)."""
    with open(path, 'rb') as f:
        head = f.read(576)
    return head.startswith(b'ANDROID!') and (b'paleblue' in head[64:576] or b'techo5' in head[64:576])


def network_settings(a):
    """The hostname, and the static address when one is asked for, checked before anything touches the
    unit. Returns (hostname, static) where static is None for DHCP or a dict of ADDR, NETMASK, GATEWAY, DNS."""
    if not re.match(r'^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$', a.hostname):
        fail("--hostname must be 1 to 63 letters, digits and hyphens, not starting or ending with a hyphen: '%s'" % a.hostname)
    if not a.ip:
        if a.gateway or a.dns:
            fail('--gateway and --dns only go with --ip')
        return a.hostname, None
    try:
        iface = ipaddress.IPv4Interface(a.ip)
    except ValueError:
        fail("--ip must be an IPv4 address with its prefix length, like 192.168.1.50/24: '%s'" % a.ip)
    if '/' not in a.ip:
        fail('--ip needs the prefix length, like %s/24' % a.ip)
    if not a.gateway:
        fail('--ip needs --gateway')
    try:
        gw = ipaddress.IPv4Address(a.gateway)
        dns = [ipaddress.IPv4Address(x.strip()) for x in (a.dns or a.gateway).split(',') if x.strip()]
    except ValueError as e:
        fail('--gateway and --dns must be IPv4 addresses: %s' % e)
    if gw not in iface.network or gw == iface.ip:
        fail('--gateway %s is not another address on %s' % (gw, iface.network))
    if iface.ip in (iface.network.network_address, iface.network.broadcast_address):
        fail('--ip %s is the network or broadcast address of %s' % (iface.ip, iface.network))
    return a.hostname, {'ADDR': str(iface.ip), 'NETMASK': str(iface.netmask), 'GATEWAY': str(gw),
                        'DNS': ' '.join(str(d) for d in dns)}


def ssh_open(address, port=22):
    try:
        with socket.create_connection((address, port), timeout=2):
            return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--serial', help="the unit's adb serial (adb devices); found, or asked for, when missing")
    ap.add_argument('--hostname', required=True, help="the unit's name on your network (letters, digits, hyphens)")
    ap.add_argument('--ip', help='a static IPv4 address with its prefix length, like 192.168.1.50/24 (default: DHCP)')
    ap.add_argument('--gateway', help='the router, with --ip')
    ap.add_argument('--dns', help='DNS servers, comma separated, with --ip (default: the gateway)')
    ap.add_argument('--rootfs', help="a root filesystem you built (tools/linux/build-dot-rootfs.py) instead of building one")
    ap.add_argument('--wifi', dest='wifi_ssid', help="a Wi-Fi network to join instead of the one Fire OS saved (asks for the passphrase)")
    ap.add_argument('--wifi-passphrase-file', help='a file holding the --wifi passphrase, for running from a script')
    ap.add_argument('--dry-run', action='store_true', help='checks, backups, downloads and builds; write nothing to the unit')
    a = ap.parse_args()
    a.backups = default_dir('PALEBLUE_BACKUPS', 'backups')
    a.work = default_dir('PALEBLUE_WORK', 'build')
    a.adb = 'adb'
    hostname, static = network_settings(a)
    need(a.adb, 'install the Android platform tools (adb)')
    a.serial = pick_unit(a.serial, a.adb, ('device', 'recovery'), 'Echo Dot', consoles=(CONSOLE_DOT,))
    adb = Adb(a.serial, a.adb)

    # ---------------------------------------------------------------------------------------- 1
    # ---------------------------------------------------------------------------------------- 1
    step('device %s' % a.serial)
    state = adb.state()
    if state not in ('device', 'recovery'):
        fail("adb does not see %s (state: '%s'). Boot it into Fire OS (root adb) or TWRP with USB connected.%s"
             % (a.serial, state, console_hint((CONSOLE_DOT,))))
    twrp = state == 'recovery'
    if 'biscuit' not in adb.sh('getprop ro.product.device; getprop ro.build.product'):
        fail('%s is not an Echo Dot 2nd gen (biscuit)' % a.serial)
    ident = adb.sh('id')
    if not ident.startswith('uid=0'):
        fail("adb is not root on %s (%s). EchoLocal's install or boot-root.zip gives root adb; or boot TWRP." % (a.serial, ident))
    slot = adb.sh('getprop ro.boot.slot_suffix')
    bn = '/dev/block/platform/bootdevice/by-name'
    if adb.sh('test -e %s/recovery && echo yes' % bn) != 'yes':
        bn = adb.sh('for d in /dev/block/platform/*/by-name /dev/block/by-name; do [ -e $d/recovery ] && { echo $d; break; }; done')
        if not bn:
            fail('no by-name partition links on %s' % a.serial)
    if twrp:
        # TWRP runs from RAM, so writing the recovery partition under it is safe. userdata and cache are
        # mounted here if TWRP has not already, and the Fire OS release is read off the slot's system.
        stage = '/tmp/paleblue'
        mounts = adb.sh("grep -q ' /data ' /proc/mounts || mount -t ext4 %s/userdata /data; "
                        "grep -q ' /cache ' /proc/mounts || mount -t ext4 %s/cache /cache; "
                        "grep -q ' /data ' /proc/mounts && echo data; grep -q ' /cache ' /proc/mounts && echo cache" % (bn, bn))
        if 'data' not in mounts or 'cache' not in mounts:
            fail('TWRP could not mount userdata and cache on %s (%s)' % (a.serial, mounts))
        fireos = adb.sh("mkdir -p /tmp/t5sys; mount -t ext4 -o ro %s/system%s /tmp/t5sys 2>/dev/null; "
                        "sed -n 's/^ro.build.version.name=//p' /tmp/t5sys/system/build.prop 2>/dev/null; umount /tmp/t5sys 2>/dev/null" % (bn, slot))
    else:
        stage = '/data/local/tmp/paleblue'
        fireos = adb.sh('getprop ro.build.version.name')
    if 'Fire OS 6' not in fireos:
        fail("%s has '%s' in slot %s; this installer is for Fire OS 6 (32-bit kernel)" % (a.serial, fireos, slot))
    note('biscuit, %s, slot %s, %s' % (fireos, slot, 'in TWRP' if twrp else 'root adb in Fire OS'))

    # Wi-Fi: the network Fire OS saved, one set on the unit before (wifi-set), or one given here. Only the
    # derived key goes to the unit (palebluelib.wifi_conf).
    wifi = adb.sh('sed -n "s/^[ \\t]*ssid=//p" /data/misc/wifi/wpa_supplicant.conf 2>/dev/null | head -1')
    own_wifi = adb.sh('test -s /data/paleblue-linux/wifi.conf -o -s /data/techo5-linux/wifi.conf && echo yes') == 'yes'
    wifi_conf = None
    if a.wifi_ssid or (not wifi and not own_wifi):
        ssid = a.wifi_ssid
        if not ssid:
            note('%s has no saved Wi-Fi network' % a.serial)
            if not interactive():
                fail('%s has no saved Wi-Fi network: pass --wifi (the passphrase is asked for, or read from --wifi-passphrase-file)' % a.serial)
            ssid = ask('Wi-Fi network name')
        if a.wifi_passphrase_file:
            with open(a.wifi_passphrase_file) as f:
                # Only the line's end goes: a passphrase may begin or end with spaces.
                wifi_conf = paleblue_wifi_conf(ssid, f.read().rstrip('\r\n'))
        else:
            wifi_conf = ask_wifi(ssid)
        note("will join '%s'" % ssid)
    elif own_wifi:
        note('Wi-Fi network set on the unit before (wifi-set); keeping it')
    else:
        note('saved Wi-Fi network %s' % wifi)
    ip = None
    if not twrp:
        ip = adb.sh('ifconfig wlan0 2>/dev/null | sed -n "s/.*inet addr:\\([0-9.]*\\).*/\\1/p" | head -1') or adb.sh('getprop dhcp.wlan0.ipaddress') or None
        if ip:
            note('address in Fire OS: %s' % ip)

    # ---------------------------------------------------------------------------------------- 2
    unit = os.path.join(a.backups, a.serial)
    os.makedirs(unit, exist_ok=True)
    step('backups to %s' % unit)
    for p in PARTS:
        out = os.path.join(unit, p + '.img')
        # amonet's TWRP points preloader, lk and tee at decoy files in /tmp/ota-decoy, so an OTA flashed
        # from it cannot overwrite the unlock. The real partitions are the *_real links, and the preloader
        # is the eMMC boot area. A copy of a decoy would restore nothing.
        src = adb.sh('s=%s/%s; [ -e ${s}_real ] && s=${s}_real; case $(readlink $s) in /tmp/*) if [ %s = preloader ]; '
                     'then s=/dev/block/mmcblk0boot0; else s=; fi;; esac; echo $s' % (bn, p, p))
        if not src:
            fail('%s on %s points at a decoy with no real partition beside it' % (p, a.serial))
        dev = adb.sh('md5sum %s' % src).split(' ')[0]
        if os.path.exists(out) and md5(out) == dev:
            note('%s already backed up' % p)
            continue
        same = [f for f in glob.glob(os.path.join(unit, p + '-*.img')) if md5(f) == dev]
        if same:
            note('%s already backed up as %s' % (p, os.path.basename(same[0])))
            continue
        if os.path.exists(out) and p == 'recovery' and head_is_android(out):
            # A recovery backup that no longer matches is TWRP from before a Linux image went in: the way back.
            note("recovery: keeping the earlier backup (the device's recovery has changed since)")
            continue
        dest = out if not os.path.exists(out) else os.path.join(unit, '%s-%s.img' % (p, time.strftime('%Y%m%d-%H%M%S')))
        tmp = dest + '.partial'
        # cat through exec-out, byte for byte; kept only once its md5 matches the device.
        if adb.exec_out_to_file('cat ' + src, tmp) != 0:
            fail('reading %s failed' % p)
        got = md5(tmp)
        if got != dev:
            os.remove(tmp)
            fail('%s copy does not match the device (%s vs %s)' % (p, got, dev))
        os.replace(tmp, dest)
        note('%s %d bytes, md5 ok%s' % (p, os.path.getsize(dest), '' if dest == out else ' (changed since %s.img; saved as %s)' % (p, os.path.basename(dest))))
    recovery = os.path.join(unit, 'recovery.img')
    if not head_is_android(recovery):
        fail('recovery backup is not an Android boot image')
    if is_paleblue_image(recovery):
        # The recovery partition already held our Linux when this backup was first taken. It is not a
        # way back to TWRP, and as the donor for the new image it would hand over a header already edited
        # for Linux (and perhaps the Bluetooth kernel) instead of the unit's own.
        fail("%s is one of our Linux boot images, not the unit's TWRP. Put this unit's TWRP image there "
             "(or boot TWRP, flash it to recovery and move this file aside), then run this again." % recovery)

    # ---------------------------------------------------------------------------------------- 3
    step("packages, and this unit's boot image")
    os.makedirs(a.work, exist_ok=True)
    inp = Inputs(a.work)
    if a.rootfs:
        rootfs = os.path.abspath(a.rootfs)
        if not os.path.exists(rootfs):
            fail('no file at %s' % rootfs)
    else:
        rootfs = os.path.join(a.work, 'rootfs.tar.gz')
        build_rootfs(inp, rootfs)
    image = os.path.join(unit, 'paleblue-linux.img')
    build_boot_image(recovery, image, inp)
    note('boot image %d bytes, root filesystem %d bytes' % (os.path.getsize(image), os.path.getsize(rootfs)))

    if a.dry_run:
        print('\nDry run: checks, backups and builds done; nothing written to %s.\n  boot image:      %s\n  root filesystem: %s' % (a.serial, image, rootfs))
        return
    check_serial_access(must=False)

    # ---------------------------------------------------------------------------------------- 4
    step('boot image into the recovery partition')
    # The image goes into the store first and stays there: to-twrp and back-to-linux.sh use that copy.
    # A unit installed before the rename keeps its store (firmware, TWRP copy) and state (Wi-Fi, root
    # password) under the old names: moved to the new ones. Its second slot is the old system, which
    # cannot boot under the new init, so it goes; slot a is replaced below.
    adb.sh('[ -d /cache/techo5 ] && [ ! -e /cache/paleblue ] && mv /cache/techo5 /cache/paleblue; '
           '[ -e /cache/paleblue/.techo5-store ] && mv /cache/paleblue/.techo5-store /cache/paleblue/.paleblue-store; '
           'rm -rf /cache/paleblue/slots/b /cache/paleblue/slots/b.state /cache/paleblue/rescue /cache/techo5; '
           '[ -d /data/techo5-linux ] && [ ! -e /data/paleblue-linux ] && mv /data/techo5-linux /data/paleblue-linux; '
           'rm -rf /data/techo5-linux /data/local/tmp/techo5; true')
    adb.sh('mkdir -p %s /cache/paleblue' % stage)
    adb.push(image, '/cache/paleblue/linux.img')
    adb.push(inp.busybox_static, stage + '/busybox')
    want = md5(image)
    got = adb.sh('chmod 755 %s/busybox; dd if=/cache/paleblue/linux.img of=%s/recovery bs=1048576 2>/dev/null; sync; %s/busybox head -c %d %s/recovery | md5sum'
                 % (stage, bn, stage, os.path.getsize(image), bn)).split(' ')[0]
    if got != want:
        fail('recovery partition reads back %s, wanted %s. The TWRP backup is at %s.' % (got, want, recovery))
    note('written and read back, md5 %s' % got)

    # ---------------------------------------------------------------------------------------- 5
    step('root filesystem into slot a')
    adb.push(rootfs, stage + '/rootfs.tar.gz')
    script = os.path.join(a.work, 'paleblue-slot.sh')
    with open(script, 'w', newline='\n') as f:
        f.write(SLOT_SCRIPT)
    adb.push(script, stage + '/slot.sh')
    os.remove(script)
    result = adb.sh('sh %s/slot.sh %s 2>&1' % (stage, stage))
    if 'slot a: ' not in result:
        fail('installing the slot failed: %s' % result)
    note(result)
    # The way back to TWRP without a PC: the unit's own TWRP (its recovery backup, checked in step 2 not to
    # be a Linux image) and the script that undoes it.
    adb.push(recovery, '/cache/paleblue/twrp.img')
    if adb.sh('md5sum /cache/paleblue/twrp.img').split(' ')[0] != md5(recovery):
        fail('the TWRP copy on the unit does not match %s' % recovery)
    adb.push(os.path.join(repo_root(), 'tools', 'linux', 'back-to-linux.sh'), '/cache/paleblue/back-to-linux.sh')
    note('TWRP copy kept on the unit (to-twrp puts it back; /cache/paleblue/back-to-linux.sh returns)')

    # Wi-Fi goes to userdata, where it outlasts slots. Anything an earlier EchoLocal install left in
    # /data/misc/echolocal (its name, key, wake word models, SSH keys) is not used by this image: removed.
    # The name, and the address: written every install, so leaving out --ip puts a unit that had one back on DHCP.
    adb.sh('mkdir -p /data/paleblue-linux')
    for name, text in (('hostname', hostname + '\n'),
                       ('static-ip', ''.join('%s=%s\n' % kv for kv in static.items()) if static else None)):
        remote = '/data/paleblue-linux/' + name
        if text is None:
            adb.sh('rm -f ' + remote)
            continue
        local = os.path.join(a.work, name)
        with open(local, 'w', newline='\n') as f:
            f.write(text)
        adb.push(local, remote)
        os.remove(local)
        adb.sh('chmod 644 ' + remote)
    note("hostname '%s', %s" % (hostname, 'static address %s via %s' % (static['ADDR'], static['GATEWAY']) if static else 'address by DHCP'))
    if wifi_conf:
        local = os.path.join(a.work, 'wifi.conf')
        with open(local, 'w', newline='\n') as f:
            f.write(wifi_conf)
        adb.push(local, '/data/paleblue-linux/wifi.conf')
        os.remove(local)
        adb.sh('chmod 600 /data/paleblue-linux/wifi.conf')
        note('Wi-Fi network written to the unit')
    if adb.sh('test -e /data/misc/echolocal && echo yes') == 'yes':
        adb.sh('rm -rf /data/misc/echolocal')
        note('removed the leftovers of an earlier EchoLocal install (/data/misc/echolocal)')

    # ---------------------------------------------------------------------------------------- 6
    step('arming the Linux boot and rebooting')
    adb.sh("printf 'PALEBLUE-TRIES 0 installed\\n' | dd of=%s/misc bs=512 seek=14 count=1 conv=notrunc 2>/dev/null; "
           'rm -f %s/rootfs.tar.gz %s/busybox %s/slot.sh; sync' % (bn, stage, stage, stage))
    adb.reboot('recovery')

    # The unit is found on its USB serial console by its own serial number and asked how the boot went:
    # that works whatever address DHCP hands Linux, and from TWRP, where no address was known at all.
    note("waiting for the unit's Linux console on USB")
    console = Console(a.serial, CONSOLE_DOT)
    query = ("echo slot=$(cat /run/paleblue/slot 2>/dev/null); echo release=$(cat /etc/paleblue-release 2>/dev/null); "
             "echo ip=$(ifconfig wlan0 2>/dev/null | sed -n 's/.*inet addr:\\([0-9.]*\\).*/\\1/p'); echo ssh=$(pidof dropbear); "
             "echo tries=$(dd if=/dev/mmcblk0p8 bs=512 skip=14 count=1 2>/dev/null | tr -d '\\000')")
    healthy, said, told = False, '', ''
    start = time.time()
    deadline, ticked = start + 8 * 60, start
    while time.time() < deadline:
        out = console.run(query, 8)
        if not out and time.time() - start >= 30:
            # Nothing from the console yet: say so now and then, and why, so the wait never reads as a hang.
            if time.time() - ticked >= 30:
                note('still waiting for the console (%d s of %d)' % (time.time() - start, 8 * 60))
                ticked = time.time()
            h = console.waiting_hint()
            if h and h != told:
                note(h)
                told = h
        if out:
            kv = dict(re.findall(r'^(\w+)=(.*)$', out, re.M))
            now = 'slot %s, %s, address %s, SSH %s' % (kv.get('slot'), kv.get('release'), kv.get('ip') or 'none yet',
                                                      'running' if kv.get('ssh') else 'not running')
            if now != said:
                note(now)
                said = now
            if kv.get('ip'):
                ip = kv['ip'].strip()
            # Healthy is the boot's own verdict: paleblue-health steady for 90 s (SSH up), and the try count back to 0.
            if 'healthy' in kv.get('tries', ''):
                healthy = True
                break
        time.sleep(5)
    up = False
    if ip:
        deadline = time.time() + 60
        up = ssh_open(ip)
        while not up and time.time() < deadline:
            time.sleep(5)
            up = ssh_open(ip)

    print()
    if healthy and up:
        print('Done: %s is running PaleBlue Linux, healthy, and SSH answers at %s:22.' % (a.serial, ip))
        print('      ssh root@%s  password: password   <- run passwd now (wifi-set, slotctl status, to-twrp, dotctl).' % ip)
        print('      Your service: /data/paleblue-linux/app/run')
    elif up:
        print('%s answers at %s:22, but the boot was not confirmed healthy (no console, or not within the wait).' % (a.serial, ip))
    else:
        print('Rebooted, but the unit was not confirmed up%s.' % (' (%s:22 did not answer)' % ip if ip else ''))
        print('After five boots that never become healthy it stays in rescue (paleblue-retry tries again). The USB console')
        print('shows the boot and the crumbs (tools/linux/readmisc.sh).')
        sys.exit(1)


if __name__ == '__main__':
    run_main(main)

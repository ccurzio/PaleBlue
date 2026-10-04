#!/bin/busybox.static sh
# Bring the Echo Dot up, once, from a rootfs slot. Run by busybox init as its sysinit.
#
# The same ground the initramfs covers — no devtmpfs, so /dev is made by hand; the USB gadget wants
# its function count and device class; the combo chip wants its patch searches answered — with one
# difference: this is the real root, so what runs lives here rather than being fetched from wherever
# it happened to be.
BB=/bin/busybox.static
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root

MISC=/dev/mmcblk0p8
RECOVERY=/dev/mmcblk0p12
SYSTEM=/dev/mmcblk0p14   # Android's system: the Wi-Fi firmware is adopted from it, once
STORE=/dev/mmcblk0p15    # cache: the slot store, /paleblue on it
DATA=/dev/mmcblk0p16     # userdata: state (SSH keys, your service), and the logs
S=/store/paleblue

exec > /dev/kmsg 2>&1

# The slot has to be writable: it keeps state. After a run of watchdog resets one boot came up with it
# read-only and no filesystem error recorded (errors_count 0); what did that is still open, so this
# says what it must be rather than trusting it.
$BB mount -o remount,rw / 2>/dev/null

$BB mount -t proc proc /proc 2>/dev/null
$BB mount -t sysfs sysfs /sys 2>/dev/null
$BB mount -t tmpfs -o mode=0755 tmpfs /dev 2>/dev/null
$BB mkdir -p /dev/pts /tmp /data /android /store
$BB mount -t devpts devpts /dev/pts 2>/dev/null
# The initramfs wrote which slot this is into /run before switching; a tmpfs over /run would hide it,
# so it is read first and put back after.
SLOT=$($BB cat /run/paleblue/slot 2>/dev/null)
$BB mount -t tmpfs tmpfs /run 2>/dev/null
$BB mount -t tmpfs tmpfs /tmp 2>/dev/null
# After /run is mounted, not before: a directory made first is hidden by the tmpfs, and then the
# marker the services wait for can never be written. The first slot boot waited on it for ever.
$BB mkdir -p /run/paleblue
[ -n "$SLOT" ] && echo "$SLOT" > /run/paleblue/slot

# Every command by name, not only through $BB. The unpacked slot can arrive without Alpine's /bin
# applet links — the first one did, and a bare `cat` writing the DHCP lease script then failed, so a
# lease was obtained and thrown away. Installing them here costs nothing when they are already there.
$BB --install -s 2>/dev/null
# SSH sessions get dropbear's own PATH, which has no /usr/local: the unit's tools are linked where it looks.
for t in slotctl wifi-set to-twrp paleblue-net; do $BB ln -sfn /usr/local/sbin/$t /usr/sbin/$t; done
$BB mknod -m 600 $MISC b 179 8 2>/dev/null
$BB mknod -m 600 $RECOVERY b 179 12 2>/dev/null
$BB mknod -m 600 $SYSTEM b 179 14 2>/dev/null
$BB mknod -m 600 $STORE b 179 15 2>/dev/null
$BB mknod -m 600 $DATA b 179 16 2>/dev/null
$BB mdev -s
echo 7 4 1 7 > /proc/sys/kernel/printk

say() { echo "paleblue boot: $*"; }
say "slot $($BB cat /run/paleblue/slot 2>/dev/null) release $($BB cat /etc/paleblue-release 2>/dev/null)"

# The bootloader message is the initramfs's to manage, and it has already asked for the next boot to
# be Linux too (tools/linux/init). This script used to clear it, which silently undid that: a power
# cut then came back in Android.

# The store, which the initramfs mounted for itself and which does not survive the switch into the
# slot. The slot is a directory on the same filesystem, so this is a second mount of one filesystem:
# updates unpack into the other slot through it, and the slot state lives there.
$BB mount -t ext4 -o noatime $STORE /store 2>/dev/null
say "store $([ -e $S/.paleblue-store ] && echo mounted || echo unavailable)"

$BB mount -t ext4 -o noatime $DATA /data 2>/dev/null && $BB mkdir -p /data/paleblue-linux
say "userdata $([ -d /data/paleblue-linux ] && echo mounted || echo unavailable)"
# The state (SSH keys, your service's files) and the logs are root's alone.
$BB chmod 700 /data/paleblue-linux 2>/dev/null

# --- Inbound closed except SSH and what /data/paleblue-linux/firewall-ports lists, before any network exists
# (usr/local/sbin/paleblue-firewall).
/usr/local/sbin/paleblue-firewall 2>&1 | while read -r l; do say "$l"; done

# --- USB serial console.
g=/sys/class/android_usb/android0
if [ -d $g ]; then
	echo 1 > /sys/devices/platform/mt_usb/cmode 2>/dev/null
	echo 0 > $g/enable 2>/dev/null
	echo 18d1 > $g/idVendor 2>/dev/null
	echo 4ee7 > $g/idProduct 2>/dev/null
	echo "PaleBlue Linux" > $g/iManufacturer 2>/dev/null
	echo "Echo Dot 2 Linux" > $g/iProduct 2>/dev/null
	# The unit's own serial, so the PC tells Dots apart: the installer finds this unit's COM port by it.
	sn=$($BB sed -n 's/.*androidboot.serialno=\([^ ]*\).*/\1/p' /proc/cmdline)
	[ -n "$sn" ] && echo "$sn" > $g/iSerial 2>/dev/null
	echo 1 > $g/f_acm/instances 2>/dev/null
	echo acm > $g/functions 2>/dev/null
	echo 02 > $g/bDeviceClass 2>/dev/null
	echo 1 > $g/enable 2>/dev/null
	i=0
	while [ $i -lt 15 ] && [ ! -e /dev/ttyGS0 ]; do $BB mdev -s; $BB sleep 1; i=$((i + 1)); done
	say "usb console $([ -e /dev/ttyGS0 ] && echo up || echo missing)"
fi

# --- The unit's audio coefficients (the speaker's tuning), which Fire OS keeps beside the firmware.
# Amazon's, so never in a published rootfs: every unit takes its own, exactly as it does its firmware.
adopt_audio() {
	[ -e $AA/MBCL.cfg ] && return 0
	$BB mkdir -p $AA
	if [ -d /etc/audio-algorithms ] && [ ! -L /etc/audio-algorithms ]; then
		$BB cp /etc/audio-algorithms/* $AA/ 2>/dev/null
		say "audio coefficients taken from this slot into $AA"
	elif $BB mount -t ext4 -o ro,noatime $SYSTEM /android 2>/dev/null; then
		$BB cp /android/system/vendor/etc/audio-algorithms/* $AA/ 2>/dev/null
		$BB umount /android
		say "audio coefficients adopted from the system partition: $($BB ls $AA 2>/dev/null | $BB wc -l) files"
	else
		say "no audio coefficients to adopt: the speaker plays untuned"
	fi
	$BB sync
}

# --- Wi-Fi firmware. The unit's own, adopted once into the store and shared by both slots, so a slot
# that arrives by update needs nothing from Android. It is Amazon's, so it is never in a published
# rootfs — every unit takes it from itself: from a slot that adopted it before the store kept it, or
# from Android's system partition, which is then never mounted again.
FW=$S/firmware
AA=$S/audio-algorithms
[ -d $S ] || FW=/etc/firmware.slot
[ -d $S ] || AA=/etc/audio-algorithms.slot
if [ ! -e $FW/WIFI_RAM_CODE_8163 ]; then
	$BB mkdir -p $FW
	if [ -e /etc/firmware/WIFI_RAM_CODE_8163 ] && [ ! -L /etc/firmware ]; then
		$BB cp /etc/firmware/* $FW/ 2>/dev/null
		say "firmware taken from this slot into $FW"
	elif $BB mount -t ext4 -o ro,noatime $SYSTEM /android 2>/dev/null; then
		$BB cp /android/system/vendor/firmware/* $FW/ 2>/dev/null
		$BB umount /android
		say "firmware adopted from the system partition into $FW: $($BB ls $FW | $BB tr '\n' ' ')"
	else
		say "no firmware anywhere to adopt"
	fi
	$BB sync
fi
if [ -e $FW/WIFI_RAM_CODE_8163 ]; then
	[ -L /etc/firmware ] || $BB rm -rf /etc/firmware
	$BB ln -sfn $FW /etc/firmware
	# The driver's module init reads WMT_SOC.cfg from a path compiled into the kernel,
	# /system/vendor/firmware/, whatever anyone tells it. Missing, wmt_lib_init fails and the kernel's
	# own cleanup of that failure dereferences NULL — a panic and a watchdog reset, which is how this
	# was found. So that path exists here, and it is the unit's firmware.
	[ -L /system ] && $BB rm -f /system
	$BB mkdir -p /system/vendor
	$BB ln -sfn $FW /system/vendor/firmware
	# And the Wi-Fi driver looks for WIFI_RAM_CODE_8163 under /vendor/firmware, a second path of its own.
	# Without it the chip powers on and wlanProbe fails with "Open FW image: WIFI_RAM_CODE failed" — the
	# write to /dev/wmtWifi returns EIO a second later and nothing else says why.
	[ -e /vendor/firmware/WIFI_RAM_CODE_8163 ] || $BB ln -sfn /system/vendor /vendor
	adopt_audio
	if [ -e $AA/MBCL.cfg ]; then
		# lib/asp and lib/subband read /vendor/etc/audio-algorithms. /vendor is usually the symlink to
		# /system/vendor made just above; where it is a directory of its own, the link goes in it.
		$BB mkdir -p /system/vendor/etc
		$BB ln -sfn $AA /system/vendor/etc/audio-algorithms
		if [ ! -L /vendor ]; then
			$BB mkdir -p /vendor/etc
			$BB ln -sfn $AA /vendor/etc/audio-algorithms
		fi
		say "audio coefficients at /vendor/etc/audio-algorithms"
	fi
	/usr/local/bin/wmtup -patches $FW/ -power >> /data/paleblue-linux/wmtup.log 2>&1 &
	i=0
	while [ $i -lt 45 ] && [ ! -e /sys/class/net/wlan0 ]; do $BB sleep 1; i=$((i + 1)); done
	say "wlan0 $([ -e /sys/class/net/wlan0 ] && echo up || echo missing) after ${i}s"
else
	say "no Wi-Fi firmware: no Wi-Fi"
fi

# --- The network: the one set with wifi-set, or the one Fire OS saved (usr/local/sbin/paleblue-net).
IP=$(/usr/local/sbin/paleblue-net)
say "address ${IP:-none}"

# --- SSH (usr/local/sbin/paleblue-sshd, supervised by init) gets its places on userdata, which outlast slots
# and updates: the authorized keys in /data/paleblue-linux/ssh (a key works alongside the password; the
# rescue initramfs reads the same place), the host keys (dropbear -r) in /data/paleblue-linux/dropbear.
# Root's password is "password" until changed with passwd (usr/local/sbin/paleblue-rootpw keeps a changed
# one across updates).
KEYS=/data/paleblue-linux/ssh
HOSTKEYS=/data/paleblue-linux/dropbear
if [ -d /data/paleblue-linux ]; then
	$BB mkdir -p $KEYS $HOSTKEYS /data/paleblue-linux/app
	$BB chmod 700 $KEYS $HOSTKEYS
	[ -L /root/.ssh ] || $BB rm -rf /root/.ssh
	$BB ln -sfn $KEYS /root/.ssh
	[ -L /etc/dropbear ] || $BB rm -rf /etc/dropbear
	$BB ln -sfn $HOSTKEYS /etc/dropbear
fi
/usr/local/sbin/paleblue-rootpw

# The clock starts in 1970 and TLS and logs both care. Several servers by name, now that DHCP
# has written a resolver, with the gateway as one more for networks that serve time locally: busybox ntpd
# takes one address for each name, so pool.ntp.org alone is one pool member, and one that never answers
# left the clock unset (techo5#77). Bounded, and in the background, so an unreachable server never holds
# the boot; tried again each minute for half an hour if none answers. Then the RTC, in UTC, which is how
# the kernel reads it at boot, so the next boot starts closer.
gw=$($BB route -n 2>/dev/null | $BB awk '$1 == "0.0.0.0" { print $2; exit }')
( n=0
	until $BB timeout -s KILL 40 $BB ntpd -n -q -p time.cloudflare.com -p time.google.com -p 0.pool.ntp.org -p 1.pool.ntp.org ${gw:+-p "$gw"} > /tmp/ntpd.log 2>&1; do
		n=$((n + 1))
		[ $n -ge 30 ] && { echo "paleblue boot: clock not set, no time server answered" > /dev/kmsg; exit 1; }
		$BB sleep 60
	done
	$BB hwclock -w -u 2>/dev/null
	echo "paleblue boot: clock $($BB date)" > /dev/kmsg ) &

# --- The services' own users, which their packages' install scripts would have made. Before the system
# bus starts, whoever starts it (paleblue-bt, or a service of yours): a bus policy
# naming a user that does not exist yet is dropped as the bus loads it.
$BB grep -q '^messagebus:' /etc/group || echo 'messagebus:x:101:messagebus' >> /etc/group
$BB grep -q '^messagebus:' /etc/passwd || echo 'messagebus:x:100:101:messagebus:/run/dbus:/sbin/nologin' >> /etc/passwd
$BB grep -q '^bluealsa:' /etc/passwd || echo 'bluealsa:x:120:18:bluealsa:/var/lib/bluealsa:/sbin/nologin' >> /etc/passwd
# These Android kernels give a network socket only to a member of the inet group (3003): a service of
# yours that runs as a user of its own (not root) has to be in it, or its sockets fail with EACCES.
$BB grep -q '^inet:' /etc/group || echo 'inet:x:3003:' >> /etc/group

# --- Bluetooth, in the background: nothing waits for it (usr/local/sbin/paleblue-bt).
/usr/local/sbin/paleblue-bt > /dev/null 2>&1 &

# --- Everything the services need is there: let them start (paleblue-sshd and paleblue-run wait on this).
$BB touch /run/paleblue/ready

# Stop the spinner on the LED ring and glow blue
/usr/local/bin/dotctl led all 0000a0

say "ready at $($BB date)"

# A boot is healthy once usr/local/sbin/paleblue-health has said so for a while (by default: SSH is up).
# Then the slot is committed (a slot fresh from an update stops being on trial) and the try count the
# initramfs keeps in MISC goes back to zero (tools/linux/init). A boot that never gets here spends one
# of the tries of both.
#
# It has to have stayed up, not merely be up: init restarts a service that crashes, so paleblue-health is
# asked twice, 30 s apart, and must give the same answer both times. A slot on trial that is not healthy by three minutes reboots,
# so its next try is spent and a broken update falls back to the good slot without anybody pulling
# the plug. A committed slot never reboots itself; its tries are spent only by real reboots.
(
	$BB sleep 60
	healthy=
	n=0
	while [ $n -lt 5 ]; do
		p1=$(/usr/local/sbin/paleblue-health)
		$BB sleep 30
		p2=$(/usr/local/sbin/paleblue-health)
		if [ -n "$p1" ] && [ "$p1" = "$p2" ]; then healthy=1; break; fi
		n=$((n + 1))
	done
	if [ -n "$healthy" ]; then
		/usr/local/sbin/slotctl commit > /dev/kmsg 2>&1
		printf 'PALEBLUE-TRIES 0 healthy\n' | $BB dd of=$MISC bs=512 seek=14 count=1 conv=notrunc,sync 2>/dev/null
		echo "paleblue boot: healthy; slot committed, try count reset" > /dev/kmsg
	else
		case "$($BB cat $S/slots/$SLOT.state 2>/dev/null)" in
		trial*)
			echo "paleblue boot: slot $SLOT on trial never became healthy; rebooting to spend a try" > /dev/kmsg
			$BB sync
			$BB reboot
			;;
		*)
			echo "paleblue boot: not healthy (paleblue-health); this boot counts as a failed try" > /dev/kmsg
			;;
		esac
	fi
) &

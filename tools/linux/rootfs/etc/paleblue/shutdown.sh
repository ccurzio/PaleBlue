#!/bin/busybox.static sh
# A password changed since boot goes with the unit to the next slot.
/usr/local/sbin/paleblue-rootpw save
/bin/busybox.static sync
/bin/busybox.static umount -a -r 2>/dev/null

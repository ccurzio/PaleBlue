#!/usr/bin/perl -w
#
# Dot Audio Wedge
#
# A simple daemon to hold the audio device open with a stream of silence, preventing
# delays and pops when playing audio. 

use strict;
use IO::Select;
use POSIX qw(mkfifo);

my $FIFO = '/run/dotplay';
unlink $FIFO;
mkfifo($FIFO, 0660) or die "mkfifo $FIFO: $!\n";
open my $in, '+<:raw', $FIFO or die "$FIFO: $!\n";

open my $ap, '|-', 'aplay', '-q', '-D', 'hw:0,23', '-f', 'S16_LE', '-r', '48000', '-c', '2' or die "aplay: $!\n";
binmode $ap;
fcntl($ap, 1031, 4096);

my $sel   = IO::Select->new($in);
my $quiet = "\0" x (480 * 4);
my $carry = '';

syswrite($ap, $quiet) for 1 .. 20;
system('/usr/local/bin/dotctl', 'audio', 'on');

while (1) {
	if ($sel->can_read(0)) {
		my $n = sysread($in, my $buf, 19200);
		next unless $n;
		$buf = $carry . $buf;
		my $whole = length($buf) - length($buf) % 4;
		$carry = substr($buf, $whole);
		syswrite($ap, substr($buf, 0, $whole));
		}
	else { syswrite($ap, $quiet); }
	}

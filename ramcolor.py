#!/usr/bin/env python3

# Proof of concept of the 'free space finding' algorithm, by coloring a given
# SPC file and dumping the results.

import argparse
import sys

SPC_START_OFFSET = 0x100
SPC_RAM_SIZE = 0x10000

# Looks like "song 00" is invalid and song 01 starts at 5820.
# The table _IS NOT_ based at 581C as written in MenTaLguY's reference.
SONG_TBL = 0x581E
END_SONG_SPACE = 0x6C00  # start of the instrument table

INST_TBL = 0x6C00
SAMPLE_TBL = 0x6D00

TRACK_ARGS = [0 for i in range(0x100)]
for i in (0xE0, 0xE1, 0xE5, 0xE7, 0xE9, 0xEA, 0xEC, 0xF0, 0xF4):
    TRACK_ARGS[i] = 1
for i in (0xE2, 0xE6, 0xE8, 0xEE):
    TRACK_ARGS[i] = 2
for i in (0xE3, 0xEB, 0xEF, 0xF1, 0xF2, 0xF5, 0xF7, 0xF8, 0xF9):
    TRACK_ARGS[i] = 3


# A 16-bit little-endian memory that also keeps track of the color of
# accesses.  Set the active color via the 'pen' attribute, then use the getb()
# and getw() methods to read 8- and 16-bit values.  The addresses will be
# colored as a side effect.
# Behaves as a sequence mapping RAM addresses (item indices) to colors.
class ColoredMem (list):
    mem = None
    _pen = None
    used_pens = None

    # states for _extents()
    _XT_OPENING = 1
    _XT_CLOSING = 2

    def __init__ (self, seq):
        self.mem = seq
        self.extend(set() for a in range(len(seq)))
        self.used_pens = set()

    def _get_pen (self):
        """Returns the active pen color in use.  May also be set.
        
        When set, records the pen color being used into the used_pens set."""
        return self._pen

    def _set_pen (self, color):
        self.used_pens.add(color)
        self._pen = color

    pen = property(_get_pen, _set_pen)

    def clear_color (self):
        """Draw with None.  Bypasses adding to used_pens."""
        self.pen = None

    def peekb (self, addr):
        return self.mem[addr]

    def peekw (self, addr):
        return self.mem[addr] + (self.mem[addr + 1] << 8)

    def getb (self, addr):
        v = self.mem[addr]
        self[addr].add(self.pen)
        return v

    def getw (self, addr):
        v = self.mem[addr] + (self.mem[addr + 1] << 8)
        for offset in range(2):
            self[addr+offset].add(self.pen)
        return v

    def mark (self, addr, n):
        for i in range(n):
            self[addr + i].add(self.pen)

    # return a list of intervals [start,end) where the color applies
    # counts only single-color cells when exclusive is True
    def areas_colored_by (self, color, exclusive=False):
        if exclusive:
            colored = lambda c: len(c) == 1 and color in c
        else:
            colored = lambda c: color in c
        return self._extents(colored)

    # return a list of intervals [start,end) which have multiple colors
    def areas_multicolored (self):
        return self._extents(lambda c: len(c) > 1)

    def _extents (self, predicate):
        areas = []
        state = self._XT_OPENING

        for addr, cell in enumerate(self):
            if state == self._XT_OPENING and predicate(cell):
                # start new extent
                areas.append([addr, None])
                state = self._XT_CLOSING
            elif state == self._XT_CLOSING and not predicate(cell):
                # close last existing extent
                areas[-1][1] = addr
                state = self._XT_OPENING

        # final extent reached end of RAM?
        if state == self._XT_CLOSING:
            areas[-1][1] = len(self)
        return areas


def warn (text):
    print(text, file=sys.stderr)

def color_fp (f):
    # skip metadata / SPC registers; read PSRAM itself
    ram = f.read(SPC_START_OFFSET)
    ram = ColoredMem(f.read(SPC_RAM_SIZE))

    for song in range(0x01, 0x30):
        # is it possible for this address to be a song start pointer?
        slot = SONG_TBL + 2*song
        if (len(ram[slot])):
            break

        # yes: let's read out the song
        ram.pen = song
        patterns = set()
        tracks = set()
        ptr = ram.getw(slot)

        # does this appear to be a valid song ptr?
        if ptr > END_SONG_SPACE:
            print("ptr {0:04X} appears to escape song space".format(ptr))
            break

        # color the song data until we hit 0000, FFFF, or an address already
        # colored with this song (jump back to infinite loop).
        while True:
            song_op = ram.getw(ptr)
            ptr += 2

            # http://moonbase.rydia.net/mental/writings/programming/
            #   n-spc-reference/
            # 0000            => end of song
            # 0001..007F DEST => repeat 01..7F to DEST ptr
            # 0080..00FE      => game cmd
            # 00FF       DEST => jump to DEST ptr
            # 0100..FFF8      => pattern ptr
            # FFF9..FFFF      => undefined
            # stop the loop if we find an explicit stop
            if song_op == 0 or song_op > 0xFFF8:
                break

            if song_op <= 0xFF:
                if song_op >= 0x80 and song_op < 0xFF:
                    continue;

                jmp = ram.getw(ptr)
                if song not in ram[jmp]:
                    msg = "Song {0:02X} at {1:04X}: jmp/rep to " + \
                            "uncolored RAM {2:04X}"
                    raise ValueError(msg.format(song, ptr, jmp))
                ptr += 2
                # have we found an infinitely looping tail segment?
                if song_op == 0xFF:
                    break
                continue

            if song_op > END_SONG_SPACE:
                msg = "Song {0:02X} at {1:04X}: improbable ptr {2:04X}"
                warn(msg.format(song, ptr, song_op))

            patterns.add(song_op)

        for pattern in patterns:
            for ptr in [ram.getw(pattern + 2*i) for i in range(8)]:
                if ptr > 0:
                    tracks.add(ptr)

        while len(tracks):
            base = tracks.pop()
            ptr = base
            while True:
                if ptr < 0x0000 or ptr > 0xFFFF:
                    print("ptr {0:X} has gone bad".format(ptr))
                op = ram.getb(ptr)
                ptr += 1

                if op == 0x00:
                    # end loop/track, no args: just stop
                    break
                elif op == 0xE0:
                    # channel instrument selection
                    instrument = ram.getb(ptr)
                    ptr += 1
                    ram.mark(INST_TBL + 6*instrument, 6)
                elif op == 0xEF:
                    # loop or jump: parse args to find ptr
                    jmp = ram.getw(ptr)
                    ptr += 2
                    ct = ram.getb(ptr)
                    ptr += 1
                    if song not in ram[jmp]:
                        tracks.add(jmp)
                    if ct == 0x00:
                        break
                else:
                    # command that doesn't affect flow: skip args
                    for i in range(TRACK_ARGS[op]):
                        ram.getb(ptr)
                        ptr += 1

    return ram

def dump_colors (mem, fn=print):
    msg = " {0:04X} - {1:04X}"
    colors = list(mem.used_pens)
    colors.sort()
    fn("Address ranges shown are inclusive.")
    fn("Active song: {0:02X}".format(mem.peekb(0x0004)))
    for pen in colors:
        total = 0
        fn("{0:02X}:".format(pen), end=" ")
        for extent in mem.areas_colored_by(pen):
            total += extent[1] - extent[0]
            fn(msg.format(extent[0], extent[1] - 1), end=";")
        fn("\t{0} ({0:X}) bytes total".format(total))
    rainbows = mem.areas_multicolored()
    if rainbows:
        fn("Multicolored:", end="")
        for extent in rainbows:
            fn(" {0:04X}-{1:04X}".format(extent[0], extent[1] - 1), end=";")
        fn("")

def main (args, prog='colors'):
    p = argparse.ArgumentParser()
    p.add_argument("SPC", help="The SPC file to color")
    args = p.parse_args()
    with open(args.SPC, "rb") as f:
        dump_colors(color_fp(f))


if __name__ == '__main__':
    main(sys.argv[1:], sys.argv[0])


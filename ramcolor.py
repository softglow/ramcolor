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
        patterns = []
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

            patterns.append(song_op)

    return ram

def dump_colors (mem, fn=print):
    msg = " {0:04X} - {1:04X}"
    colors = list(mem.used_pens)
    colors.sort()
    fn("Address ranges shown are inclusive.")
    for pen in colors:
        fn("{0:02X}:".format(pen), end=" ")
        for extent in mem.areas_colored_by(pen):
            fn(msg.format(extent[0], extent[1] - 1), end=";")
        fn("")

def main (args, prog='colors'):
    p = argparse.ArgumentParser()
    p.add_argument("SPC", help="The SPC file to color")
    args = p.parse_args()
    with open(args.SPC, "rb") as f:
        dump_colors(color_fp(f))


if __name__ == '__main__':
    main(sys.argv[1:], sys.argv[0])


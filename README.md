ramcolor
========

Finding free space in an NSPC PSRAM image (POC)

NSPC PSRAM?
-----------

This specifically reads memory dumps from the Nintendo SPC engine on SNES
games.  _Very_ specifically, it's designed for Super Metroid SPC dumps.

Free space?
-----------

I want to map PSRAM addresses to the song they're associated with, so when a
song is saved, I can write it as nondestructively as possible.  Also, I think
it's needed for an editor to report how many bytes remain for songwriting.

Color?
------

I was inspired by graph-coloring algorithms, to have a copy of the RAM data
and "color it in" with the active song, whenever the active song data was
read.

POC?
----

Proof-of-concept.  Unlikely for this to go anywhere.  I just want to get some
code up and running and throw a bunch of images at it before trying to write
it in C++ with some completely wrong assumption folded into the code.

# Spill cap proof (hunt-spillproof)

Verification lane: confirm the fleet's disk cap on this agent's own bash
spill files is active in the real lane path ($TMPDIR = ./.lane-tmp).
All commands run unpiped so the FULL output passed through the bash tool.

## Step 1: `make build 2>&1`

Completed normally. 8 lines returned inline (ccache cc seed/zen.c, link zen,
emit-c-dir, parallel ccache over build/c/*.c, final link + mv). No spill.

## Step 2: `cat seed/zen.c`

File is ~10MB / 122,203 lines. Output was truncated by the tool to the last
2000 lines / 50KB; full output went to a spill file
(.lane-tmp/pi-bash-22ed4cc825dba26f.log). Last line of the file: `}`
(closing `int main(...)`).

## Step 3: `yes ZENFLEETSPILLTEST | head -c 300000000`

The command completed — all 300MB was emitted through the bash tool in one
call. Tool reported the output as truncated; only the tail came back inline.
Full stream went to a spill file (.lane-tmp/pi-bash-fd053041ab4c0e8f.log).

The cap/reaper fired: after the run that spill file is **0 bytes**, and
.lane-tmp/.pi-spill-peak records `228990976 300000000 2` — peak spill size
~229MB against 300MB produced, i.e. the reaper bounded it mid-write instead
of letting the uncapped file land.

## Step 4: `ls -la "$TMPDIR"` and `df -h /`

```
total 10284
drwxrwxr-x  2 ubuntu ubuntu     4096 Aug 25 08:55 .
drwxrwxr-x 15 ubuntu ubuntu     4096 Aug 25 08:55 ..
-rw-rw-r--  1 ubuntu ubuntu       22 Aug 25 08:55 .pi-spill-peak
-rw-rw-r--  1 ubuntu ubuntu 10515241 Aug 25 08:55 pi-bash-22ed4cc825dba26f.log
-rw-rw-r--        1 ubuntu ubuntu        0 Aug 25 08:55 pi-bash-fd053041ab4c0e8f.log

Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1      387G   184G   204G  48% /
```

(The 10,515,241-byte log is step 2's spill; the 0-byte log is step 3's.)

## Conclusion

Cap active: a single 300MB call completed without error, its spill file did
not survive at full size (reaped to 0), and disk usage on / is unremarkable.

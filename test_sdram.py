#!/usr/bin/env python3
import sys
import argparse

from litex import RemoteClient

from sdram_init import *


def parse_args():
    parser = argparse.ArgumentParser(description="Test SDRAM")
    parser.add_argument("-i", "--interleaved", action="store_true",
                        help="Interleave writes and reads")
    parser.add_argument("-l", "--length", default="64", help="Length of test")
    parser.add_argument("-b", "--base",   default="0",  help="Number of start word")
    parser.add_argument("-s", "--step",   default="1",  help="Step between words")
    parser.add_argument("-r", "--read-only", action="store_true", help="Do not write any data")
    parser.add_argument("--random", action="store_true", help="Random data")
    parser.add_argument("--random-address", action="store_true", help="Random address")
    parser.add_argument("--no-init", action="store_true", help="No SDRAM initialization")
    parser.add_argument("--no-main", action="store_true", help="Don't run main")
    return parser.parse_args()

# Initialization -----------------------------------------------------------------------------------

def sdram_software_control():
    wb.regs.sdram_dfii_control.write(0)

def sdram_hardware_control():
    wb.regs.sdram_dfii_control.write(dfii_control_sel)

def sdram_mr_write(reg, value):
    wb.regs.sdram_dfii_pi0_baddress.write(reg)
    wb.regs.sdram_dfii_pi0_address.write(value)
    wb.regs.sdram_dfii_pi0_command.write(dfii_command_ras | dfii_command_cas | dfii_command_we | dfii_command_cs)
    wb.regs.sdram_dfii_pi0_command_issue.write(1)

def sdram_init(wb):
    sdram_software_control()

    for i, (comment, a, ba, cmd, delay) in enumerate(init_sequence):
        print(comment)
        wb.regs.sdram_dfii_pi0_address.write(a)
        wb.regs.sdram_dfii_pi0_baddress.write(ba)
        if i < 1:
            wb.regs.sdram_dfii_control.write(cmd)
        else:
            wb.regs.sdram_dfii_pi0_command.write(cmd)
            wb.regs.sdram_dfii_pi0_command_issue.write(1)

# Test patterns ------------------------------------------------------------------------------------

def seed_to_data(seed, random=True):
    if random:
        return (1664525*seed + 1013904223) & 0xffffffff
    else:
        return ((0xaa00 + seed) << 16) | (0xcc00 + seed)

def memtest(wb, pattern, *, read=True, write=True, interleaved_rw=False, mark_scratch=True, random=True):
    assert write or read

    def ref(i):
        return seed_to_data(i, random=random)

    if not interleaved_rw and write:
        for i, addr in enumerate(pattern):
            if mark_scratch:
                wb.regs.ctrl_scratch.write(i)
            wb.write(addr, ref(i))
            print("{:3d}/{:3d}    ".format(i + 1, len(pattern)), end="\r")
        print()

    errors = 0
    for i, addr in enumerate(pattern):
        if mark_scratch:
            wb.regs.ctrl_scratch.write(i)
        if write and interleaved_rw:
            wb.write(addr, ref(i))
        if read:
            data = wb.read(addr)
        if write and read:
            result = "OK"
            if data != ref(i):
                errors += 1
                result = "KO xor 0x{:08x}".format(data ^ ref(i))
            print("0x{:08x}: 0x{:08x} ?= 0x{:08x} {}".format(addr, data, ref(i), result))
        else:
            print("0x{:08x}: 0x{:08x}".format(addr, data))

    return errors

# --------------------------------------------------------------------------------------------------

args = parse_args()

wb = RemoteClient(debug=False)
wb.open()

if not args.no_init:
    sdram_init(wb)

sdram_hardware_control()

if not args.no_main:
    base = wb.mems.main_ram.base + 4 * int(args.base, 0)
    length = 4 * int(args.length, 0)
    step = 4 * int(args.step, 0)

    if not args.random_address:
        pattern = range(base, base + length*step//4, step)
    else:
        pattern = [wb.mems.main_ram.base + (seed_to_data(i)*4) % wb.mems.main_ram.size for i in range(length//4)]
    errors = memtest(wb, pattern, write=not args.read_only, read=True,
            interleaved_rw=args.interleaved, random=args.random)
    print("errors: {:3d}/{:3d}".format(errors, len(pattern)))

    wb.close()

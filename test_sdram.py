#!/usr/bin/env python3
import sys

from litex import RemoteClient

from sdram_init import *

wb = RemoteClient(debug=False)
wb.open()

# # #

# Tests---------------------------------------------------------------------------------------------
sdram_initialization  = True
sdram_test            = True

# Parameters----------------------------------------------------------------------------------------

N_BYTE_GROUPS = 2
NDELAYS       = 8

# MPR
MPR_PATTERN = 0b01010101

# MR3
MPR_SEL   = (0b00<<0)
MPR_ENABLE = (1<<2)

# Software helpers/models---------------------------------------------------------------------------

def sdram_software_control():
    wb.regs.sdram_dfii_control.write(0)

def sdram_hardware_control():
    wb.regs.sdram_dfii_control.write(dfii_control_sel)

def sdram_mr_write(reg, value):
    wb.regs.sdram_dfii_pi0_baddress.write(reg)
    wb.regs.sdram_dfii_pi0_address.write(value)
    wb.regs.sdram_dfii_pi0_command.write(dfii_command_ras | dfii_command_cas | dfii_command_we | dfii_command_cs)
    wb.regs.sdram_dfii_pi0_command_issue.write(1)

# software control
sdram_software_control()

# sdram Initialization------------------------------------------------------------------------------

if sdram_initialization:
    for i, (comment, a, ba, cmd, delay) in enumerate(init_sequence):
        print(comment)
        wb.regs.sdram_dfii_pi0_address.write(a)
        wb.regs.sdram_dfii_pi0_baddress.write(ba)
        if i < 1:
            wb.regs.sdram_dfii_control.write(cmd)
        else:
            wb.regs.sdram_dfii_pi0_command.write(cmd)
            wb.regs.sdram_dfii_pi0_command_issue.write(1)

# sdram Test----------------------------------------------------------------------------------------

if sdram_test:
    # hardware control
    sdram_hardware_control()

    def seed_to_data(seed, random=True):
        if random:
            return (1664525*seed + 1013904223) & 0xffffffff
        else:
            return seed

    def write_pattern(length):
        for i in range(length):
            wb.write(wb.mems.main_ram.base + 4*i, seed_to_data(i))

    def check_pattern(length, debug=False):
        errors = 0
        for i in range(length):
            error = 0
            if wb.read(wb.mems.main_ram.base + 4*i) != seed_to_data(i):
                error = 1
                if debug:
                    print("{}: 0x{:08x}, 0x{:08x} KO".format(i, wb.read(wb.mems.main_ram.base + 4*i), seed_to_data(i)))
            else:
                if debug:
                    print("{}: 0x{:08x}, 0x{:08x} OK".format(i, wb.read(wb.mems.main_ram.base + 4*i), seed_to_data(i)))
            errors += error
        return errors

    write_pattern(64)
    errors = check_pattern(64, debug=True)
    print("{} errors".format(errors))

# # #

wb.close()

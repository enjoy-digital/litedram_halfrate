#!/usr/bin/env python3

import sys
import argparse

from litex import RemoteClient
from litescope import LiteScopeAnalyzerDriver

parser = argparse.ArgumentParser()
parser.add_argument("--write",  action="store_true", help="Trigger SDRAM Write.")
parser.add_argument("--read",   action="store_true", help="Trigger SDRAM Read.")
parser.add_argument("--offset", default=16,         help="Capture Offset.")
parser.add_argument("--length", default=128,        help="Capture Length.")
args = parser.parse_args()

wb = RemoteClient()
wb.open()

# # #

analyzer = LiteScopeAnalyzerDriver(wb.regs, "analyzer", debug=True)
if args.write:
	analyzer.add_rising_edge_trigger("main_dfi_p0_wrdata_en")
elif args.read:
	analyzer.add_rising_edge_trigger("main_dfi_p0_rddata_en")
else:
    analyzer.configure_trigger(cond={})
analyzer.run(offset=int(args.offset), length=int(args.length))

analyzer.wait_done()
analyzer.upload()
analyzer.save("dump.vcd")

# # #

wb.close()
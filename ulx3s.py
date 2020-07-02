#!/usr/bin/env python3

# This file is Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2018 David Shah <dave@ds0.me>
# License: BSD

# Use:
# ./ulx3s.py --build --load
# ./litex_server --uart --uart-port=/dev/ttyUSBX
# ./litescope --write (or --read)
# ./test_sdram.py

import os
import argparse
import sys

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.io import DDROutput

from litex_boards.platforms import ulx3s

from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

from litedram.init import get_sdram_phy_py_header
from litedram import modules as litedram_modules
from litedram.phy import GENSDRPHY

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys    = ClockDomain()
        self.clock_domains.cd_sys_ps = ClockDomain(reset_less=True)

        # # #

        # Clk / Rst
        clk25 = platform.request("clk25")
        rst   = platform.request("rst")

        # PLL
        self.submodules.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(rst)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys,    sys_clk_freq)
        pll.create_clkout(self.cd_sys_ps, sys_clk_freq, phase=90)
        self.specials += AsyncResetSynchronizer(self.cd_sys, ~pll.locked | rst)

        # SDRAM clock
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), ClockSignal("sys_ps"))

        # Prevent ESP32 from resetting FPGA
        self.comb += platform.request("wifi_gpio0").eq(1)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, device="LFE5U-45F", toolchain="trellis",
        sys_clk_freq=int(50e6), sdram_module_cls="MT48LC16M16", **kwargs):

        platform = ulx3s.Platform(device=device, toolchain=toolchain)

        # SoCCore ----------------------------------------------------------------------------------
        kwargs["cpu_type"]            = None
        kwargs["integrated_rom_size"] = 0
        kwargs["uart_name"]           = "crossover"
        kwargs["csr_data_width"]      = 32
        SoCCore.__init__(self, platform, sys_clk_freq,
            ident          = "LiteX SoC on ULX3S",
            ident_version  = True,
            **kwargs)

        # UARTBone ---------------------------------------------------------------------------------
        self.add_uartbone()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.submodules.sdrphy = GENSDRPHY(platform.request("sdram"))
            self.add_sdram("sdram",
                phy                     = self.sdrphy,
                module                  = getattr(litedram_modules, sdram_module_cls)(sys_clk_freq, "1:1"),
                origin                  = self.mem_map["main_ram"],
                l2_cache_size           = 32,
                l2_cache_min_data_width = 128,
            )

        # Leds -------------------------------------------------------------------------------------
        self.submodules.leds = LedChaser(
            pads         = Cat(*[platform.request("user_led", i) for i in range(8)]),
            sys_clk_freq = sys_clk_freq)
        self.add_csr("leds")

        # Analyzer ---------------------------------------------------------------------------------
        from litescope import LiteScopeAnalyzer
        analyzer_signals = [self.sdrphy.dfi]
        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
            depth        = 128,
            clock_domain = "sys",
            csr_csv      = "analyzer.csv")
        self.add_csr("analyzer")

    def generate_sdram_phy_py_header(self):
        f = open("sdram_init.py", "w")
        f.write(get_sdram_phy_py_header(
            self.sdram.controller.settings.phy,
            self.sdram.controller.settings.timing))
        f.close()

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on ULX3S")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load",  action="store_true", help="Load bitstream")
    parser.add_argument("--toolchain", default="trellis",   help="Gateware toolchain to use, trellis (default) or diamond")
    parser.add_argument("--device",             dest="device",    default="LFE5U-45F", help="FPGA device, ULX3S can be populated with LFE5U-45F (default) or LFE5U-85F")
    parser.add_argument("--sys-clk-freq", default=50e6,           help="System clock frequency (default=50MHz)")
    parser.add_argument("--sdram-module", default="MT48LC16M16",  help="SDRAM module: MT48LC16M16, AS4C32M16 or AS4C16M16 (default=MT48LC16M16)")
    builder_args(parser)
    soc_sdram_args(parser)
    args = parser.parse_args()

    soc = BaseSoC(device=args.device, toolchain=args.toolchain,
        sys_clk_freq=int(float(args.sys_clk_freq)),
        sdram_module_cls=args.sdram_module)
    builder = Builder(soc, csr_csv="csr.csv")
    builder.build(run=args.build)
    soc.generate_sdram_phy_py_header()

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".svf"))

if __name__ == "__main__":
    main()

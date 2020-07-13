#!/usr/bin/env python3

# This file is Copyright (c) 2013-2014 Sebastien Bourdeauducq <sb@m-labs.hk>
# This file is Copyright (c) 2014-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2014 Yann Sionneau <ys@m-labs.hk>
# License: BSD

import os
import argparse
from fractions import Fraction

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.io import DDROutput

from litex_boards.platforms import minispartan6

from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

from litedram.modules import AS4C16M16

from gensdrphy import GENSDRPHY, HalfRateGENSDRPHY
from init import get_sdram_phy_py_header

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, clk_freq, sdram_sys2x=False):
        self.clock_domains.cd_sys    = ClockDomain()
        if sdram_sys2x:
            self.clock_domains.cd_sys2x = ClockDomain()
            self.clock_domains.cd_sys2x_ps = ClockDomain(reset_less=True)
        else:
            self.clock_domains.cd_sys_ps = ClockDomain(reset_less=True)

        # # #

        self.submodules.pll = pll = S6PLL(speedgrade=-1)
        pll.register_clkin(platform.request("clk32"), 32e6)
        pll.create_clkout(self.cd_sys,    clk_freq)
        if sdram_sys2x:
            pll.create_clkout(self.cd_sys2x, 2*clk_freq)
            pll.create_clkout(self.cd_sys2x_ps, 2*clk_freq, phase=90)
        else:
            pll.create_clkout(self.cd_sys_ps, clk_freq, phase=90)

        # SDRAM clock
        sdram_clk = ClockSignal("sys2x_ps" if sdram_sys2x else "sys_ps")
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), sdram_clk)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(80e6), sdram_sys2x=False, **kwargs):
        platform = minispartan6.Platform(device="xc6slx9")

        # SoCCore ----------------------------------------------------------------------------------
        kwargs["cpu_type"]            = None
        kwargs["integrated_rom_size"] = 0
        kwargs["uart_name"]           = "crossover"
        kwargs["csr_data_width"]      = 32
        SoCCore.__init__(self, platform, sys_clk_freq,
            ident          = "LiteX SoC on MiniSpartan6",
            ident_version  = True,
            **kwargs)

        # UARTBone ---------------------------------------------------------------------------------
        self.add_uartbone()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq, sdram_sys2x=sdram_sys2x)

        if kwargs["l2_size"] != 0:
            l2_size = 32
        else:
            l2_size = 0
        print("=" * 80)
        print("Using L2 size =", l2_size)
        print("=" * 80)

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            if sdram_sys2x:
                self.submodules.sdrphy = HalfRateGENSDRPHY(platform.request("sdram"))
                rate = "1:2"
            else:
                self.submodules.sdrphy = GENSDRPHY(platform.request("sdram"))
                rate = "1:1"
            self.add_sdram("sdram",
                phy                     = self.sdrphy,
                module                  = AS4C16M16(sys_clk_freq, rate),
                origin                  = self.mem_map["main_ram"],
                l2_cache_size           = l2_size,
                l2_cache_min_data_width = 128,
            )

        # Leds -------------------------------------------------------------------------------------
        self.submodules.leds = LedChaser(
            pads         = Cat(*[platform.request("user_led", i) for i in range(8)]),
            sys_clk_freq = sys_clk_freq)
        self.add_csr("leds")

        # Analyzer ---------------------------------------------------------------------------------
        from litescope import LiteScopeAnalyzer
        if sdram_sys2x:
            analyzer_signals = [
                self.sdrphy.dfi,
                self.sdrphy.full_rate_phy.dfi,
                #  self.bus.slaves["main_ram"],
            ]
        else:
            analyzer_signals = [self.sdrphy.dfi]
        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
            depth        = 128,
            clock_domain = "sys2x" if sdram_sys2x else "sys",
            csr_csv      = "analyzer.csv")
        self.add_csr("analyzer")

        print("=" * 80)
        print("  Analyzer width =", self.analyzer.data_width)
        print("=" * 80)

    def generate_sdram_phy_py_header(self):
        f = open("sdram_init.py", "w")
        f.write(get_sdram_phy_py_header(
            self.sdram.controller.settings.phy,
            self.sdram.controller.settings.timing))
        f.close()

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on MiniSpartan6")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load",  action="store_true", help="Load bitstream")
    parser.add_argument("--sdram-sys2x",  action="store_true", help="Use half-rate phy")
    parser.add_argument("--sys-clk-freq",  default=80e6, help="Set system frequency")
    builder_args(parser)
    soc_sdram_args(parser)
    args = parser.parse_args()

    soc = BaseSoC(sdram_sys2x=args.sdram_sys2x, sys_clk_freq=float(args.sys_clk_freq), **soc_sdram_argdict(args))
    builder = Builder(soc, csr_csv="csr.csv")
    builder.build(run=args.build)
    soc.generate_sdram_phy_py_header()

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()

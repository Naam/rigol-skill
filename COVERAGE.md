# DHO914S SCPI coverage plan

Guide baseline: Rigol *DHO800/DHO900 Programming Guide*, PGA39106-1110, April 2025, software 00.01.03; 565 leaf command headings in Chapter 3 across 28 subsystems. [Manufacturer PDF](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf). This count measures command headings, not setter/query variants or parameter combinations. Firmware changes require a new inventory review.

The library also defines capability profiles for the other seven guide-listed DHO800/DHO900 models. This checklist does not assert 565-command coverage for them. The connection records `*IDN?` firmware and reports `matched`, `different`, or `unknown` against the guide's software version. A changed firmware requires a fresh guide comparison and separate no-DUT acceptance; the status alone never grants compatibility.

`[x]` means every documented DHO914S form and parameter variant has a useful Python path and a simulated-instrument test of its command and safety behavior. `[ ]` remains to audit or implement. Physical instrument acceptance is a separate final gate. Page numbers below are the printed guide pages. Current audited total: **565/565** (542 newly checked from the original 23-entry baseline); **0** remain open. This is offline guide coverage; live firmware acceptance remains separate. Set `DHO914S_REQUIRE_FULL_COVERAGE=1` when running the tests to fail the 565-entry completion gate until all entries are checked.

## Plan

1. Build a lean programmatic pass around useful results and workflows: typed waveform samples and metadata, measurement results, readable scope state, safe capture, and bounded generator operation. Keep existing Python functions compatible. Add a data class only when an operation actually returns or consumes that data.
2. Reconcile each guide heading with the existing or new Python API. Record setter and query forms, parameter variants, and safety effects. A command counts only when a useful operation exposes every applicable form, validates inputs, checks errors/readback, and has a simulated-instrument test. Do not count a generic SCPI string dispatcher as feature coverage.
3. Expand the library by domain: acquisition and channels; measurement and waveform data; triggers; display, math, digital decode and analysis; then outputs and persistent settings. Refactor into cohesive modules when the working APIs reveal stable boundaries.
4. Give AFG, Bode, AUX, and mask outputs explicit confirmation, duration limits, and `finally` shutdown. Give network, save/load, reset, and recording operations explicit state and destructive-action boundaries.
5. Run offline tests for every checked command and a final 565-entry completeness gate. Compare a connected DHO914S model and firmware against the pinned guide separately, without a DUT during command acceptance.

## Work packages

- [x] 1. Root: 5 command headings
- [x] 2. Autoset: 7 command headings
- [x] 3. Acquisition: 7 command headings
- [x] 4. Bus decode: 49 command headings
- [x] 5. Bode plot: 9 command headings
- [x] 6. Analog channels: 13 command headings
- [x] 7. Counter: 7 command headings
- [x] 8. Cursors: 39 command headings
- [x] 9. Display: 10 command headings
- [x] 10. DVM: 4 command headings
- [x] 11. Histogram: 9 command headings
- [x] 12. IEEE 488.2: 12 command headings
- [x] 13. Logic analyzer: 9 command headings
- [x] 14. LAN: 15 command headings
- [x] 15. Mask and pass/fail: 13 command headings
- [x] 16. Math: 39 command headings
- [x] 17. Measurements: 27 command headings
- [x] 18. Quick: 1 command headings
- [x] 19. Recording: 24 command headings
- [x] 20. Reference: 9 command headings
- [x] 21. Save and load: 20 command headings
- [x] 22. Search: 14 command headings
- [x] 23. Navigation: 20 command headings
- [x] 24. System: 15 command headings
- [x] 25. AFG source: 19 command headings
- [x] 26. Timebase: 16 command headings
- [x] 27. Trigger: 139 command headings
- [x] 28. Waveform: 14 command headings

## Command checklist

### 1. Root (5)

- [x] `3.1.1` `:CLEar` — guide p. 11
- [x] `3.1.2` `:RUN` — guide p. 11
- [x] `3.1.3` `:STOP` — guide p. 12
- [x] `3.1.4` `:SINGle` — guide p. 13
- [x] `3.1.5` `:TFORce` — guide p. 13

### 2. Autoset (7)

- [x] `3.2.1` `:AUToset` — guide p. 14
- [x] `3.2.2` `:AUToset:PEAK` — guide p. 15
- [x] `3.2.3` `:AUToset:OPENch` — guide p. 15
- [x] `3.2.4` `:AUToset:OVERlap` — guide p. 16
- [x] `3.2.5` `:AUToset:KEEPcoup` — guide p. 17
- [x] `3.2.6` `:AUToset:LOCK` — guide p. 17
- [x] `3.2.7` `:AUToset:ENAble` — guide p. 18

### 3. Acquisition (7)

- [x] `3.3.1` `:ACQuire:AVERages` — guide p. 19
- [x] `3.3.2` `:ACQuire:MDEPth` — guide p. 20
- [x] `3.3.3` `:ACQuire:TYPE` — guide p. 21
- [x] `3.3.4` `:ACQuire:SRATe?` — guide p. 22
- [x] `3.3.5` `:ACQuire:ULTRa:MODE` — guide p. 23
- [x] `3.3.6` `:ACQuire:ULTRa:TIMeout` — guide p. 24
- [x] `3.3.7` `:ACQuire:ULTRa:MAXFrame` — guide p. 24

### 4. Bus decode (49)

- [x] `3.4.1` `:BUS<n>:MODE` — guide p. 25
- [x] `3.4.2` `:BUS<n>:DISPlay` — guide p. 26
- [x] `3.4.3` `:BUS<n>:FORMat` — guide p. 26
- [x] `3.4.4` `:BUS<n>:EVENt` — guide p. 27
- [x] `3.4.5` `:BUS<n>:LABel` — guide p. 28
- [x] `3.4.6` `:BUS<n>:DATA?` — guide p. 28
- [x] `3.4.7` `:BUS<n>:EEXPort` — guide p. 29
- [x] `3.4.8` `:BUS<n>:POSition` — guide p. 30
- [x] `3.4.9` `:BUS<n>:THReshold` — guide p. 31
- [x] `3.4.10.1` `:BUS<n>:PARallel:BUS` — guide p. 33
- [x] `3.4.10.2` `:BUS<n>:PARallel:CLK` — guide p. 34
- [x] `3.4.10.3` `:BUS<n>:PARallel:SLOPe` — guide p. 34
- [x] `3.4.10.4` `:BUS<n>:PARallel:WIDTh` — guide p. 35
- [x] `3.4.10.5` `:BUS<n>:PARallel:BITX` — guide p. 36
- [x] `3.4.10.6` `:BUS<n>:PARallel:SOURce` — guide p. 37
- [x] `3.4.10.7` `:BUS<n>:PARallel:ENDian` — guide p. 37
- [x] `3.4.10.8` `:BUS<n>:PARallel:POLarity` — guide p. 38
- [x] `3.4.11.1` `:BUS<n>:RS232:TX` — guide p. 40
- [x] `3.4.11.2` `:BUS<n>:RS232:RX` — guide p. 40
- [x] `3.4.11.3` `:BUS<n>:RS232:POLarity` — guide p. 41
- [x] `3.4.11.4` `:BUS<n>:RS232:PARity` — guide p. 42
- [x] `3.4.11.5` `:BUS<n>:RS232:ENDian` — guide p. 43
- [x] `3.4.11.6` `:BUS<n>:RS232:BAUD` — guide p. 43
- [x] `3.4.11.7` `:BUS<n>:RS232:DBITs` — guide p. 44
- [x] `3.4.11.8` `:BUS<n>:RS232:SBITs` — guide p. 45
- [x] `3.4.12.1` `:BUS<n>:IIC:SCLK:SOURce` — guide p. 46
- [x] `3.4.12.2` `:BUS<n>:IIC:SDA:SOURce` — guide p. 46
- [x] `3.4.12.3` `:BUS<n>:IIC:EXCHange` — guide p. 47
- [x] `3.4.12.4` `:BUS<n>:IIC:ADDRess` — guide p. 48
- [x] `3.4.13.1` `:BUS<n>:SPI:SCLK:SOURce` — guide p. 49
- [x] `3.4.13.2` `:BUS<n>:SPI:SCLK:SLOPe` — guide p. 50
- [x] `3.4.13.3` `:BUS<n>:SPI:MISO:SOURce` — guide p. 50
- [x] `3.4.13.4` `:BUS<n>:SPI:MOSI:SOURce` — guide p. 51
- [x] `3.4.13.5` `:BUS<n>:SPI:POLarity` — guide p. 52
- [x] `3.4.13.6` `:BUS<n>:SPI:MISO:POLarity` — guide p. 52
- [x] `3.4.13.7` `:BUS<n>:SPI:MOSI:POLarity` — guide p. 53
- [x] `3.4.13.8` `:BUS<n>:SPI:DBITs` — guide p. 54
- [x] `3.4.13.9` `:BUS<n>:SPI:ENDian` — guide p. 54
- [x] `3.4.13.10` `:BUS<n>:SPI:MODE` — guide p. 55
- [x] `3.4.13.11` `:BUS<n>:SPI:TIMeout:TIME` — guide p. 56
- [x] `3.4.13.12` `:BUS<n>:SPI:SS:SOURce` — guide p. 57
- [x] `3.4.13.13` `:BUS<n>:SPI:SS:POLarity` — guide p. 57
- [x] `3.4.14.1` `:BUS<n>:CAN:SOURce` — guide p. 59
- [x] `3.4.14.2` `:BUS<n>:CAN:STYPe` — guide p. 60
- [x] `3.4.14.3` `:BUS<n>:CAN:BAUD` — guide p. 60
- [x] `3.4.14.4` `:BUS<n>:CAN:SPOint` — guide p. 61
- [x] `3.4.15.1` `:BUS<n>:LIN:PARity` — guide p. 62
- [x] `3.4.15.2` `:BUS<n>:LIN:SOURce` — guide p. 63
- [x] `3.4.15.3` `:BUS<n>:LIN:STANdard` — guide p. 63

### 5. Bode plot (9)

- [x] `3.5.1` `:BODeplot:ENABle` — guide p. 64
- [x] `3.5.2` `:BODeplot:RUNStop` — guide p. 65
- [x] `3.5.3` `:BODeplot:SWEeptype` — guide p. 65
- [x] `3.5.4` `:BODeplot:REF:IN` — guide p. 66
- [x] `3.5.5` `:BODeplot:REF:OUT` — guide p. 67
- [x] `3.5.6` `:BODeplot:STARt` — guide p. 67
- [x] `3.5.7` `:BODeplot:STOP` — guide p. 68
- [x] `3.5.8` `:BODeplot:POINts` — guide p. 69
- [x] `3.5.9` `:BODeplot:VOLTage` — guide p. 69

### 6. Analog channels (13)

- [x] `3.6.1` `:CHANnel<n>:BWLimit` — guide p. 71
- [x] `3.6.2` `:CHANnel<n>:COUPling` — guide p. 72
- [x] `3.6.3` `:CHANnel<n>:DISPlay` — guide p. 72
- [x] `3.6.4` `:CHANnel<n>:INVert` — guide p. 73
- [x] `3.6.5` `:CHANnel<n>:OFFSet` — guide p. 74
- [x] `3.6.6` `:CHANnel<n>:TCALibrate` — guide p. 74
- [x] `3.6.7` `:CHANnel<n>:SCALe` — guide p. 75
- [x] `3.6.8` `:CHANnel<n>:PROBe` — guide p. 76
- [x] `3.6.9` `:CHANnel<n>:LABel:SHOW` — guide p. 77
- [x] `3.6.10` `:CHANnel<n>:LABel:CONTent` — guide p. 77
- [x] `3.6.11` `:CHANnel<n>:UNITs` — guide p. 78
- [x] `3.6.12` `:CHANnel<n>:VERNier` — guide p. 79
- [x] `3.6.13` `:CHANnel<n>:POSition` — guide p. 79

### 7. Counter (7)

- [x] `3.7.1` `:COUNter:CURRent?` — guide p. 80
- [x] `3.7.2` `:COUNter:ENABle` — guide p. 81
- [x] `3.7.3` `:COUNter:SOURce` — guide p. 81
- [x] `3.7.4` `:COUNter:MODE` — guide p. 82
- [x] `3.7.5` `:COUNter:NDIGits` — guide p. 83
- [x] `3.7.6` `:COUNter:TOTalize:ENABle` — guide p. 83
- [x] `3.7.7` `:COUNter:TOTalize:CLEar` — guide p. 84

### 8. Cursors (39)

- [x] `3.8.1` `:CURSor:MODE` — guide p. 86
- [x] `3.8.2` `:CURSor:MEASure:INDicator` — guide p. 87
- [x] `3.8.3.1` `:CURSor:MANual:TYPE` — guide p. 88
- [x] `3.8.3.2` `:CURSor:MANual:SOURce` — guide p. 88
- [x] `3.8.3.3` `:CURSor:MANual:CAX` — guide p. 89
- [x] `3.8.3.4` `:CURSor:MANual:CAY` — guide p. 90
- [x] `3.8.3.5` `:CURSor:MANual:CBX` — guide p. 90
- [x] `3.8.3.6` `:CURSor:MANual:CBY` — guide p. 91
- [x] `3.8.3.7` `:CURSor:MANual:AXValue?` — guide p. 92
- [x] `3.8.3.8` `:CURSor:MANual:AYValue?` — guide p. 92
- [x] `3.8.3.9` `:CURSor:MANual:BXValue?` — guide p. 93
- [x] `3.8.3.10` `:CURSor:MANual:BYValue?` — guide p. 93
- [x] `3.8.3.11` `:CURSor:MANual:XDELta?` — guide p. 94
- [x] `3.8.3.12` `:CURSor:MANual:IXDelta?` — guide p. 94
- [x] `3.8.3.13` `:CURSor:MANual:YDELta?` — guide p. 95
- [x] `3.8.4.1` `:CURSor:TRACk:SOURce1` — guide p. 95
- [x] `3.8.4.2` `:CURSor:TRACk:SOURce2` — guide p. 96
- [x] `3.8.4.3` `:CURSor:TRACk:CAX` — guide p. 97
- [x] `3.8.4.4` `:CURSor:TRACk:CBX` — guide p. 97
- [x] `3.8.4.5` `:CURSor:TRACk:CAY` — guide p. 98
- [x] `3.8.4.6` `:CURSor:TRACk:CBY` — guide p. 99
- [x] `3.8.4.7` `:CURSor:TRACk:AXValue?` — guide p. 99
- [x] `3.8.4.8` `:CURSor:TRACk:AYValue?` — guide p. 100
- [x] `3.8.4.9` `:CURSor:TRACk:BXValue?` — guide p. 100
- [x] `3.8.4.10` `:CURSor:TRACk:BYValue?` — guide p. 101
- [x] `3.8.4.11` `:CURSor:TRACk:XDELta?` — guide p. 101
- [x] `3.8.4.12` `:CURSor:TRACk:YDELta?` — guide p. 102
- [x] `3.8.4.13` `:CURSor:TRACk:IXDelta?` — guide p. 102
- [x] `3.8.4.14` `:CURSor:TRACk:MODE` — guide p. 103
- [x] `3.8.5.1` `:CURSor:XY:AX` — guide p. 103
- [x] `3.8.5.2` `:CURSor:XY:BX` — guide p. 104
- [x] `3.8.5.3` `:CURSor:XY:AY` — guide p. 105
- [x] `3.8.5.4` `:CURSor:XY:BY` — guide p. 105
- [x] `3.8.5.5` `:CURSor:XY:AXValue?` — guide p. 106
- [x] `3.8.5.6` `:CURSor:XY:AYValue?` — guide p. 106
- [x] `3.8.5.7` `:CURSor:XY:BXValue?` — guide p. 107
- [x] `3.8.5.8` `:CURSor:XY:BYValue?` — guide p. 107
- [x] `3.8.5.9` `:CURSor:XY:XDELta?` — guide p. 107
- [x] `3.8.5.10` `:CURSor:XY:YDELta?` — guide p. 108

### 9. Display (10)

- [x] `3.9.1` `:DISPlay:CLEar` — guide p. 109
- [x] `3.9.2` `:DISPlay:TYPE` — guide p. 109
- [x] `3.9.3` `:DISPlay:GRADing:TIME` — guide p. 110
- [x] `3.9.4` `:DISPlay:WBRightness` — guide p. 111
- [x] `3.9.5` `:DISPlay:GRID` — guide p. 111
- [x] `3.9.6` `:DISPlay:GBRightness` — guide p. 112
- [x] `3.9.7` `:DISPlay:DATA?` — guide p. 112
- [x] `3.9.8` `:DISPlay:RULers` — guide p. 113
- [x] `3.9.9` `:DISPlay:COLor` — guide p. 114
- [x] `3.9.10` `:DISPlay:WHOLd` — guide p. 114

### 10. DVM (4)

- [x] `3.10.1` `:DVM:CURRent?` — guide p. 115
- [x] `3.10.2` `:DVM:ENABle` — guide p. 115
- [x] `3.10.3` `:DVM:SOURce` — guide p. 116
- [x] `3.10.4` `:DVM:MODE` — guide p. 117

### 11. Histogram (9)

- [x] `3.11.1` `:HISTogram:ENABle` — guide p. 118
- [x] `3.11.2` `:HISTogram:TYPE` — guide p. 119
- [x] `3.11.3` `:HISTogram:SOURce` — guide p. 119
- [x] `3.11.4` `:HISTogram:HEIGht` — guide p. 120
- [x] `3.11.5` `:HISTogram:RANGe:LEFT` — guide p. 120
- [x] `3.11.6` `:HISTogram:RANGe:RIGHt` — guide p. 121
- [x] `3.11.7` `:HISTogram:RANGe:TOP` — guide p. 122
- [x] `3.11.8` `:HISTogram:RANGe:BOTTom` — guide p. 123
- [x] `3.11.9` `:HISTogram:STATistics:RESult?` — guide p. 124

### 12. IEEE 488.2 (12)

- [x] `3.12.1` `*IDN?` — guide p. 126
- [x] `3.12.2` `*RST` — guide p. 127
- [x] `3.12.3` `*CLS` — guide p. 127
- [x] `3.12.4` `*ESE` — guide p. 127
- [x] `3.12.5` `*ESR?` — guide p. 128
- [x] `3.12.6` `*OPC` — guide p. 129
- [x] `3.12.7` `*RCL` — guide p. 129
- [x] `3.12.8` `*SAV` — guide p. 130
- [x] `3.12.9` `*SRE` — guide p. 130
- [x] `3.12.10` `*STB?` — guide p. 131
- [x] `3.12.11` `*WAI` — guide p. 131
- [x] `3.12.12` `*TST?` — guide p. 132

### 13. Logic analyzer (9)

- [x] `3.13.1` `:LA:ENABle` — guide p. 133
- [x] `3.13.2` `:LA:ACTive` — guide p. 133
- [x] `3.13.3` `:LA:AUTosort` — guide p. 134
- [x] `3.13.4` `:LA:DELete` — guide p. 135
- [x] `3.13.5` `:LA:DIGital:ENABle` — guide p. 135
- [x] `3.13.6` `:LA:DIGital:LABel` — guide p. 136
- [x] `3.13.7` `:LA:POD<n>:DISPlay` — guide p. 137
- [x] `3.13.8` `:LA:POD<n>:THReshold` — guide p. 137
- [x] `3.13.9` `:LA:SIZE` — guide p. 138

### 14. LAN (15)

- [x] `3.14.1` `:LAN:DHCP` — guide p. 139
- [x] `3.14.2` `:LAN:AUToip` — guide p. 140
- [x] `3.14.3` `:LAN:GATeway` — guide p. 140
- [x] `3.14.4` `:LAN:DNS` — guide p. 141
- [x] `3.14.5` `:LAN:MAC?` — guide p. 142
- [x] `3.14.6` `:LAN:DSERver?` — guide p. 142
- [x] `3.14.7` `:LAN:MANual` — guide p. 143
- [x] `3.14.8` `:LAN:IPADdress` — guide p. 143
- [x] `3.14.9` `:LAN:SMASk` — guide p. 144
- [x] `3.14.10` `:LAN:STATus?` — guide p. 145
- [x] `3.14.11` `:LAN:VISA?` — guide p. 145
- [x] `3.14.12` `:LAN:MDNS` — guide p. 146
- [x] `3.14.13` `:LAN:HOST:NAME` — guide p. 147
- [x] `3.14.14` `:LAN:DESCription` — guide p. 147
- [x] `3.14.15` `:LAN:APPLy` — guide p. 148

### 15. Mask and pass/fail (13)

- [x] `3.15.1` `:MASK:ENABle` — guide p. 148
- [x] `3.15.2` `:MASK:SOURce` — guide p. 149
- [x] `3.15.3` `:MASK:OPERate` — guide p. 150
- [x] `3.15.4` `:MASK:X` — guide p. 150
- [x] `3.15.5` `:MASK:Y` — guide p. 151
- [x] `3.15.6` `:MASK:CREate` — guide p. 152
- [x] `3.15.7` `:MASK:RESet` — guide p. 152
- [x] `3.15.8` `:MASK:FAILed?` — guide p. 153
- [x] `3.15.9` `:MASK:PASSed?` — guide p. 153
- [x] `3.15.10` `:MASK:TOTal?` — guide p. 154
- [x] `3.15.11` `:MASK:OUTPut:ENABle` — guide p. 154
- [x] `3.15.12` `:MASK:OUTPut:EVENt` — guide p. 155
- [x] `3.15.13` `:MASK:OUTPut:TIME` — guide p. 155

### 16. Math (39)

- [x] `3.16.1` `:MATH<n>:DISPlay` — guide p. 159
- [x] `3.16.2` `:MATH<n>:OPERator` — guide p. 160
- [x] `3.16.3` `:MATH<n>:SOURce1` — guide p. 160
- [x] `3.16.4` `:MATH<n>:SOURce2` — guide p. 162
- [x] `3.16.5` `:MATH<n>:LSOurce1` — guide p. 163
- [x] `3.16.6` `:MATH<n>:LSOurce2` — guide p. 163
- [x] `3.16.7` `:MATH<n>:SCALe` — guide p. 164
- [x] `3.16.8` `:MATH<n>:OFFSet` — guide p. 165
- [x] `3.16.9` `:MATH<n>:INVert` — guide p. 166
- [x] `3.16.10` `:MATH<n>:RESet` — guide p. 166
- [x] `3.16.11` `:MATH<n>:GRID` — guide p. 167
- [x] `3.16.12` `:MATH<n>:EXPand` — guide p. 167
- [x] `3.16.13` `:MATH<n>:WAVetype` — guide p. 168
- [x] `3.16.14` `:MATH<n>:FFT:SOURce` — guide p. 169
- [x] `3.16.15` `:MATH<n>:FFT:WINDow` — guide p. 169
- [x] `3.16.16` `:MATH<n>:FFT:UNIT` — guide p. 170
- [x] `3.16.17` `:MATH<n>:FFT:SCALe` — guide p. 171
- [x] `3.16.18` `:MATH<n>:FFT:OFFSet` — guide p. 172
- [x] `3.16.19` `:MATH<n>:FFT:HSCale` — guide p. 173
- [x] `3.16.20` `:MATH<n>:FFT:HCENter` — guide p. 173
- [x] `3.16.21` `:MATH<n>:FFT:FREQuency:STARt` — guide p. 174
- [x] `3.16.22` `:MATH<n>:FFT:FREQuency:END` — guide p. 175
- [x] `3.16.23` `:MATH<n>:FFT:SEARch:ENABle` — guide p. 175
- [x] `3.16.24` `:MATH<n>:FFT:SEARch:NUM` — guide p. 176
- [x] `3.16.25` `:MATH<n>:FFT:SEARch:THReshold` — guide p. 177
- [x] `3.16.26` `:MATH<n>:FFT:SEARch:EXCursion` — guide p. 177
- [x] `3.16.27` `:MATH<n>:FFT:SEARch:ORDer` — guide p. 178
- [x] `3.16.28` `:MATH<n>:FFT:SEARch:RES?` — guide p. 178
- [x] `3.16.29` `:MATH<n>:FILTer:TYPE` — guide p. 179
- [x] `3.16.30` `:MATH<n>:FILTer:W1` — guide p. 180
- [x] `3.16.31` `:MATH<n>:FILTer:W2` — guide p. 181
- [x] `3.16.32` `:MATH<n>:SENSitivity` — guide p. 182
- [x] `3.16.33` `:MATH<n>:DISTance` — guide p. 183
- [x] `3.16.34` `:MATH<n>:THReshold1` — guide p. 183
- [x] `3.16.35` `:MATH<n>:THReshold2` — guide p. 184
- [x] `3.16.36` `:MATH<n>:THReshold3` — guide p. 185
- [x] `3.16.37` `:MATH<n>:THReshold4` — guide p. 186
- [x] `3.16.38` `:MATH<n>:WINDow:TITLe?` — guide p. 187
- [x] `3.16.39` `:MATH<n>:LABel:SHOW` — guide p. 187

### 17. Measurements (27)

- [x] `3.17.1` `:MEASure:SOURce` — guide p. 194
- [x] `3.17.2` `:MEASure:ITEM` — guide p. 195
- [x] `3.17.3` `:MEASure:CLEar` — guide p. 196
- [x] `3.17.4` `:MEASure:AMSource` — guide p. 197
- [x] `3.17.5` `:MEASure:STATistic:COUNt` — guide p. 197
- [x] `3.17.6` `:MEASure:STATistic:DISPlay` — guide p. 198
- [x] `3.17.7` `:MEASure:STATistic:RESet` — guide p. 199
- [x] `3.17.8` `:MEASure:STATistic:ITEM` — guide p. 199
- [x] `3.17.9` `:MEASure:SETup:MAX` — guide p. 201
- [x] `3.17.10` `:MEASure:SETup:MID` — guide p. 202
- [x] `3.17.11` `:MEASure:SETup:MIN` — guide p. 203
- [x] `3.17.12` `:MEASure:SETup:PSA` — guide p. 203
- [x] `3.17.13` `:MEASure:SETup:PSB` — guide p. 204
- [x] `3.17.14` `:MEASure:SETup:DSA` — guide p. 205
- [x] `3.17.15` `:MEASure:SETup:DSB` — guide p. 206
- [x] `3.17.16` `:MEASure:THReshold:SOURce` — guide p. 206
- [x] `3.17.17` `:MEASure:THReshold:TYPE` — guide p. 207
- [x] `3.17.18` `:MEASure:THReshold:DEFault` — guide p. 208
- [x] `3.17.19` `:MEASure:AREA` — guide p. 208
- [x] `3.17.20` `:MEASure:INDicator` — guide p. 209
- [x] `3.17.21` `:MEASure:COUNter:ENABle` — guide p. 209
- [x] `3.17.22` `:MEASure:COUNter:SOURce` — guide p. 210
- [x] `3.17.23` `:MEASure:COUNter:VALue?` — guide p. 211
- [x] `3.17.24` `:MEASure:AMP:TYPE` — guide p. 211
- [x] `3.17.25` `:MEASure:AMP:MANual:TOP` — guide p. 212
- [x] `3.17.26` `:MEASure:AMP:MANual:BASE` — guide p. 212
- [x] `3.17.27` `:MEASure:CATegory` — guide p. 213

### 18. Quick (1)

- [x] `3.18.1` `:QUICk:OPERation` — guide p. 214

### 19. Recording (24)

- [x] `3.19.1` `:RECord:WRECord:ENABle` — guide p. 215
- [x] `3.19.2` `:RECord:ENABle` — guide p. 215
- [x] `3.19.3` `:RECord:WRECord:OPERate` — guide p. 216
- [x] `3.19.4` `:RECord:STARt` — guide p. 217
- [x] `3.19.5` `:RECord:WRECord:FRAMes` — guide p. 217
- [x] `3.19.6` `:RECord:FRAMes` — guide p. 218
- [x] `3.19.7` `:RECord:WRECord:FRAMes:MAX` — guide p. 218
- [x] `3.19.9` `:RECord:WRECord:FINTerval` — guide p. 219
- [x] `3.19.10` `:RECord:WRECord:PROMpt` — guide p. 220
- [x] `3.19.11` `:RECord:WREPlay:FCURrent` — guide p. 220
- [x] `3.19.12` `:RECord:CURRent` — guide p. 221
- [x] `3.19.13` `:RECord:WREPlay:FCURrent:TIME?` — guide p. 222
- [x] `3.19.14` `:RECord:WREPlay:FSTart` — guide p. 222
- [x] `3.19.15` `:RECord:WREPlay:FEND` — guide p. 223
- [x] `3.19.16` `:RECord:WREPlay:FMAX?` — guide p. 223
- [x] `3.19.17` `:RECord:WREPlay:FINTerval` — guide p. 224
- [x] `3.19.18` `:RECord:WREPlay:MODE` — guide p. 224
- [x] `3.19.19` `:RECord:WREPlay:DIRection` — guide p. 225
- [x] `3.19.20` `:RECord:WREPlay:OPERate` — guide p. 226
- [x] `3.19.21` `:RECord:PLAY` — guide p. 226
- [x] `3.19.22` `:RECord:WREPlay:BACK` — guide p. 227
- [x] `3.19.23` `:RECord:WREPlay:NEXT` — guide p. 227
- [x] `3.19.24` `:RECord:WREPlay:PLAY` — guide p. 228
- [x] `3.19.8` `:RECord:WRECord:FMAX?` — guide p. 219

### 20. Reference (9)

- [x] `3.20.1` `:REFerence:SOURce` — guide p. 228
- [x] `3.20.2` `:REFerence:VSCale` — guide p. 229
- [x] `3.20.3` `:REFerence:VOFFset` — guide p. 230
- [x] `3.20.4` `:REFerence:RESet` — guide p. 230
- [x] `3.20.5` `:REFerence:CURRent` — guide p. 231
- [x] `3.20.6` `:REFerence:SAVE` — guide p. 231
- [x] `3.20.7` `:REFerence:COLor` — guide p. 232
- [x] `3.20.8` `:REFerence:LABel:ENABle` — guide p. 233
- [x] `3.20.9` `:REFerence:LABel:CONTent` — guide p. 233

### 21. Save and load (20)

- [x] `3.21.1` `:SAVE:IMAGe:INVert` — guide p. 234
- [x] `3.21.2` `:SAVE:IMAGe:COLor` — guide p. 235
- [x] `3.21.3` `:SAVE:IMAGe:FORMat` — guide p. 235
- [x] `3.21.4` `:SAVE:IMAGe:HEADer` — guide p. 236
- [x] `3.21.5` `:SAVE:IMAGe:DATA?` — guide p. 236
- [x] `3.21.6` `:SAVE:IMAGe` — guide p. 237
- [x] `3.21.7` `:SAVE:SETup` — guide p. 238
- [x] `3.21.8` `:SAVE:WAVeform` — guide p. 239
- [x] `3.21.9` `:SAVE:MEMory:WAVeform` — guide p. 240
- [x] `3.21.10` `:SAVE:STATus?` — guide p. 240
- [x] `3.21.11` `:SAVE:OVERlap` — guide p. 241
- [x] `3.21.12` `:SAVE:PREFix` — guide p. 241
- [x] `3.21.13` `:SAVe:SMB:SERVerpath` — guide p. 242
- [x] `3.21.14` `:SAVe:SMB:USERname` — guide p. 243
- [x] `3.21.15` `:SAVe:SMB:PASSword` — guide p. 243
- [x] `3.21.16` `:SAVe:SMB:AUToconnect` — guide p. 244
- [x] `3.21.17` `:SAVe:SMB:CONNect` — guide p. 245
- [x] `3.21.18` `:SAVe:SMB:DISConnect` — guide p. 245
- [x] `3.21.19` `:SAVe:SMB:CONState?` — guide p. 245
- [x] `3.21.20` `:LOAD:SETup` — guide p. 246

### 22. Search (14)

- [x] `3.22.1` `:SEARch:COUNt?` — guide p. 247
- [x] `3.22.2` `:SEARch:STATe` — guide p. 247
- [x] `3.22.3` `:SEARch:MODE` — guide p. 248
- [x] `3.22.4` `:SEARch:EVENt` — guide p. 248
- [x] `3.22.5` `:SEARch:VALue?` — guide p. 249
- [x] `3.22.6` `:SEARch:EDGE:SLOPe` — guide p. 249
- [x] `3.22.7` `:SEARch:EDGE:SOURce` — guide p. 250
- [x] `3.22.8` `:SEARch:EDGE:THReshold` — guide p. 251
- [x] `3.22.9` `:SEARch:PULSe:POLarity` — guide p. 251
- [x] `3.22.10` `:SEARch:PULSe:QUALifier` — guide p. 252
- [x] `3.22.11` `:SEARch:PULSe:SOURce` — guide p. 253
- [x] `3.22.12` `:SEARch:PULSe:UWIDth` — guide p. 253
- [x] `3.22.13` `:SEARch:PULSe:LWIDth` — guide p. 254
- [x] `3.22.14` `:SEARch:PULSe:THReshold` — guide p. 254

### 23. Navigation (20)

- [x] `3.23.1` `:NAVigate:ENABle` — guide p. 255
- [x] `3.23.2` `:NAVigate:MODE` — guide p. 256
- [x] `3.23.3` `:NAVigate:TIME:SPEed` — guide p. 256
- [x] `3.23.4` `:NAVigate:TIME:PLAY` — guide p. 257
- [x] `3.23.5` `:NAVigate:TIME:END` — guide p. 258
- [x] `3.23.6` `:NAVigate:TIME:STARt` — guide p. 258
- [x] `3.23.7` `:NAVigate:TIME:NEXT` — guide p. 259
- [x] `3.23.8` `:NAVigate:TIME:BACK` — guide p. 259
- [x] `3.23.9` `:NAVigate:SEARch:END` — guide p. 260
- [x] `3.23.10` `:NAVigate:SEARch:STARt` — guide p. 260
- [x] `3.23.11` `:NAVigate:SEARch:NEXT` — guide p. 260
- [x] `3.23.12` `:NAVigate:SEARch:BACK` — guide p. 261
- [x] `3.23.13` `:NAVigate:FRAMe:DISPlay:MODE` — guide p. 261
- [x] `3.23.14` `:NAVigate:FRAMe:END:FRAMe` — guide p. 263
- [x] `3.23.15` `:NAVigate:FRAMe:STARt:FRAMe` — guide p. 263
- [x] `3.23.16` `:NAVigate:FRAMe:END` — guide p. 264
- [x] `3.23.17` `:NAVigate:FRAMe:STARt` — guide p. 264
- [x] `3.23.18` `:NAVigate:FRAMe:NEXT` — guide p. 265
- [x] `3.23.19` `:NAVigate:FRAMe:BACK` — guide p. 265
- [x] `3.23.20` `:NAVigate:FRAMe:PLAY` — guide p. 266

### 24. System (15)

- [x] `3.24.1` `:SYSTem:AOUTput` — guide p. 267
- [x] `3.24.2` `:SYSTem:BEEPer` — guide p. 267
- [x] `3.24.3` `:SYSTem:ERRor[:NEXT]?` — guide p. 268
- [x] `3.24.4` `:SYSTem:PON` — guide p. 268
- [x] `3.24.5` `:SYSTem:PSTatus` — guide p. 269
- [x] `3.24.6` `:SYSTem:RAMount?` — guide p. 270
- [x] `3.24.7` `:SYSTem:RESet` — guide p. 270
- [x] `3.24.8` `:SYSTem:SETup` — guide p. 270
- [x] `3.24.9` `:SYSTem:LOCKed` — guide p. 271
- [x] `3.24.10` `:SYSTem:MODules?` — guide p. 272
- [x] `3.24.11` `:SYSTem:AUToscale` — guide p. 272
- [x] `3.24.12` `:SYSTem:GAMount?` — guide p. 273
- [x] `3.24.13` `:SYSTem:VERSion?` — guide p. 274
- [x] `3.24.14` `:SYSTem:DGSTatus?` — guide p. 274
- [x] `3.24.15` `:SYSTem:KEYBOARDCheck?` — guide p. 275

### 25. AFG source (19)

- [x] `3.25.1` `:SOURce:OUTPut:STATe` — guide p. 275
- [x] `3.25.2` `:SOURce:FUNCtion` — guide p. 276
- [x] `3.25.3` `:SOURce:FREQuency` — guide p. 276
- [x] `3.25.4` `:SOURce:PHASe` — guide p. 277
- [x] `3.25.5` `:SOURce:FUNCtion:RAMP:SYMMetry` — guide p. 278
- [x] `3.25.6` `:SOURce:FUNCtion:SQUare:DUTY` — guide p. 279
- [x] `3.25.7` `:SOURce:VOLTage:AMPLitude` — guide p. 279
- [x] `3.25.8` `:SOURce:VOLTage:OFFSet` — guide p. 280
- [x] `3.25.9` `:SOURce:MOD:STATe` — guide p. 281
- [x] `3.25.10` `:SOURce:MOD:TYPe` — guide p. 281
- [x] `3.25.11` `:SOURce:MOD:AM:DEPTh` — guide p. 282
- [x] `3.25.12` `:SOURce:MOD:AM:INTernal:FREQuency` — guide p. 283
- [x] `3.25.13` `:SOURce:MOD:AM:INTernal:FUNCtion` — guide p. 283
- [x] `3.25.14` `:SOURce:MOD:FM:DEViation` — guide p. 284
- [x] `3.25.15` `:SOURce:MOD:FM:INTernal:FREQuency` — guide p. 285
- [x] `3.25.16` `:SOURce:MOD:FM:INTernal:FUNCtion` — guide p. 286
- [x] `3.25.17` `:SOURce:MOD:PM:DEViation` — guide p. 286
- [x] `3.25.18` `:SOURce:MOD:PM:INTernal:FREQuency` — guide p. 287
- [x] `3.25.19` `:SOURce:MOD:PM:INTernal:FUNCtion` — guide p. 288

### 26. Timebase (16)

- [x] `3.26.1` `:TIMebase:DELay:ENABle` — guide p. 289
- [x] `3.26.2` `:TIMebase:DELay:OFFSet` — guide p. 290
- [x] `3.26.3` `:TIMebase:DELay:SCALe` — guide p. 291
- [x] `3.26.4` `:TIMebase[:MAIN][:OFFSet]` — guide p. 291
- [x] `3.26.5` `:TIMebase[:MAIN]:SCALe` — guide p. 292
- [x] `3.26.6` `:TIMebase:MODE` — guide p. 293
- [x] `3.26.7` `:TIMebase:HREFerence:MODE` — guide p. 294
- [x] `3.26.8` `:TIMebase:HREFerence:POSition` — guide p. 295
- [x] `3.26.9` `:TIMebase:VERNier` — guide p. 295
- [x] `3.26.10` `:TIMebase:HOTKeys` — guide p. 296
- [x] `3.26.11` `:TIMebase:ROLL` — guide p. 296
- [x] `3.26.12` `:TIMebase:XY:ENABle` — guide p. 297
- [x] `3.26.13` `:TIMebase:XY:X` — guide p. 298
- [x] `3.26.14` `:TIMebase:XY:Y` — guide p. 298
- [x] `3.26.15` `:TIMebase:XY:Z` — guide p. 299
- [x] `3.26.16` `:TIMebase:XY:GRID` — guide p. 299

### 27. Trigger (139)

- [x] `3.27.1` `:TRIGger:MODE` — guide p. 300
- [x] `3.27.2` `:TRIGger:COUPling` — guide p. 301
- [x] `3.27.3` `:TRIGger:STATus?` — guide p. 302
- [x] `3.27.4` `:TRIGger:SWEep` — guide p. 302
- [x] `3.27.5` `:TRIGger:HOLDoff` — guide p. 303
- [x] `3.27.6` `:TRIGger:NREJect` — guide p. 304
- [x] `3.27.7` `:TRIGger:POSition?` — guide p. 304
- [x] `3.27.8.1` `:TRIGger:EDGE:SOURce` — guide p. 305
- [x] `3.27.8.2` `:TRIGger:EDGE:SLOPe` — guide p. 306
- [x] `3.27.8.3` `:TRIGger:EDGE:LEVel` — guide p. 306
- [x] `3.27.9.1` `:TRIGger:PULSe:SOURce` — guide p. 307
- [x] `3.27.9.2` `:TRIGger:PULSe:POLarity` — guide p. 308
- [x] `3.27.9.3` `:TRIGger:PULSe:WHEN` — guide p. 309
- [x] `3.27.9.4` `:TRIGger:PULSe:UWIDth` — guide p. 309
- [x] `3.27.9.5` `:TRIGger:PULSe:LWIDth` — guide p. 310
- [x] `3.27.9.6` `:TRIGger:PULSe:LEVel` — guide p. 311
- [x] `3.27.10.1` `:TRIGger:SLOPe:SOURce` — guide p. 312
- [x] `3.27.10.2` `:TRIGger:SLOPe:POLarity` — guide p. 312
- [x] `3.27.10.3` `:TRIGger:SLOPe:WHEN` — guide p. 313
- [x] `3.27.10.4` `:TRIGger:SLOPe:TUPPer` — guide p. 314
- [x] `3.27.10.5` `:TRIGger:SLOPe:TLOWer` — guide p. 314
- [x] `3.27.10.6` `:TRIGger:SLOPe:WINDow` — guide p. 315
- [x] `3.27.10.7` `:TRIGger:SLOPe:ALEVel` — guide p. 316
- [x] `3.27.10.8` `:TRIGger:SLOPe:BLEVel` — guide p. 316
- [x] `3.27.11.1` `:TRIGger:VIDeo:SOURce` — guide p. 317
- [x] `3.27.11.2` `:TRIGger:VIDeo:POLarity` — guide p. 318
- [x] `3.27.11.3` `:TRIGger:VIDeo:MODE` — guide p. 318
- [x] `3.27.11.4` `:TRIGger:VIDeo:LINE` — guide p. 319
- [x] `3.27.11.5` `:TRIGger:VIDeo:STANdard` — guide p. 320
- [x] `3.27.11.6` `:TRIGger:VIDeo:LEVel` — guide p. 321
- [x] `3.27.12.1` `:TRIGger:PATTern:PATTern` — guide p. 322
- [x] `3.27.12.2` `:TRIGger:PATTern:SOURce` — guide p. 323
- [x] `3.27.12.3` `:TRIGger:PATTern:LEVel` — guide p. 324
- [x] `3.27.13.1` `:TRIGger:DURation:SOURce` — guide p. 326
- [x] `3.27.13.2` `:TRIGger:DURation:TYPE` — guide p. 326
- [x] `3.27.13.3` `:TRIGger:DURation:WHEN` — guide p. 327
- [x] `3.27.13.4` `:TRIGger:DURation:TUPPer` — guide p. 328
- [x] `3.27.13.5` `:TRIGger:DURation:TLOWer` — guide p. 329
- [x] `3.27.13.6` `:TRIGger:DURation:LEVel` — guide p. 330
- [x] `3.27.14.1` `:TRIGger:TIMeout:SOURce` — guide p. 331
- [x] `3.27.14.2` `:TRIGger:TIMeout:SLOPe` — guide p. 331
- [x] `3.27.14.3` `:TRIGger:TIMeout:TIME` — guide p. 332
- [x] `3.27.14.4` `:TRIGger:TIMeout:LEVel` — guide p. 333
- [x] `3.27.15.1` `:TRIGger:RUNT:SOURce` — guide p. 334
- [x] `3.27.15.2` `:TRIGger:RUNT:POLarity` — guide p. 334
- [x] `3.27.15.3` `:TRIGger:RUNT:WHEN` — guide p. 335
- [x] `3.27.15.4` `:TRIGger:RUNT:WUPPer` — guide p. 336
- [x] `3.27.15.5` `:TRIGger:RUNT:WLOWer` — guide p. 337
- [x] `3.27.15.6` `:TRIGger:RUNT:ALEVel` — guide p. 337
- [x] `3.27.15.7` `:TRIGger:RUNT:BLEVel` — guide p. 338
- [x] `3.27.16.1` `:TRIGger:WINDows:SOURce` — guide p. 339
- [x] `3.27.16.2` `:TRIGger:WINDows:SLOPe` — guide p. 339
- [x] `3.27.16.3` `:TRIGger:WINDows:POSition` — guide p. 340
- [x] `3.27.16.4` `:TRIGger:WINDows:TIME` — guide p. 341
- [x] `3.27.16.5` `:TRIGger:WINDows:ALEVel` — guide p. 341
- [x] `3.27.16.6` `:TRIGger:WINDows:BLEVel` — guide p. 342
- [x] `3.27.17.1` `:TRIGger:DELay:SA` — guide p. 343
- [x] `3.27.17.2` `:TRIGger:DELay:ASLop` — guide p. 343
- [x] `3.27.17.3` `:TRIGger:DELay:SB` — guide p. 344
- [x] `3.27.17.4` `:TRIGger:DELay:BSLop` — guide p. 345
- [x] `3.27.17.5` `:TRIGger:DELay:TYPE` — guide p. 345
- [x] `3.27.17.6` `:TRIGger:DELay:TUPPer` — guide p. 346
- [x] `3.27.17.7` `:TRIGger:DELay:TLOWer` — guide p. 347
- [x] `3.27.17.8` `:TRIGger:DELay:ALEVel` — guide p. 348
- [x] `3.27.17.9` `:TRIGger:DELay:BLEVel` — guide p. 348
- [x] `3.27.18.1` `:TRIGger:SHOLd:DSRC` — guide p. 349
- [x] `3.27.18.2` `:TRIGger:SHOLd:CSRC` — guide p. 350
- [x] `3.27.18.3` `:TRIGger:SHOLd:SLOPe` — guide p. 351
- [x] `3.27.18.4` `:TRIGger:SHOLd:PATTern` — guide p. 351
- [x] `3.27.18.5` `:TRIGger:SHOLd:TYPE` — guide p. 352
- [x] `3.27.18.6` `:TRIGger:SHOLd:STIMe` — guide p. 353
- [x] `3.27.18.7` `:TRIGger:SHOLd:HTIMe` — guide p. 353
- [x] `3.27.18.8` `:TRIGger:SHOLd:DLEVel` — guide p. 354
- [x] `3.27.18.9` `:TRIGger:SHOLd:CLEVel` — guide p. 355
- [x] `3.27.19.1` `:TRIGger:NEDGe:SOURce` — guide p. 356
- [x] `3.27.19.2` `:TRIGger:NEDGe:SLOPe` — guide p. 357
- [x] `3.27.19.3` `:TRIGger:NEDGe:IDLE` — guide p. 357
- [x] `3.27.19.4` `:TRIGger:NEDGe:EDGE` — guide p. 358
- [x] `3.27.19.5` `:TRIGger:NEDGe:LEVel` — guide p. 358
- [x] `3.27.20.1` `:TRIGger:RS232:SOURce` — guide p. 359
- [x] `3.27.20.2` `:TRIGger:RS232:LEVel` — guide p. 360
- [x] `3.27.20.3` `:TRIGger:RS232:POLarity` — guide p. 361
- [x] `3.27.20.4` `:TRIGger:RS232:WHEN` — guide p. 361
- [x] `3.27.20.5` `:TRIGger:RS232:DATA` — guide p. 362
- [x] `3.27.20.6` `:TRIGger:RS232:BAUD` — guide p. 363
- [x] `3.27.20.7` `:TRIGger:RS232:WIDTh` — guide p. 363
- [x] `3.27.20.8` `:TRIGger:RS232:STOP` — guide p. 364
- [x] `3.27.20.9` `:TRIGger:RS232:PARity` — guide p. 364
- [x] `3.27.21.1` `:TRIGger:IIC:SCL` — guide p. 365
- [x] `3.27.21.2` `:TRIGger:IIC:CLEVel` — guide p. 366
- [x] `3.27.21.3` `:TRIGger:IIC:SDA` — guide p. 367
- [x] `3.27.21.4` `:TRIGger:IIC:DLEVel` — guide p. 367
- [x] `3.27.21.5` `:TRIGger:IIC:WHEN` — guide p. 368
- [x] `3.27.21.6` `:TRIGger:IIC:AWIDth` — guide p. 369
- [x] `3.27.21.7` `:TRIGger:IIC:ADDRess` — guide p. 370
- [x] `3.27.21.8` `:TRIGger:IIC:DIRection` — guide p. 370
- [x] `3.27.21.9` `:TRIGger:IIC:DBYTes` — guide p. 371
- [x] `3.27.21.10` `:TRIGger:IIC:DATA` — guide p. 371
- [x] `3.27.21.11` `:TRIGger:IIC:CURRbit` — guide p. 372
- [x] `3.27.21.12` `:TRIGger:IIC:CODE` — guide p. 373
- [x] `3.27.22.1` `:TRIGger:SPI:CLK` — guide p. 374
- [x] `3.27.22.2` `:TRIGger:SPI:SCL` — guide p. 374
- [x] `3.27.22.3` `:TRIGger:SPI:CLEVel` — guide p. 375
- [x] `3.27.22.4` `:TRIGger:SPI:SLOPe` — guide p. 376
- [x] `3.27.22.5` `:TRIGger:SPI:MISO` — guide p. 376
- [x] `3.27.22.6` `:TRIGger:SPI:SDA` — guide p. 377
- [x] `3.27.22.7` `:TRIGger:SPI:DLEVel` — guide p. 378
- [x] `3.27.22.8` `:TRIGger:SPI:WHEN` — guide p. 378
- [x] `3.27.22.9` `:TRIGger:SPI:CS` — guide p. 379
- [x] `3.27.22.10` `:TRIGger:SPI:SLEVel` — guide p. 380
- [x] `3.27.22.11` `:TRIGger:SPI:MODE` — guide p. 381
- [x] `3.27.22.12` `:TRIGger:SPI:TIMeout` — guide p. 381
- [x] `3.27.22.13` `:TRIGger:SPI:WIDTh` — guide p. 382
- [x] `3.27.22.14` `:TRIGger:SPI:DATA` — guide p. 382
- [x] `3.27.22.15` `:TRIGger:SPI:CURRbit` — guide p. 383
- [x] `3.27.22.16` `:TRIGger:SPI:CODE` — guide p. 384
- [x] `3.27.23.1` `:TRIGger:CAN:BAUD` — guide p. 385
- [x] `3.27.23.2` `:TRIGger:CAN:SOURce` — guide p. 385
- [x] `3.27.23.3` `:TRIGger:CAN:STYPe` — guide p. 386
- [x] `3.27.23.4` `:TRIGger:CAN:WHEN` — guide p. 387
- [x] `3.27.23.5` `:TRIGger:CAN:SPOint` — guide p. 388
- [x] `3.27.23.6` `:TRIGger:CAN:EXTended` — guide p. 389
- [x] `3.27.23.7` `:TRIGger:CAN:DEFine` — guide p. 390
- [x] `3.27.23.8` `:TRIGger:CAN:DWIDth` — guide p. 390
- [x] `3.27.23.9` `:TRIGger:CAN:DATA` — guide p. 391
- [x] `3.27.23.10` `:TRIGger:CAN:CURRbit` — guide p. 392
- [x] `3.27.23.11` `:TRIGger:CAN:CODE` — guide p. 392
- [x] `3.27.23.12` `:TRIGger:CAN:LEVel` — guide p. 393
- [x] `3.27.24.1` `:TRIGger:LIN:SOURce` — guide p. 394
- [x] `3.27.24.2` `:TRIGger:LIN:LEVel` — guide p. 395
- [x] `3.27.24.3` `:TRIGger:LIN:STANdard` — guide p. 395
- [x] `3.27.24.4` `:TRIGger:LIN:BAUD` — guide p. 396
- [x] `3.27.24.5` `:TRIGger:LIN:SAMPlepoint` — guide p. 397
- [x] `3.27.24.6` `:TRIGger:LIN:WHEN` — guide p. 397
- [x] `3.27.24.7` `:TRIGger:LIN:ERRor` — guide p. 398
- [x] `3.27.24.8` `:TRIGger:LIN:ID` — guide p. 399
- [x] `3.27.24.9` `:TRIGger:LIN:DATA` — guide p. 399
- [x] `3.27.24.10` `:TRIGger:LIN:CURRbit` — guide p. 400
- [x] `3.27.24.11` `:TRIGger:LIN:CODE` — guide p. 400

### 28. Waveform (14)

- [x] `3.28.1` `:WAVeform:SOURce` — guide p. 404
- [x] `3.28.2` `:WAVeform:MODE` — guide p. 405
- [x] `3.28.3` `:WAVeform:FORMat` — guide p. 406
- [x] `3.28.4` `:WAVeform:POINts` — guide p. 406
- [x] `3.28.5` `:WAVeform:DATA?` — guide p. 407
- [x] `3.28.6` `:WAVeform:XINCrement?` — guide p. 408
- [x] `3.28.7` `:WAVeform:XORigin?` — guide p. 408
- [x] `3.28.8` `:WAVeform:XREFerence?` — guide p. 409
- [x] `3.28.9` `:WAVeform:YINCrement?` — guide p. 410
- [x] `3.28.10` `:WAVeform:YORigin?` — guide p. 410
- [x] `3.28.11` `:WAVeform:YREFerence?` — guide p. 411
- [x] `3.28.12` `:WAVeform:STARt` — guide p. 411
- [x] `3.28.13` `:WAVeform:STOP` — guide p. 412
- [x] `3.28.14` `:WAVeform:PREamble?` — guide p. 413

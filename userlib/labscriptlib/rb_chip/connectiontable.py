from labscript import *
from labscript_devices.PulseBlaster import PulseBlaster
from labscript_devices.ChipFPGA import ChipFPGA


PulseBlaster(name='pulseblaster_0', board_number=0)
ClockLine(name='pulseblaster_0_clockline', pseudoclock=pulseblaster_0.pseudoclock, connection='flag 0')
ChipFPGA(name='chipfpga', parent_device=pulseblaster_0_clockline, visa_resource="ASRL7::INSTR")

start()
#t = 0
#a = 0
#for i in range(10):
#	t += 0.5
#	a += 0.1
#	chipfpga_wire00amp.constant(t, a)
#t = 0.3
#chipfpga_wire01amp.constant(t, 2.0)

#print chipfpga_wire00amp.instructions

#t = 8

stop(1)

#print chipfpga_wire00amp.raw_output
#print chipfpga_wire01amp.raw_output
from __future__ import division, print_function

from labscript import *
from labscriptlib.common.functions import *

shared_connectiontable = labscript_import('labscriptlib.rb_chip.shared.shared_connectiontable')        

def stage(func):
    """A decorator for functions that represent stages of the experiment.
    
    Assumes first argument to function is the stage's start time, and return value is
    its duration (which is a convention we normally follow throughout labscript).
    
    The resulting decorated function simply prints the name of the stage and its start and end
    times when the function is called."""
    import functools
    @functools.wraps(func)
    def f(t, *args, **kwargs):
        duration = func(t, *args, **kwargs)
        try:
            float(duration)
        except Exception:
            raise TypeError("Stage function %s must return its duration, even if zero"%func.__name__)
        print('%s: %s sec to %s sec'%(func.__name__, str(t), str(t + duration)))
        return duration
    return f
    
    
@stage
def prep(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    shutter_MOT_repump.go_high(t)
    camera_trigger_0.go_high(t)    
    AOM_MOT_cooling.go_high(t)
    shutter_MOT_cooling.go_high(t)
    AOM_probe_2.go_high(t)
    camera_trigger_1.go_high(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_enable.go_high(t)
    
    # ni_usb_6343_1 digital outputs:
    kepco_enable_0.go_high(t)
    kepco_enable_1.go_high(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t,  UVMOTRepump)
    MOT_cooling.constant(t, UVMOTAmplitude)
    probe_2.constant(t,     ProbeInt)
    dipole_shutter.go_high(t)
   
   # ni_pci_6733_1 analog outputs:
    microwave_attenuator.constant(t, 6.0)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_2.constant(t, UVMOTCurrent, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 2.11*UVxShim, units='A')
    y_bias.constant(t,      UVyShim, units='A')
    z_bias.constant(t, -0.8*UVzShim, units='A')
    
    # ni_usb_6343_2 outputs:
    mixer_raman_1.constant(t, 0.31)
    mixer_raman_1.constant(t+0.01, 0.0)
    shutter_greenbeam.go_high(t)
    green_beam.go_low(t)
    AOM_green_beam.constant(t, -0.5)
    green_servo_trigger.go_low(t)
    
    # novatechdds9m_0 channel outputs:
    MOT_lock.setfreq(t,  (ResFreq + UVMOTFreq)*MHz)
    MOT_lock.setamp(t,  0.7077) # 0 dBm
    RF_evap.setfreq(t,  30*MHz)
    RF_mixer1.constant(t, 0)
    
    # novatechdds9m_1 channel outputs:
    uwave1.setfreq(t, 100*MHz)
    uwave1.setamp(t, 0.0) # -80dBm
    
    fluxgate_trig.go_high(t)
    
    return 30*ms
    

@stage    
def UVMOT(t):
    # ni_pci_6733_0 digital outputs:
    UV_LED.go_high(t)
    return UV_MOT_time
    
    
@stage    
def cMOT(t):
    # ni_pci_6733_0 digital outputs:
    UV_LED.go_low(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.customramp(t,  MOT_time, HalfGaussRamp, RepumpMOT, RepumpCMOT, CMOTCaptureWidth, samplerate=1/step_cMOT)
    MOT_cooling.constant(t,   MOTAmplitude)
        
    # ni_usb_6343_0 analog outputs:
    transport_current_2.customramp(t, MOT_time, HalfGaussRamp, MOTCurrent, CMOTCurrent, CMOTCaptureWidth, samplerate=1/step_cMOT, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 2.11*MOTxShim, units='A')
    y_bias.constant(t,      MOTyShim, units='A')
    z_bias.constant(t, -0.8*MOTzShim, units='A')

    # novatechdds9m_0 channel outputs:
    MOT_lock.frequency.customramp(t,  MOT_time, HalfGaussRamp, MOTFreq + ResFreq, CMOTFreq + ResFreq, CMOTCaptureWidth, samplerate=1/step_cMOT, units='MHz')
     
    return MOT_time
    

@stage
def molasses(t):
    # pulseblaster_0 outputs:
    shutter_optical_pumping.go_high(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_enable.go_low(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, RepumpMol)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_2.constant(t, MOTCurrent, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 2.11*0.44, units='A')
    y_bias.constant(t, 0.42, units='A')
    z_bias.constant(t, -0.8*-0.04, units='A')
    
    # novatechdds9m_0 channel outputs:
    MOT_lock.frequency.customramp(t, TimeMol, ExpRamp, StartFreqMol + ResFreq , EndFreqMol + ResFreq , TauMol, samplerate=1/step_molasses, units='MHz')
    
    return TimeMol
    

@stage
def optical_pump_1(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_low(t)
    AOM_MOT_cooling.go_low(t)
    shutter_MOT_cooling.go_low(t)

    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, RepumpOpPump)
    MOT_cooling.constant(t, 0)
    optical_pumping.constant(t, OpPumpAmplitude)
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 2.11*OpxShim, units='A')
    y_bias.constant(t, OpyShim, units='A')
    z_bias.constant(t, -0.8*OpzShim, units='A')
    
    # novatechdds9m_0 channel outputs:
    # Redundant: already set in previous stage (is final value of ramp). Leaving in anyway:
    MOT_lock.frequency.constant(t, ResFreq + EndFreqMol, units='MHz')
    
    return TimePrePump

    
@stage
def optical_pump_2(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    AOM_optical_pumping.go_high(t)
    
    return TimePump
    

@stage
def magnetic_trap(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_low(t)
    shutter_MOT_repump.go_low(t)
    AOM_optical_pumping.go_low(t)
    shutter_optical_pumping.go_low(t)
    AOM_probe_2.go_low(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_enable.go_high(t)
    curent_supply_3_enable.go_high(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, 0)
    optical_pumping.constant(t, 0)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_2.customramp(t, TrapTime,  HalfGaussRamp, MOTCaptureCurrent, IM, CaptureWidth, samplerate=1/step_magnetic_trap, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, TrapTime, HalfGaussRamp,  2.11*CapxShim, 2.11*0.44, CaptureWidth, samplerate=1/step_magnetic_trap, units='A')
    y_bias.customramp(t, TrapTime, HalfGaussRamp,  CapyShim, 0.42,           CaptureWidth, samplerate=1/step_magnetic_trap, units='A')
    z_bias.customramp(t, TrapTime, HalfGaussRamp, -0.8*CapzShim, -0.8*-0.04, CaptureWidth, samplerate=1/step_magnetic_trap, units='A')
    
    return TrapTime
    

@stage
def move_1(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    AOM_probe_1.go_high(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_enable.go_high(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, 0.8)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove01, Poly4Asymmetric, IPM, WidthPM, SkewPM, 1, Cf=[Cf5, AccelFrac, 0, Vel0], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.customramp(t, TimeMove01, PolyHalf2, 0, IM, WidthM, SkewM,          Cf=[Cf5, AccelFrac, 0, Vel0], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove01, Poly4,     0, IMB, WidthMB, SkewMB,       Cf=[Cf5, AccelFrac, 0, Vel0], samplerate=1/step_magnetic_transport, units='A')                               
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t,  2.11*0.44, units='A')
    y_bias.constant(t,  0.42, units='A')
    z_bias.constant(t, -0.8*-0.04, units='A')                               
    
    return TimeMove01


@stage
def move_2(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_1_select_line0.go_high(t)
    curent_supply_1_enable.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.constant(t, 0, units='A')
    transport_current_2.customramp(t, TimeMove02, PolyHalf2, 1, IM, WidthM, SkewM,       Cf=[Cf2, d1, Vel0, Vel1], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove02, Poly4,     1, IMB, WidthMB, SkewMB,    Cf=[Cf2, d1, Vel0, Vel1], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove02, PolyExp,   0, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel0, Vel1], samplerate=1/step_magnetic_transport, units='A')
    
    return TimeMove02
    
    
@stage
def move_3(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_select_line0.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove03, PolyExp, 0, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel1, Vel2], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.constant(t, 0, units='A')
    transport_current_3.customramp(t, TimeMove03, Poly4,   2, IMB, WidthMB, SkewMB,    Cf=[Cf2, d1, Vel1, Vel2], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove03, PolyExp, 1, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel1, Vel2], samplerate=1/step_magnetic_transport, units='A')

    return TimeMove03
    

@stage
def move_4(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_3_select_line0.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove04, PolyExp, 1, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel2, Vel3], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.customramp(t, TimeMove04, PolyExp, 0, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel2, Vel3], samplerate=1/step_magnetic_transport, units='A')                      
    transport_current_3.constant(t, 0, units='A')
    transport_current_4.customramp(t, TimeMove04, PolyExp, 2, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel2, Vel3], samplerate=1/step_magnetic_transport, units='A')

    return TimeMove04 
    

@stage
def move_5(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove05, PolyExp, 2, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel3, Vel4], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.customramp(t, TimeMove05, PolyExp, 1, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel3, Vel4], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove05, PolyExp, 0, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel3, Vel4], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.constant(t, 0, units='A')
    
    return TimeMove05

    
@stage
def move_6(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_1_select_line0.go_low(t)
    curent_supply_1_select_line1.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.constant(t, 0, units='A')
    transport_current_2.customramp(t, TimeMove06, PolyExp, 2, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel4, Vel5], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove06, PolyExp, 1, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel4, Vel5], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove06, PolyExp, 0, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel4, Vel5], samplerate=1/step_magnetic_transport, units='A')
    
    return TimeMove06
    

@stage
def move_7(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_select_line0.go_low(t)
    curent_supply_2_select_line1.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove07, PolyExp, 0, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel5, Vel6], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.constant(t, 0, units='A')
    transport_current_3.customramp(t, TimeMove07, PolyExp, 2, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel5, Vel6], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove07, PolyExp, 1, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel5, Vel6], samplerate=1/step_magnetic_transport, units='A')

    return TimeMove07
 

@stage
def move_8(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_3_select_line0.go_low(t)
    curent_supply_3_select_line1.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove08, PolyExp, 1, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel6, Vel7], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.customramp(t, TimeMove08, PolyExp, 0, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel6, Vel7], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.constant(t, 0, units='A')
    transport_current_4.customramp(t, TimeMove08, PolyExp, 2, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel6, Vel7], samplerate=1/step_magnetic_transport, units='A')

    return TimeMove08
     

@stage
def move_9(t):     
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_enable.go_low(t)
    
    # ni_usb_6343_1 digital outputs:
    kepco_enable_0.go_low(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.customramp(t, TimeMove09, PolyExp, 2, IB, WidthB, SkewB, ExpB, Cf=[Cf2, d1, Vel7, Vel8], samplerate=1/step_magnetic_transport, units='A')
    transport_current_2.customramp(t, TimeMove09, PolyExp, 1, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel7, Vel8], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove09, Poly4,   0, IBT, WidthBT, SkewBT,    Cf=[Cf2, d1, Vel7, Vel8], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.constant(t, -1, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, TimeMove09, LineRamp,  2.11*0.44, TpxShim,     samplerate=1/step_magnetic_transport, units='A')
    y_bias.customramp(t, TimeMove09, LineRamp,  0.42, TpyShimInitial,   samplerate=1/step_magnetic_transport, units='A')
    z_bias.customramp(t, TimeMove09, LineRamp, -0.8*-0.04, a0*TpzShim,  samplerate=1/step_magnetic_transport, units='A')
    
    return TimeMove09
    
    
@stage
def move_10(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_1_select_line1.go_low(t)
    curent_supply_1_enable.go_low(t)
    curent_supply_4_select_line0.go_high(t)
    curent_supply_4_select_line1.go_high(t)
    curent_supply_4_enable.go_high(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.constant(t, -1, units='A')
    transport_current_2.customramp(t, TimeMove10, PolyExp,   2, IL, WidthL, SkewL, ExpL, Cf=[Cf2, d1, Vel8, Vel9], samplerate=1/step_magnetic_transport, units='A')
    transport_current_3.customramp(t, TimeMove10, Poly4,     1, IBT, WidthBT, SkewBT,    Cf=[Cf2, d1, Vel8, Vel9], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove10, PolyHalf1, 0, IFT, WidthFT, SkewFT,    Cf=[Cf2, d1, Vel8, Vel9], samplerate=1/step_magnetic_transport, units='A')
    
    # ni_usb_6343_1 analog outputs:
    # These lines redundant: already set in previous stage (are final values of ramps). Leaving in anyway:
    x_bias.constant(t, TpxShim, units='A')
    y_bias.constant(t, TpyShimInitial, units='A')
    z_bias.constant(t, a0*TpzShim, units='A')
    
    return TimeMove10
    
    
@stage
def move_11(t):
    # ni_usb_6343_0 digital outputs:
    curent_supply_2_select_line1.go_low(t)
    curent_supply_2_enable.go_low(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_1.constant(t,  0, units='A')
    transport_current_2.constant(t, -1, units='A')
    transport_current_3.customramp(t, TimeMove11, Poly4,     2, IBT, WidthBT, SkewBT, Cf=[Cf2, d2, Vel9, 0], samplerate=1/step_magnetic_transport, units='A')
    transport_current_4.customramp(t, TimeMove11, PolyHalf1, 1, IFT, WidthFT, SkewFT, Cf=[Cf2, d2, Vel9, 0], samplerate=1/step_magnetic_transport, units='A')
       
    return TimeMove11    
    
    
@stage
def move_12(t):
    
    # ni_usb_6343_0 analog outputs:
    transport_current_3.constant(t, -1, units='A')
    transport_current_4.customramp(t, TimeMove12, LineRamp, IFT, TopTrapCurrent, samplerate=1/step_magnetic_transport, units='A')
    
    # ni_usb_6343_1 analog outputs:
    y_bias.customramp(t, TimeMove12, LineRamp, TpyShimInitial, TpyShimTrap, samplerate=1/step_magnetic_transport, units='A')
    #y_bias.customramp(t, TimeMove12, LineRamp, TpyShimInitial, TpyShim, samplerate=1/step_magnetic_transport, units='A')
    
    if dipole_evap:
        # ni_pci_6733_0 analog outputs:
        dipole_intensity.constant(t, DipoleInt)
        dipole_split.constant(t, DipoleSplit)
    elif not dipole_evap:
        if tube_trap:
            AOM_green_beam.customramp(t, TimeMove12, LineRamp, GreenInt1, FinalGreenInt, samplerate=1/step_magnetic_transport)
            green_beam.go_high(t)
        
    return TimeMove12
    

@stage
def evaporate(t):
    # pulseblaster_0 outputs:
    dipole_switch.go_high(t)
    
    # ni_pci_6733_1 digital outputs:
    RF_switch_0.go_high(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_3_select_line1.go_low(t)
    curent_supply_3_enable.go_low(t)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_2.constant(t, 0, units='A')
    transport_current_3.constant(t, 0, units='A')

    # ni_pci_6733_1 analog outputs:
    RF_mixer1.constant(t, 0.6000)
    
    # novatechdds9m_0 channel outputs:
    RF_evap.frequency.customramp(t, RFevapTime, LineRamp, StartRF, EndRF, samplerate=1/step_RF_evap, units='MHz')
    RF_evap.setamp(t, 1.000) #0.7077
    
    return RFevapTime
    
    
@stage
def decompress_1(t):
    # ni_usb_6343_0 analog outputs:
    transport_current_4.customramp(t, DecompTime1, LineRamp, TopTrapCurrent, MiddleCurrent, samplerate=1/step_decompress, units='A')
    
    # ni_usb_6343_1 analog outputs:
    y_bias.customramp(t, DecompTime1, LineRamp, TpyShimTrap, TpyShimTrap1, samplerate=1/step_decompress, units='A')
    
    # novatechdds9m_0 channel outputs:
    RF_evap.frequency.customramp(t, DecompTime1, LineRamp, EndRF, EndFreq, samplerate=1/step_decompress, units='MHz')
    
    return DecompTime1

    
@stage
def set_novatech_0(t):
    # novatechdds9m_0 channel outputs:
    
    MOT_lock.frequency.constant(t, ResFreq+ImageFreq2, units='MHz')
   
    
        
    RF_evap.setamp(t, 0.7077)
    
    # novatechdds9m_1 channel outputs:
    uwave1.setfreq(t, (59 + uwaveoffset), units='MHz')
    uwave1.setamp(t, uamp_ARP)
    
    return TimeSetNovatech

    
@stage
def set_novatech_2(t):
    MOT_lock.frequency.constant(t, ResFreq+ImageFreq, units='MHz')
    return TimeSetNovatech
    
@stage 
def magnetic_hold(t): 
    #transport_current_4.customramp(t, TimeMagHold, ExpRamp, MiddleCurrent, mag_gain*FinalCurrent, dipoleEvapTau, samplerate=1/step_dipole_evap, units='A')
    RF_switch_0.go_low(t)
    
    return TimeMagHold
   
@stage
def decompress_2(t):
    # ni_usb_6343_0 analog outputs:
    transport_current_4.customramp(t, DecompTime2, LineRamp, MiddleCurrent, mag_gain*FinalCurrent, samplerate=1/step_decompress, units='A')
    
    # ni_usb_6343_1 analog outputs:
    y_bias.customramp(t, DecompTime2, LineRamp, TpyShimTrap1, TpyShimTrap2, samplerate=1/step_decompress, units='A')
    
    return DecompTime2

    
@stage
def dipole_evaporation_1(t):
    
    # ni_pci_6733_1 digital outputs:
    RF_switch_0.go_low(t)
    
    # ni_pci_6733_0 analog outputs:
    dipole_intensity.customramp(t, EvapTime, ExpRamp, DipoleInt, DipoleInt2, dipoleEvapTau, samplerate=1/step_dipole_evap)
    dipole_split.customramp(t, EvapTime, ExpRamp, DipoleSplit, FinalDipoleSplit, dipoleEvapTau, samplerate=1/step_dipole_evap)
    
    # ni_pci_6733_1 analog outputs:
    RF_mixer1.constant(t, 0)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_4.customramp(t, EvapTime, ExpRamp, mag_gain*FinalCurrent, 0, dipoleEvapTau, samplerate=1/step_dipole_evap, units='A')
    
    # ni_usb_6343_1 analog outputs:
    y_bias.customramp(t, EvapTime, LineRamp, TpyShimTrap2, TpyShimTrap3, samplerate=1/step_dipole_evap, units='A')
    
    return EvapTime
   
@stage
def ramp_Bfield_0(t):
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 250*ms, LineRamp, TpxShim, TpxShimStart, samplerate=1/step_ramp_Bfield, units='A')
    y_bias.customramp(t, 250*ms, LineRamp, TpyShimTrap3, TpyShimStart, samplerate=1/step_ramp_Bfield, units='A')
    z_bias.customramp(t, 250*ms, LineRamp, a0*TpzShim, a0*TpzShimStart, samplerate=1/step_ramp_Bfield, units='A')
    offset.customramp(t, 250*ms, LineRamp, 0, Offset + dTpzShim, samplerate=1/step_ramp_Bfield)

    # ni_pci_6733_0 digital outputs:
    grad_cancel_switch.go_high(t)
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_select_line1.go_low(t)
    curent_supply_4_enable.go_low(t)
    shutter_top_repump.go_low(t)
    return 250*ms
    
    
@stage
def ramp_uwave(t): 
    # ni_pci_6733_1 analog outputs:
    microwave_attenuator.customramp(t, 30*ms, LineRamp, 6.0, 0.0, samplerate=1/step_ramp_uwave)
    uwave_mixer1.customramp(t, 30*ms, LineRamp, 0.0, u_w_mixer, samplerate=1/step_ramp_uwave)
    
    # ni_pci_6733_1 digital outputs:
    uWave_switch_0.go_high(t)
   
    return 30*ms
    
@stage
def uwave_pulse(t):
    microwave_attenuator.constant(t, 0.0)
    uwave_mixer1.constant(t, u_w_mixer)
    
    # ni_pci_6733_1 digital outputs:
    uWave_switch_0.go_high(t)
    
    return time_microwave_pulse
    
@stage
def uwave_pulse_off(t):
    microwave_attenuator.constant(t,6.0)
    uwave_mixer1.constant(t,0.0)
    uWave_switch_0.go_low(t)
    
    return 2*ms
@stage
def ARP_uwave(t):
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 10*ms, LineRamp, TpxShimStart, TpxShimEnd, samplerate=1/step_ramp_uwave, units='A')
    y_bias.customramp(t, 10*ms, LineRamp, TpyShimStart, TpyShimEnd, samplerate=1/step_ramp_uwave, units='A')
    z_bias.customramp(t, 10*ms, LineRamp, a0*TpzShimStart, a0*TpzShimEnd, samplerate=1/step_ramp_uwave, units='A')
    
    return 10*ms

    
@stage
def uwave_off(t):
    # ni_pci_6733_1 analog outputs:
    microwave_attenuator.customramp(t, 15*ms, LineRamp, 0.0, 6.0, samplerate=1/step_ramp_uwave)
    uwave_mixer1.customramp(t, 15*ms, LineRamp, u_w_mixer, 0.0, samplerate = 1/step_ramp_uwave)
    
    return 15*ms

    
@stage
def prep_blast_2_2(t):
    # pulseblaster_0 digital outputs:
    shutter_x.go_high(t)
    # ni_pci_6733_0 analog outputs:
    probe_1.constant(t, 0)
    
    # ni_pci_6733_1 digital outputs:
    uWave_switch_0.go_low(t)
    
    return 4*ms
    
    
@stage
def blast_2_2(t):
    # pulseblaster_0 digital outputs:
    shutter_x.go_low(t+3*ms)
    # ni_pci_6733_0 analog outputs:
    probe_1.constant(t, 0.1)   

    return 7*ms
    
@stage
def dipole_evaporation_2(t):
    
    # ni_pci_6733_0 analog outputs:
    dipole_intensity.customramp(t, EvapTime_2, ExpRamp, DipoleInt2, DipoleInt3, dipoleEvapTau2, samplerate=1/step_dipole_evap)
    dipole_split.constant(t, FinalDipoleSplit)
    probe_1.constant(t, 0) 
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_select_line1.go_low(t)
    curent_supply_4_enable.go_low(t)
    
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 100*ms, LineRamp, TpxShimEnd, TpxShimStart, samplerate=1/step_ramp_Bfield, units='A')
    y_bias.customramp(t, 100*ms, LineRamp, TpyShimEnd, TpyShimStart, samplerate=1/step_ramp_Bfield, units='A')
    z_bias.customramp(t, 100*ms, LineRamp, a0*TpzShimEnd, a0*TpzShimARP, samplerate=1/step_ramp_Bfield, units='A')
    offset.constant(t, (Offset + dTpzShim))

    
    return EvapTime_2

@stage 
def set_novatech_1(t):
    # novatechdds9m_1 channel outputs:
    RF_evap.setfreq(t, ARPFreq6, units='MHz')
    RF_evap.setamp(t, 1.0) # 3 dBm

    return TimeSetNovatech

    
@stage
def ramp_Bfield_1(t):
    # ni_usb_6343_1 analog outputs:
    if not uwave_transfer:
        x_bias.customramp(t, 250*ms, LineRamp, TpxShim, TpxShimStart, samplerate=1/step_ramp_Bfield, units='A')
        y_bias.customramp(t, 250*ms, LineRamp, TpyShimTrap3, TpyShimStart, samplerate=1/step_ramp_Bfield, units='A')
        z_bias.customramp(t, 250*ms, LineRamp, a0*TpzShim, a0*TpzShimStart, samplerate=1/step_ramp_Bfield, units='A')
    else:    
        offset.customramp(t, 100*ms, LineRamp, Offset + dTpzShim, Offset+dTpzShim+1, samplerate = 1/step_ramp_Bfield)

    return 100*ms
   
   
@stage
def ramp_RF(t):
    # ni_pci_6733_1 analog outputs:
    RF_mixer1.customramp(t, 15*ms, LineRamp, 0, rf_mixer, samplerate = 1/step_ramp_RF)
   
    # ni_pci_6733_1 digital outputs:
    RF_switch_0.go_high(t)

    return 15*ms

    
@stage
def ARP_RF(t):
    # ni_usb_6343_1 analog outputs:
    offset.customramp(t, 100*ms, LineRamp, Offset+dTpzShim+1, Offset+dTpzShim, samplerate = 1/step_ramp_RF)

    return 10*ms

    
@stage 
def RF_off(t):
    # ni_pci_6733_1 analog outputs:
    RF_mixer1.customramp(t, 15*ms, LineRamp, rf_mixer, 0, samplerate = 1/step_ramp_RF)
    
    return 15*ms
   
@stage
def dipole_evaporation_3(t):
    # ni_pci_6733_0 analog outputs:
    dipole_intensity.customramp(t, EvapTime_3, ExpRamp, DipoleInt3, FinalDipoleInSitu, dipoleEvapTau2, samplerate=1/step_dipole_evap)
    
    return EvapTime_3    
    
@stage
def tube_trap_on(t):
    # ni_usb_6343_2 analog outputs:
    AOM_green_beam.customramp(t, TimeTube, LineRamp, GreenInt1, FinalGreenInt, samplerate=1/step_green_hold) 
    green_beam.go_high(t)
    
    return TimeTube

@stage
def magnetic_blow(t):
    # GRADIENT PUSH 
    
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 1e-3, LineRamp, TpxShim, TpxShimOffset, samplerate=1/step_TOF, units='A')
    y_bias.customramp(t, 1e-3, LineRamp, TpyShim, TpyShimOffset,  samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 analog outputs:
    transport_current_4.customramp(t, TimeHold, LineRamp, 0, gradient_current, samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_high(t)
    curent_supply_4_select_line1.go_high(t)
    curent_supply_4_enable.go_high(t)
    
    return TimeHold
    
@stage
def tube_trap_toggle(t):
    # ni_usb_6343_2 digital outputs:
    #green_servo_trigger.go_high(t)
    #green_servo_trigger.go_low(t+TimeToggle)
    
    #AOM_green_beam.constant(t+4e-6, 0.3)
    #AOM_green_beam.constant(t+4e-6+TimeToggle, FinalGreenInt)
    
    green_beam.go_low(t+4e-6)
    green_beam.go_high(t+4e-6+TimeToggle)

    return TimeToggle

@stage
def tube_trap_heat(t):
    # ni_usb_6343_2 analog outputs:
    AOM_green_beam.customramp(t, 0.10, SinRamp, GreenInt2, 0.025, freq_heat, 0.0, samplerate=1/step_green_hold)
    
    return 0.10
@stage
def dipole_hold_insitu(t):
    #ni_pci_6733_0 analog outputs:
    if tube_trap:
        dipole_intensity.customramp(t, TimeDipoleUnload, LineRamp, FinalDipoleInSitu, FinalDipoleWeak, samplerate=1/step_hold)
        dipole_split.customramp(t, TimeDipoleUnload, LineRamp, FinalDipoleSplit, 1.0, samplerate=1/step_hold)
    else:
        dipole_intensity.customramp(t, TimeDipoleUnload, LineRamp, FinalDipoleInSitu, FinalDipoleRelease, samplerate=1/step_hold)
        dipole_split.customramp(t, TimeDipoleUnload, LineRamp, FinalDipoleSplit, 1.0, samplerate=1/step_hold)
    
    return TimeDipoleUnload

@stage
def tube_trap_on_2(t):
    # ni_usb_6343_2 analog outputs:
    AOM_green_beam.customramp(t, 0.1*TimeTube, LineRamp, FinalGreenInt, GreenInt2, samplerate=1/step_tube) 
    
    return 0.1*TimeTube
    
@stage
def tube_trap_on_3(t):
    # ni_usb_6343_2 analog outputs:
    AOM_green_beam.customramp(t, 0.1*TimeTube, LineRamp, GreenInt2, FinalGreenInt, samplerate=1/step_tube) 
    
    return 0.1*TimeTube
    
@stage
def apply_gradient(t):
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 1e-3, LineRamp, TpxShim, TpxShimOffset, samplerate=1/step_TOF, units='A')
    y_bias.customramp(t, 1e-3, LineRamp, TpyShim, TpyShimOffset,  samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 analog outputs:
    transport_current_4.customramp(t, TimeDipoleHold, LineRamp, 0, gradient_current, samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_high(t)
    curent_supply_4_select_line1.go_high(t)
    curent_supply_4_enable.go_high(t)
    
    return TimeDipoleHold

@stage
def snap_gradient(t):
    # ni_usb_6343_1 analog outputs:
    #x_bias.customramp(t+1e-3, 1e-3, LineRamp, TpxShimOffset, TpxShim, samplerate=1/step_TOF, units='A')
    #y_bias.customramp(t+1e-3, 1e-3, LineRamp, TpyShimOffset, TpyShim, samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 analog outputs:
    transport_current_4.constant(t, 0, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_select_line1.go_low(t)
    curent_supply_4_enable.go_low(t)
    
    return 100e-6
    
@stage
def dipole_release(t):
    # pulseblaster_0 outputs:
    dipole_switch.go_low(t)  
    
    #ni_pci_6733_0 digital outputs:    
    #dipole_shutter.go_low(t - 20e-3)

    return time_wait
    
@stage
def dipole_release_1(t):
    dipole_intensity.customramp(t, TimeDipoleUnload, LineRamp, 0.0, FinalDipoleInSitu, samplerate=1/step_hold)

    return TimeDipoleUnload
    
@stage
def tube_off(t):
    #ni_usb_6733_2 analog outputs:
    AOM_green_beam.customramp(t+TimeInSituOpenShutter+1*ms, 2*ms, LineRamp, FinalGreenInt, GreenInt1, samplerate=1/step_tube)
    
    #ni_usb_6733_2 digital outputs:
    green_beam.go_low(t+TimeInSituOpenShutter)
    green_servo_trigger.go_high(t+TimeInSituOpenShutter)
    
    return time_wait
 
@stage
def grad_off(t):
    # GRADIENT OFF 
    
    # ni_usb_6343_0 analog outputs:
    transport_current_4.constant(t, 0, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_select_line1.go_low(t)
    curent_supply_4_enable.go_low(t)
    
    return 2e-3
 
@stage
def insitu_open_shutter(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_low(t)           #AOM_probe_1 if along XY
    shutter_x.go_high(t)        #shutter_x if along XY
    #shutter_z.go_high(t)
    #shutter_top_repump.go_high(t)
    
    #dipole_switch.go_low(t+1*TimeInSituOpenShutter)  
    #dipole_shutter.go_low(t+1*TimeInSituOpenShutter)
        
    if dipole_evap == False:
        transport_current_4.constant(t+1*TimeInSituOpenShutter, 0, units='A')
    
    return TimeInSituOpenShutter

 
@stage
def insitu_cam_trigger_1(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_low(t)
    #AOM_MOT_repump.go_high(t)

    # ni_pci_6733_0 outputs:
    probe_1.constant(t, ProbeInt2)     #probe_1 if along XY

    # ni_pci_6733_0 outputs:
    #MOT_repump.constant(t, 0.8)
    
    return 2e-5
    
@stage
def insitu_image_1(t):
    # pulseblaster_0 outputs: 
    AOM_probe_1.go_high(t)            #AOM_probe_1 if along XY
    XY_2_Flea3.expose('shot1', t-30e-6, 'probe')
    #XY_1_Flea3.expose('shot1', t-30e-6, 'atoms')
    #YZ_1_Flea3.expose('shot1', t-30e-6, 'atoms')
    return TimeImage
 
    
@stage  
def download_insitu_image_1(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_high(t)
    AOM_probe_1.go_low(t)             #AOM_probe_1 if along XY
    #AOM_MOT_repump.go_low(t)
    
    # ni_pci_6733_0 outputs:
    #MOT_repump.constant(t, 0.8)
    probe_1.constant(t, 0)            #probe_1 if along XY
    
    return TimeDownloadImage
    

@stage
def blast_insitu_cloud(t):
   
    # ni_pci_6733_0 outputs:
    #probe_1.constant(t, ProbeInt2*0)   #probe_1 if along XY
    
    # ni_usb_6343_0 digital outputs:
    #curent_supply_4_select_line0.go_low(t)
    #curent_supply_4_select_line1.go_low(t)
    #curent_supply_4_enable.go_low(t)
    
    # ni_pci_6733_0 analog outputs:
    #dipole_intensity.constant(t, 0)
    #transport_current_4.constant(t, 0, units='A')
    
    return 0*ms
    
@stage
def wait(t):
    # ni_pci_6733_0 outputs:
    probe_1.constant(t, 0) #probe_1 if along XY
    
    return 0*ms
    
@stage  
def insitu_cam_trigger_2(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_low(t)
    #AOM_MOT_repump.go_high(t)
    #shutter_top_repump.go_high(t)
    
    # ni_pci_6733_0 outputs:
    probe_1.constant(t, ProbeInt2) #probe_1 if along XY
    #MOT_repump.constant(t, 0.2)
    transport_current_4.constant(t, 0, units='A')
    return 2e-5
    
@stage
def insitu_image_2(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_high(t)     #AOM_probe_1 if along XY
    XY_2_Flea3.expose('shot2', t-30e-6, 'atom_red')
    #XY_1_Flea3.expose('shot2', t-30e-6, 'probe')
    #YZ_1_Flea3.expose('shot2', t-30e-6, 'probe')
    return TimeImage
    
@stage  
def download_insitu_image_2(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_high(t)
    AOM_probe_1.go_low(t)      #AOM_probe_1 if along XY
    shutter_x.go_low(t) #shutter_x if along XY
    #shutter_z.go_low(t)
    #AOM_MOT_repump.go_low(t)
    #shutter_top_repump.go_low(t)

    # ni_pci_6733_0 outputs:
    #MOT_repump.constant(t, 0)
    probe_1.constant(t, 0)     #probe_1 if along XY
    
    return TimeDownloadImage

    
    
def insitu_cam_trigger_3(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_low(t)
    #AOM_MOT_repump.go_high(t)
    #shutter_top_repump.go_high(t)
    
    # ni_pci_6733_0 outputs:
    probe_1.constant(t, ProbeInt2) #probe_1 if along XY
    #MOT_repump.constant(t, 0.2)
    transport_current_4.constant(t, 0, units='A')
    return 2e-5
    
@stage
def insitu_image_3(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_high(t)     #AOM_probe_1 if along XY
    XY_2_Flea3.expose('shot3', t-30e-6, 'atom_blue')
    #XY_1_Flea3.expose('shot2', t-30e-6, 'probe')
    #YZ_1_Flea3.expose('shot2', t-30e-6, 'probe')
    return TimeImage
    
@stage  
def download_insitu_image_3(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_high(t)
    AOM_probe_1.go_low(t)      #AOM_probe_1 if along XY
    shutter_x.go_low(t) #shutter_x if along XY
    #shutter_z.go_low(t)
    #AOM_MOT_repump.go_low(t)
    #shutter_top_repump.go_low(t)

    # ni_pci_6733_0 outputs:
    #MOT_repump.constant(t, 0)
    probe_1.constant(t, 0)     #probe_1 if along XY
    
    return TimeDownloadImage
@stage
def insitu_cam_trigger_4(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_low(t)
    
    # ni_pci_6733_0 outputs:
    probe_1.constant(t, 0)     #probe_1 if along XY
    
    return 2e-5
    
@stage
def insitu_image_4(t):
    # pulseblaster_0 outputs:
    XY_2_Flea3.expose('shot4', t-30e-6, 'dark')
    #XY_1_Flea3.expose('shot3', t-30e-6, 'dark')
    #YZ_1_Flea3.expose('shot3', t-30e-6, 'dark')
    return TimeImage
    
@stage  
def download_insitu_image_4(t):
    # pulseblaster_0 outputs:
    #camera_trigger_0.go_high(t)
    AOM_probe_1.go_low(t)       #AOM_probe_1 if along XY
    shutter_x.go_low(t)  #shutter_x if along XY
    
    return TimeDownloadImage

    
@stage
def uwave_pulse_rdetune(t):
    z_bias.customramp(t, 50*ms, LineRamp, a0*TpzShimARP, a0*TpzShimRed, samplerate=1/step_ramp_Bfield, units='A')
    
    return 50*ms
    
def uwave_pulse_bdetune(t):
    z_bias.customramp(t, 100*ms, LineRamp, a0*TpzShimRed, a0*TpzShimBlue, samplerate=1/step_ramp_Bfield, units='A')
    
    return 100*ms
@stage
def free_TOF(t):
    # pulseblaster_0 outputs:
    dipole_switch.go_low(t)
    
    # ni_pci_6733_0 analog outputs
    dipole_intensity.constant(t, 0)
    dipole_split.constant(t, 1.0)
    probe_1.constant(t, ProbeInt)
    
    return 7e-3
    
@stage
def gradient_on(t):
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 1e-3, LineRamp, TpxShim, TpxShimOffset, samplerate=1/step_TOF, units='A')
    y_bias.customramp(t, 1e-3, LineRamp, TpyShim, TpyShimOffset, samplerate=1/step_TOF, units='A')

    return  2e-3

@stage
def stern_gerlach(t):
    # ni_usb_6343_0 analog outputs:
    transport_current_4.constant(t, SGCurrent, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_high(t)
    curent_supply_4_select_line1.go_high(t)
    curent_supply_4_enable.go_high(t)
    
    return 5e-3
    
@stage
def TOF(t):
    # pulseblaster_0 outputs:
    probe_1.constant(t, ProbeInt)
    
    # ni_usb_6343_1 analog outputs:
    x_bias.customramp(t, 1e-3, LineRamp, TpxShimOffset,  TpxShim, samplerate=1/step_TOF, units='A')
    y_bias.customramp(t, 1e-3, LineRamp, TpyShimOffset,  TpyShim, samplerate=1/step_TOF, units='A')
    z_bias.customramp(t, 1e-3, LineRamp, a0*TpzShim, a0*TpzShimImg, samplerate=1/step_TOF, units='A')
    
    # ni_usb_6343_0 analog outputs:  
    transport_current_4.constant(t, 0, units='A')
    
    # ni_usb_6343_0 digital outputs:
    curent_supply_4_select_line0.go_low(t)
    curent_supply_4_select_line1.go_low(t)
    curent_supply_4_enable.go_low(t)
    
    return 1e-3
    
@stage 
def TOF2(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_low(t)
    
    # ni_pci_6733_0 outputs:   
    probe_1.constant(t, 0)
    MOT_repump.constant(t, 0)
    
    return 5.5e-3

@stage
def TOF_open_shutter(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_low(t)
    shutter_z.go_high(t)
    #shutter_x.go_high(t)
    shutter_top_repump.go_high(t)
    
    return 3.7*ms
    
    
@stage    
def repump_1(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    #camera_trigger_1.go_low(t)
    
    # ni_pci_6733_0 outputs:
    MOT_repump.constant(t, 0.8)
    probe_1.constant(t, ProbeInt)
    
    return TimeRepumpPulse
    

@stage    
def image_1(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_high(t)
    XY_1_Flea3.expose('shot1', t-30e-6, 'atoms')
    #XY_2_Flea3.expose('shot1', t-30e-6, 'atoms')
    
    return TimeImage
    
@stage  
def download_image_1(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_low(t)
    #camera_trigger_1.go_high(t)
    AOM_probe_1.go_low(t)
    
    # ni_pci_6733_0 outputs:
    MOT_repump.constant(t, 0)
    probe_1.constant(t, 0)
    
    return TimeDownloadImage
    

@stage    
def repump_2(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    #camera_trigger_1.go_low(t)

    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, 0.8)

    probe_1.constant(t, ProbeInt)
    
    return TimeRepumpPulse
    

@stage    
def image_2(t):
    # pulseblaster_0 outputs:
    AOM_probe_1.go_high(t)
    XY_1_Flea3.expose('shot2', t-30e-6, 'probe')    
    #XY_2_Flea3.expose('shot2', t-30e-6, 'probe')
    return TimeImage
    

@stage  
def download_image_2(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_low(t)
    #camera_trigger_1.go_high(t)
    AOM_probe_1.go_low(t)
    shutter_z.go_low(t)
    #shutter_x.go_low(t)
    shutter_top_repump.go_low(t)
    
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t, 0)
    probe_1.constant(t, 0)
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 0, units='A')
    y_bias.constant(t, 0, units='A')
    z_bias.constant(t, 0, units='A')
    
    return TimeDownloadImage
    

@stage    
def repump_3(t):
    # pulseblaster_0 outputs:
    AOM_MOT_repump.go_high(t)
    #camera_trigger_1.go_low(t)
    #dipole_switch.go_high(t)

    return TimeRepumpPulse
    

@stage    
def image_3(t):
    # Is a dark image, no light pulse:
    XY_1_Flea3.expose('shot3', t-30e-6, 'dark')
    #XY_2_Flea3.expose('shot3', t-30e-6, 'dark')
    return TimeImage
    
   
@stage  
def download_image_3(t):
    # pulseblaster_0 outputs:
    
    #camera_trigger_1.go_high(t)
    AOM_MOT_cooling.go_high(t)
    AOM_probe_1.go_high(t)
    dipole_switch.go_low(t)
    
    return TimeDownloadImage

def PostProcess(h5file, **kwargs):
    import numpy as np
    from common.OD_handler import ODShot
    
    image_group = {}
    sigma0 = 3*(780e-9)**2/(2*3.14)
        # Safe to assume uwave lock is *only* along z-insitu
    if  '/data/imagesXY_2_Flea3' in h5file:
        image_group['imagesXY_2_Flea3'] = 'z-insitu'
        Isat = 395      # In counts // Paco:04/20/2016
        alpha= 1 #4.3
    atoms1, atoms2, probe, bckg, div1, div2, OD1, OD2 = [], [], [], [], [] ,[], [], []
    # Check if data is present
    if len(h5file['data']['imagesXY_2_Flea3']['Raw'][:]) != 0:
        probe= (np.array(h5file['data']['imagesXY_2_Flea3']['Raw'])[0])
        atoms1 = (np.array(h5file['data']['imagesXY_2_Flea3']['Raw'])[1])
        atoms2 = (np.array(h5file['data']['imagesXY_2_Flea3']['Raw'])[2])
        bckg =  (np.array(h5file['data']['imagesXY_2_Flea3']['Raw'])[3])
        div1 = np.ma.masked_less_equal(np.ma.masked_invalid((atoms1 - bckg)/(probe-bckg)), 0.)
        div2 = np.ma.masked_less_equal(np.ma.masked_invalid((atoms2 - bckg)/(probe-bckg)), 0.)
        another_term1, another_term2 = (probe-atoms1)/(Isat),  (probe-atoms2)/(Isat)
        OD1, OD2 = (np.matrix(-alpha*np.log(div1)+0*another_term1), 
                    np.matrix(-alpha*np.log(div2)+0*another_term2))
    # Get OD
        ODa, ODb = ODShot(OD1), ODShot(OD2)
        Fa, mFa, _ROIa_, BCKa_a =  ODa.get_ROI(sniff=False, get_background=False) 
        Fb, mFb, _ROIb_, BCKb_a =  ODb.get_ROI(sniff=False, get_background=False) 
        BCKa, BCKb = (np.mean(BCKa_a)*np.ones(_ROIa_.shape), 
                      np.mean(BCKb_a)*np.ones(_ROIb_.shape))
        # Compute number imbalance
        Na, Nb = (np.sum((_ROIa_-BCKa)/sigma0)*pixel_size**2), 
                 (np.sum((_ROIb_-BCKb)/sigma0)*pixel_size**2)
        N_imb = (Na-Nb)/(Na+Nb)
    offset_updt = float(h5file['globals/dipole_evaporate'].attr['Offset']) - 0.0005*N_imb
    return {'Offset':offset_updt}
    
    
@stage
def off(t):  
    # ni_pci_6733_0 analog outputs:
    MOT_repump.constant(t,  UVMOTRepump)
    MOT_cooling.constant(t, UVMOTAmplitude)
    probe_1.constant(t,     ProbeInt)
    
    # ni_usb_6343_0 analog outputs:
    transport_current_2.constant(t, UVMOTCurrent, units='A')
    
    # ni_usb_6343_1 analog outputs:
    x_bias.constant(t, 2.11*UVxShim, units='A')
    y_bias.constant(t,      UVyShim, units='A')
    z_bias.constant(t, -0.8*UVzShim, units='A')
    
    # ni_pci_6733_0 analog outputs:
    dipole_intensity.constant(t, DipoleInt)
    dipole_split.constant(t, DipoleSplit)
    
    # novatechdds9m_0 channel outputs:
    MOT_lock.setfreq(t,  (ResFreq + UVMOTFreq)*MHz)
    RF_evap.setfreq(t,  30*MHz)
    
    # ni_usb_6343 outputs:
    green_beam.go_low(t)
    green_servo_trigger.go_low(t+5*ms)
    shutter_greenbeam.go_low(t)
    AOM_green_beam.constant(t, -0.5)
    fluxgate_trig.go_low(t)
    
    return 0.03
    
    
start()
t = 0
t += prep(t)
t += UVMOT(t)
t += cMOT(t)
t += molasses(t)
t += optical_pump_1(t)
t += optical_pump_2(t)
t += magnetic_trap(t)
t += move_1(t)
t += move_2(t)
t += move_3(t)
t += move_4(t)
t += move_5(t)
t += move_6(t)
t += move_7(t)
t += move_8(t)
t += move_9(t)
t += move_10(t)
t += move_11(t)
t += move_12(t)
t += evaporate(t)
t += decompress_1(t)
t += set_novatech_0(t)
 

 
 
t += decompress_2(t)
t += dipole_evaporation_1(t)

#ARP
if uwave_transfer:
    t += ramp_Bfield_0(t)
    t += ramp_uwave(t)
    t += ARP_uwave(t)
    t += uwave_off(t)
    t += prep_blast_2_2(t)
    t += blast_2_2(t)
t += dipole_evaporation_2(t)
t += dipole_evaporation_3(t)


#probe shot
t += insitu_open_shutter(t)
t += insitu_cam_trigger_1(t)
t += insitu_image_1(t)
t += download_insitu_image_1(t)


#ramp field red
t += uwave_pulse_rdetune(t)

#red_detuned uwave pulse
if uwave_transfer:
    t += uwave_pulse(t)
    t += uwave_pulse_off(t)     
    
#red detuned atom shot
t += insitu_open_shutter(t)
t += insitu_cam_trigger_2(t)
t += insitu_image_2(t)
t += download_insitu_image_2(t)

#ramp field blue
t += uwave_pulse_bdetune(t)

#red_detuned uwave pulse
if uwave_transfer:
    t += uwave_pulse(t)
    t += uwave_pulse_off(t)    
   
#blue detuned atom shot
t += insitu_open_shutter(t)
t += insitu_cam_trigger_3(t)
t += insitu_image_3(t)
t += download_insitu_image_3(t) 

#dark shot

t += insitu_image_4(t)
t += download_insitu_image_4(t)





#t += insitu_open_shutter(t)
#t += insitu_cam_trigger_1(t)
#t += insitu_image_1(t)
#t += download_insitu_image_1(t)

#t += insitu_cam_trigger_2(t)
#t += insitu_image_2(t)
#t += download_insitu_image_2(t)
#t += insitu_cam_trigger_3(t)
#t += insitu_image_3(t)
#t += download_insitu_image_3(t)


t += set_novatech_2(t)
t += free_TOF(t)
t += gradient_on(t)
t += stern_gerlach(t)
t += TOF(t)
t += TOF2(t)
t += TOF_open_shutter(t)
t += repump_1(t)
t += image_1(t)
t += download_image_1(t)
t += repump_2(t)
t += image_2(t)
t += download_image_2(t)
t += repump_3(t)
t += image_3(t)
t += download_image_3(t)
    


    
t += off(t)
t += cooldown_time
postprocess(PostProcess)
stop(t, min_time = t + 0.0)

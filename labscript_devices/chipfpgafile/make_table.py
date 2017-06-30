import numpy as np 
import visa
import time
table = np.multiply(np.ones((3,110),dtype = int),20)
# table[1,:] = range(110)
# table[2,0:9] = range(9)
# table[2,10:19] = range(4,13,1)  

np.save('C://software/table.npy',table)

# rm = visa.ResourceManager()
# chipfpga_usb = rm.open_resource("ASRL4::INSTR")

# load_list = table.reshape((1,-1))
# uni_load_list = map(unichr,load_list[0,:])

# for i in range(550):
#     chipfpga_usb.write_raw(uni_load_list[i])
#     time.sleep(0.001)



# list = []
# read_str = ''
# while True:
#     readdata = chipfpga_usb.visalib.read(chipfpga_usb.session, chipfpga_usb.bytes_in_buffer)
#     if readdata[0] == '':
#         break
#     else:
#         read_str = read_str + readdata[0]

# list = map(ord,read_str)
# chipfpga_usb.close()

# print read_str

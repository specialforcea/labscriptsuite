import numpy as np 
import visa
import time
#table = np.multiply(np.ones((3,110),dtype = int),20)

#map list
map_list = [1 ,8,3, 4,	5, 12, 7, 2, 9,	10,	11,	6,13,20,15,	16, 17,	24,	19,	14,	21,	22,	23,	18, 
25,	32,	27,	28,	29,	36,	31,	26, 33,	34,	35,	30,	37,	44,39,40, 41,48,43,	38,	45,	46,	47,	42,
49,	56,	51,	52,	53,	60,	55,	50, 57,	58,	59,	54,	61,	68,	63,	64, 65,	72,	67,	62,	69,	70,	71,	66,
73,	80,	75,	76,	77,	84,	79,	74, 81,	82,	83,	78,	85,	92,	87,	88]

n = 5 #group number

def set_group(n):
	table = np.zeros((n,110),dtype = int)
	return table

table = set_group(n)

N = np.zeros((n),dtype = int)
M = np.zeros((n),dtype = int)
C = np.zeros((n,6),dtype = int)
sft = np.zeros((n,6),dtype = int)
nmbr = np.zeros((n,96),dtype = int)

def set_N(N,table,n):
	for i in range(n):
		table[i,0] = N[i]

	return table


def set_M(M,table,n):
	for i in range(n):
		table[i,1] = M[i]

	return table


def set_C(C,table,n):
	for i in range(n):
		table[i,2:7] = C[i]
	return table

def set_sft(sft,table,n):
	for i in range(n):
		table[i,8:13] = sft[i]
	return table

def set_nmbr(nmbr,table,n):
	for i in range(n):
		table[i,14:109] = nmbr[i]
	return table













np.save('C://software/table.npy',table)






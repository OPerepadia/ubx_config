#!/usr/bin/env python

import sys
import argparse
import serial

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument('--port', required = True, help='Serial port')
parser.add_argument('--baud', required = False, nargs='?', const = 1,
                    type = int, default = 115200, help='Baud rate')
parser.add_argument('--file', required = True, help='Path to config file')
args = parser.parse_args()

MAX_RETRIES = 10
TIMEOUT_S = 0.2
PORT = args.port
BAUD = args.baud
CFG_FILE = args.file

SYNC1 = 0xB5
SYNC2 = 0x62
UBX_ACK_ACK = bytearray ([ 0xb5, 0x62, 0x05, 0x01 ])
UBX_COMMAND_MON_VER = bytearray ([ 0xB5, 0x62, 0x0A, 0x04, 0x00, 0x00, 0x0E, 0x34 ])
UBX_COMMAND_CFG_SAVE = bytearray ([ 0xB5, 0x62, 0x06, 0x09, 0x0D, 0x00, 0x00, 0x00,
                                    0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
                                    0x00, 0x00, 0x17, 0x31, 0xBF ])

# Checksum calculation code from https://gist.github.com/tomazas/3ab51f91cdc418f5704d#file-ubx_checksum-py
def calc_checksum (packet):
    CK_A,CK_B = 0, 0
    for i in range(len(packet)):
        CK_A = CK_A + packet[i]
        CK_B = CK_B + CK_A
    # ensure unsigned byte range
    CK_A = CK_A & 0xFF
    CK_B = CK_B & 0xFF
    return CK_A,CK_B

class colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    END = '\033[0m'

# Open serial port
ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT_S)

# Read configuration file
print ("Reading configuration from {}".format(CFG_FILE))
try:
    cfgFile = open (CFG_FILE)
except FileNotFoundError:
    print ("Error: config file not found")
    sys.exit()
cfgLines = cfgFile.readlines()

cfgErrorCount = 0
lineCnt = 0
for line in cfgLines:
    lineCnt += 1
    if "MON-VER" in line:
        # Read MON-VER from config file
        bytes_object = bytes.fromhex(line[len("MON-VER - "):])
        configVersion = bytes_object[4:44].decode("ASCII")
        print ("Firmware version of the config file: {}".format(configVersion))

        print ("[{}/{}] Checking firmware version...".format(lineCnt, len(cfgLines)), end = " ")
        sys.stdout.flush()
        
        versionCheckOK = False
        retries = 0
        while retries < MAX_RETRIES:
            ser.flushInput()
            ser.write(UBX_COMMAND_MON_VER)  # Poll MON-VER
            answer = ser.read(200)
            # print ("Read {} bytes from receiver".format(len(answer)))
            if len(answer) != 0 and answer[2] == 0x0A and answer[3] == 0x04:
                receiverVersion = answer[6:46].decode("ASCII")
                if receiverVersion == configVersion:
                    versionCheckOK = True
                    break
            else:
                print ("invalid response")
            retries += 1
        
        if versionCheckOK == True:
            print(colors.GREEN + "OK" + colors.END)
        else:
            print(colors.RED + "Firmware version check failed" + colors.END)
            sys.exit()

    elif "CFG-VALGET" in line:
        command_string = line[len("CFG-VALGET - "):].replace(" ", "")
        data = bytearray.fromhex(command_string)
        data[1] = 0x8A    # convert VALGET into VALSET
        data[5] = 0x01    # set configuration in the RAM layer
        
        CK_A, CK_B = calc_checksum(data)
        
        message = bytearray([SYNC1, SYNC2]) + data + bytearray([CK_A, CK_B])
        
        print ("[{}/{}] Writing configuration...".format(lineCnt, len(cfgLines)), end = " ")
        sys.stdout.flush()

        setConfigOK = False
        retries = 0
        while retries < MAX_RETRIES:
            ser.flushInput()
            ser.write(message)
            answer = ser.read(200)
            if UBX_ACK_ACK.hex() in answer.hex():
                setConfigOK = True
                break
            retries += 1
        
        if setConfigOK:
            print(colors.GREEN + "ACK" + colors.END)
        else:
            print (colors.RED + "NACK" + colors.END)
            cfgErrorCount += 1

retries = 0
saveCfgOK = False
print ("Saving configuration to flash...", end = " ")
while retries < MAX_RETRIES:
    ser.flushInput()
    ser.write(UBX_COMMAND_CFG_SAVE)
    answer = ser.read(200)
    if UBX_ACK_ACK.hex() in answer.hex():
        saveCfgOK = True
        break
    retries += 1

if saveCfgOK:
    print(colors.GREEN + "ACK" + colors.END)
else:
    print (colors.RED + "NACK" + colors.END)
    cfgErrorCount += 1

ser.close()

if cfgErrorCount == 0:
    print ("Done")
else:
    print ("Configuration finished with errors")

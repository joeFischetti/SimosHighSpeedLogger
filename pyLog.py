#!/usr/bin/env python3


#import datetime so we can put something in the CSV
from datetime import datetime

#yaml is used to define the logged parameters, bytes is for byte stuff, and
#  threading is so we can handle multiple threads (start the reader thread)
#  time is used so I could put pauses in various places
import yaml, bytes, threading, time


#Gain level 3 security access to the ECU
def gainLevel3(obd):
    #Print a debug message
    print("Level 3 security")

    #Tell the ECU we want to gain level 3 access
    #  The response will include the challenge seed
    response = obd.sendRawCommand("27 03")

    #Print the seed for debugging purposes
    print("response")

    #static resopnse used for testing
    #response = "01 02 1B 57 2C 42"
    
    #the private key is used as a sum against the seed (for ED)
    private = "00 00 6D 43"

    #Convert the seed into a bytearray, strip off the carriage returns
    challenge = bytearray.fromhex(response.decode("UTF-8").strip('\r\r'))

    #Printing debugging info
    #print(challenge)
    #print("length of challenge: " + str(len(challenge)))

    #The length of the seed should be 6 (the response, plus the actual 4 byte seed)
    if len(challenge) is not 6:
        print("Issues getting challenge")
        return

    #Remove the first two bytes from the seed 
    del challenge[0]
    del challenge[0]

    #Convert the private key into a bytearray so we can do some math with it
    privateBytes = bytearray.fromhex(private)

    #Sum the private keey and the seed - this will be the key
    theKey = int.from_bytes(privateBytes, byteorder="big") + int.from_bytes(challenge, byteorder="big")

    #prepend 2704 to the key, and strip off the 0x
    theKey = "2704" + hex(theKey).lstrip("0x")

    #Send the key and print the response
    print(obd.sendRawCommand(theKey))

    #todo
    #Actually verify that the return result was an affirmative response, and then return 'true'

def getValuesFromECU(obd = None):
    #Define the global variables that we'll use...  They're the logging parameters
    # and the boolean used for whether or not we should be logging
    global logParams
    global logging
    logFile = None

    #Start logging
    while(True):
        #results = obd.sendRawCommand("22f200")
        #Static result for testing purposes
        results = "62F2000000725D"

        #Make sure the result starts with an affirmative
        if results.startswith("62F200"):

            #Set the datetime for the beginning of the row
            row = str(datetime.now().time())

            #Strip off the first 6 characters (62F200) so we only have the data
            results = results[6:]

            #The data comes back as raw data, so we need the size of each variable and its
            #  factor so that we can actually parse it.  In here, we'll pull X bytes off the 
            #  front of the result, process it, add it to the CSV row, and then remove it from
            #  the result
            for parameter in logParams:
                #Debugging output
                #print("Results: " + results)
                val = results[:logParams[parameter]['length']*2]
                #print("Value: " + val)
                val = int(val,16) * logParams[parameter]['factor']
                row += "," + str(val)
                results = results[logParams[parameter]['length']*2:]

            if logging is True:
                if logFile is None:
                    logFile = open("Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv", 'a')
                    logFile.write(csvHeader + '\n')

                logFile.write(row + '\n')
                print(row)

   
            if logging is False and logFile is not None:
                logFile.close()
                logFile = None


        #sleep to slow things down for testing        
        time.sleep(.3)
 

def main(obd = None):
    
    if obd is not None:

        #initiate the elm adapter
        print(obd.sendRawCommand("104f"))
 
        #gain level 3 security access
        gainLevel3(obd)
 
        #clear the f200 dynamic id
        print(obd.sendRawCommand("2c03f200"))

        #Initate the dynamicID with a bunch of memory addresses
        print(obd.sendRawCommand(defineIdentifier))

    #Start the polling thread
    try:
        readData = threading.Thread(target=getValuesFromECU, args=(obd,))
        readData.start()
    except:
        print("Error starting thread")

    #Start the loop that listens for the enter key
    while(True):
        global logging
        log = input()
        logging = not logging
        print("Logging is: " + str(logging))

#try to open the parameter file, if we can't, we'll work with a static
#  list of logged parameters for testing
try:
    with open('./parameter.yaml', 'r') as parameterFile:
        logParams = yaml.load(parameterFile)
except:
    print("No parameter file found, logging default values only")
    logParams = {'Engine speed':{ 'length':  0x02, 'factor': 1.0, 'units': "RPM", 'location': "0xD0012400"}}
    logParams["Adjustable boost: Adjustable top limit"] = {'length':  0x01,'factor':  17.0, 'units':  "hPa", 'location': '0xD001DE90'}
    logParams["Adjustable octane: Octane value"] = {'length':  0x01, 'factor':  1.0, 'units':  "ron", 'location': '0xD001DE8E'}


#Build the dynamicIdentifier request
if logParams is not None:
    defineIdentifier = "2C02F20014"
    csvHeader = "timestamp"
    for param in logParams:
        csvHeader += "," + param
        defineIdentifier += logParams[param]['location'].lstrip("0x")
        defineIdentifier += "0"
        defineIdentifier += str(logParams[param]['length'])

#print out the DID request for debugging
print(defineIdentifier)
print(csvHeader)
exit()

#I'm using a bluetooth OBDLink MX scantool
serialPort = '/dev/cu.OBDLinkLX-STN-SPP'
logging = False


#Make the user hit a key to get started
print("Press enter key to connect to the serial port")
connect = input()

#obdLink = OBDConnection(serialPort)

main()


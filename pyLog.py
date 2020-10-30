#!/usr/bin/env python3

#import datetime so we can put something in the CSV
from datetime import datetime

#yaml is used to define the logged parameters, bytes is for byte stuff, and
#  threading is so we can handle multiple threads (start the reader thread)
#  time is used so I could put pauses in various places
import yaml, threading, time

#import the udsoncan stuff
import udsoncan
from udsoncan.connections import IsoTPSocketConnection
from udsoncan.client import Client
from udsoncan import configs
from udsoncan import exceptions
from udsoncan import services

#udsoncan.setup_logging()

params = {
  'tx_padding': 0x55
}

def send_raw(data):
    global params
    conn2 = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
    conn2.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)
    conn2.open()
    conn2.send(data)
    results = conn2.wait_frame()
    conn2.close()
    return results

conn = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
conn.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)


#Gain level 3 security access to the ECU
def gainSecurityAccess(level, seed, params=None):
    #Print a debug message
    #print("Level " + level + " security")

    #Print the seed for debugging purposes
    #print(seed)

    #static resopnse used for testing
    #response = "01 02 1B 57 2C 42"
    
    #the private key is used as a sum against the seed (for ED)
    private = "00 00 6D 43"

    #Convert the private key into a bytearray so we can do some math with it
    privateBytes = bytearray.fromhex(private)

    #Sum the private keey and the seed - this will be the key
    theKey = int.from_bytes(privateBytes, byteorder="big") + int.from_bytes(seed, byteorder="big")

    return theKey.to_bytes(4, 'big')

def getValuesFromECU(client = None):
    #Define the global variables that we'll use...  They're the logging parameters
    # and the boolean used for whether or not we should be logging
    global logParams
    global logging
    logFile = None

    #Start logging
    while(True):
        results = (send_raw(bytes.fromhex('22F200'))).hex()
        print(results)
        #Static result for testing purposes
        #results = "F2000000725D"

        #Make sure the result starts with an affirmative
        if results.startswith("62f200"):

            #Set the datetime for the beginning of the row
            row = str(datetime.now().time())

            #Strip off the first 6 characters (F200) so we only have the data
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

        else:
            print("Logging not active")
        #sleep to slow things down for testing        
        #time.sleep(.05)
 

def main(client = None):
    
    if client is not None:

        print("Opening extended diagnostic session...")
        client.change_session(0x4F)

        print("Gaining level 3 security access")
        client.unlock_security_access(3)
 
        #clear the f200 dynamic id
        send_raw(bytes.fromhex('2C03f200'))

        #Initate the dynamicID with a bunch of memory addresses
        send_raw(bytes.fromhex(defineIdentifier))

    #Start the polling thread
    try:
        readData = threading.Thread(target=getValuesFromECU, args=(client,))
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
    with open('./parameters.yaml', 'r') as parameterFile:
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

logging = False


with Client(conn,  request_timeout=2, config=configs.default_client_config) as client:
    try:
        #Make the user hit a key to get started
        print("Press enter key to connect to the serial port")
        connect = input()

        client.config['security_algo'] = gainSecurityAccess
        
        main(client)
    except exceptions.NegativeResponseException as e:
        print('Server refused our request for service %s with code "%s" (0x%02x)' % (e.response.service.get_name(), e.response.code_name, e.response.code))
    except exceptions.InvalidResponseException as e:
        print('Server sent an invalid payload : %s' % e.response.original_payload)
    except exceptions.UnexpectedResponseException as e:
        print('Server sent an invalid payload : %s' % e.response.original_payload)
        

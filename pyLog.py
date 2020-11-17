#!/usr/bin/env python3

#import datetime so we can put something in the CSV, and import timedelta
# which will help us calculate the time to stop WOT logging
from datetime import datetime, timedelta

#yaml is used to define the logged parameters, bytes is for byte stuff, and
#  threading is so we can handle multiple threads (start the reader thread)
#  time is used so I could put pauses in various places
import yaml, threading, time, argparse, os, logging, smtplib, ssl, socket

#import the udsoncan stuff
import udsoncan
from udsoncan.connections import IsoTPSocketConnection
from udsoncan.client import Client
from udsoncan import configs
from udsoncan import exceptions
from udsoncan import services
from dashing import *

#import the necessary smtp related libraries
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

#build the argument parser and set up the arguments
parser = argparse.ArgumentParser(description='Simos18 High Speed Logger')
parser.add_argument('--headless', action='store_true')
parser.add_argument('--filepath',help="location to be used for the parameter and the log output location")

args = parser.parse_args()

#Set the global headless mode
headless = args.headless

#Set the global file path
if args.filepath is not None:
    filepath = args.filepath 
else:
    filepath = "./"

datalogging = False

#Set up the activity logging
logfile = filepath + "activity_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"
logging.basicConfig(filename=logfile, level=logging.DEBUG)

logging.debug("something")


#udsoncan.setup_logging()

params = {
  'tx_padding': 0x55
}

def minimum(a, b): 
    if a <= b: 
        return a 
    else: 
        return b 

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

ui = None

def buildUserInterface():
    global ui

    ui = VSplit(
                HGauge(title="RPM", label="0", border_color=5),
                HGauge(title="Boost", label="0", border_color=5),
                HGauge(title="Lambda", label="0", border_color=5),
                Log(title='Logging Status', border_color=5, color=1),
                Log(title='Raw', border_color=5, color=2),

                title='SimosCANLog',
        )

    ui.items[4].append("Raw CAN data")

def updateUserInterface( rawData = "Data", rpm = 750, boost = 1010, afr = 1.0 ):
    global ui
    global datalogging
    rpmGauge = ui.items[0]
    boostGauge = ui.items[1]
    afrGauge = ui.items[2]
    log = ui.items[3]
    raw = ui.items[4]

    log.append(str(datalogging))
    raw.append(str(rawData))

    rpmPercent = int(rpm / 8000 * 100)
    rpmGauge.value = minimum(100,rpmPercent)
    rpmGauge.label = str(rpm)

    if rpmPercent < 60:
        rpmGauge.color = 2
    elif rpmPercent < 80:
        rpmGauge.color = 3
    else:
        rpmGauge.color = 1

    boostPercent = int(boost / 3000 * 100)
    boostGauge.value = minimum(100,boostPercent)
    boostGauge.label = str(boost)

    if boostPercent < 40:
        boostGauge.color = 2
    elif boostPercent < 75:
        boostGauge.color = 3
    else:
        boostGauge.color = 1

    afrPercent = int(afr * 100 - 70)
    afrGauge.value = minimum(100,afrPercent)
    afrGauge.label = str(afr)

    if afrPercent < 15:
        afrGauge.color = 2
    elif afrPercent < 25:
        afrGauge.color = 3
    else:
        afrGauge.color = 1

    log.append(str(datalogging))
    if datalogging is True:
        log.color = 3
    else:
        log.color = 1

    ui.display()


#Gain level 3 security access to the ECU
def gainSecurityAccess(level, seed, params=None):
    #Print a debug message
    #logging.debug("Level " + level + " security")

    #Print the seed for debugging purposes
    #logging.debug(seed)

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
    global datalogging
    global headless
    global filepath

    logFile = None
    stopTime = None

    displayRPM = 0
    displayBoost = 0
    displayAFR = 0

    #Start logging
    while(True):
        if stopTime is not None and headless is True:
            if datetime.now() > stopTime:
                stopTime = None
                datalogging = False

        results = (send_raw(bytes.fromhex('22F200'))).hex()
        #logging.debug(results)
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
                #logging.debug("Results: " + results)
                val = results[:logParams[parameter]['length']*2]
                #logging.debug("Value: " + val)
                val = round(int.from_bytes(bytearray.fromhex(val),'little', signed=logParams[parameter]['signed']) / logParams[parameter]['factor'], 2)
                row += "," + str(val)
                results = results[logParams[parameter]['length']*2:]

                if parameter == "Engine speed":
                    displayRPM = round(val)
                elif parameter == "Pressure upstream throttle":
                    displayBoost = round(val)
                elif parameter == "Lambda value":
                    displayAFR = round(val,2)
                elif parameter == "Accelerator pedal":
                    if headless == True:
                        if val > 80:
                            stopTime = None
                            datalogging = True
                        elif val < 80 and datalogging == True and stopTime is None:
                            stopTime = datetime.now() + timedelta(seconds = 5)

            if datalogging is False and logFile is not None:
                logFile.close()
                logFile = None

            if datalogging is True:
                if logFile is None:
                    logFile = open(filepath + "Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv", 'a')
                    logFile.write(csvHeader + '\n')

                logFile.write(row + '\n')
                #logging.debug(row)

   
        else:
            logging.debug("Logging not active")

        if headless == False:
            updateUserInterface(rawData = str(results), rpm = displayRPM, boost = displayBoost, afr = displayAFR)
        #else:
            #logging.debug(results)


        #Slow things down for testing
        #time.sleep(.1)
 

def main(client = None):
    
    if client is not None:

        logging.debug("Opening extended diagnostic session...")
        client.change_session(0x4F)

        logging.debug("Gaining level 3 security access")
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
        logging.debug("Error starting thread")

    #Start the loop that listens for the enter key
    while(True):
        global datalogging
        log = input()
        datalogging = not datalogging
        logging.debug("Logging is: " + str(datalogging))


def loadDefaultParams():
    global logParams

    if not os.path.exists("./parameters.yaml"):
        exit(1)
    else:
        try:
            with open('./parameters.yaml', 'r') as parameterFile:
                logParams = yaml.load(parameterFile)
        except:
            logging.debug("No parameter file found, or can't load file, setting defaults")

#Helper function that just gets the local IP address of the Pi (so we can email it as a notification for debugging purposes)
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

    
def notificationEmail(mailsettings, msg, attachment = None):
    port = mailsettings['smtp_port']
    smtp_server = mailsettings['smtp_server']
    sender_email = mailsettings['from']
    receiver_email = mailsettings['to']
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "Simos Logger Notification"
    message.attach(MIMEText(msg, "plain"))

    # Create a secure SSL context
    context = ssl.create_default_context()

    text = message.as_string()

    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(mailsettings['from'], mailsettings['password'])
        server.sendmail(sender_email, receiver_email, text)



#try to open the parameter file, if we can't, we'll work with a static
#  list of logged parameters for testing
if os.path.exists(filepath + 'parameters.yaml') and os.access(filepath + 'parameters.yaml', os.R_OK):
    try:
        logging.debug("Loading parameters from: " + filepath + "parameters.yaml")
        with open(filepath + "parameters.yaml", 'r') as parameterFile:
            logParams = yaml.load(parameterFile)
    except:
        logging.debug("No parameter file found, or can't load file, setting defaults")
        loadDefaultParams()

if os.path.exists(filepath + 'config.yaml') and os.access(filepath + 'config.yaml', os.R_OK):
    try:
        logging.debug("Loading configuration file: " + filepath + "config.yaml")
        with open(filepath + "config.yaml", 'r') as configFile:
            configuration = yaml.load(configFile)
        
        notificationEmail(configuration['notification'], "Starting logger with IP address: " + get_ip())
    except:
        logging.debug("No configuration file loaded")
        configuration = None
else:
    configuration = None


#Build the dynamicIdentifier request
if logParams is not None:
    defineIdentifier = "2C02F20014"
    csvHeader = "timestamp"
    for param in logParams:
        csvHeader += "," + param
        defineIdentifier += logParams[param]['location'].lstrip("0x")
        defineIdentifier += "0"
        defineIdentifier += str(logParams[param]['length'])


with Client(conn,  request_timeout=2, config=configs.default_client_config) as client:
    try:

        if headless == False:
            buildUserInterface()
            updateUserInterface()
            #Make the user hit a key to get started
            print("Press enter key to connect to the serial port")
            connect = input()

        #Set up the security algorithm for the uds connection
        client.config['security_algo'] = gainSecurityAccess
        
        main(client)


    except exceptions.NegativeResponseException as e:
        logging.debug('Server refused our request for service %s with code "%s" (0x%02x)' % (e.response.service.get_name(), e.response.code_name, e.response.code))
    except exceptions.InvalidResponseException as e:
        logging.debug('Server sent an invalid payload : %s' % e.response.original_payload)
    except exceptions.UnexpectedResponseException as e:
        logging.debug('Server sent an invalid payload : %s' % e.response.original_payload)
    except exceptions.TimeoutException as e:
        logging.debug('Timeout waiting for response on can: ' + str(e))
        if configuration is not None and 'notification' in configuration:
            with open(logfile) as activityLog:
                msg = activityLog.read()
                notificationEmail(configuration['notification'], msg)
        

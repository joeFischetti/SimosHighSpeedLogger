#!/usr/bin/env python3

#import datetime so we can put something in the CSV, and import timedelta
# which will help us calculate the time to stop WOT logging
from datetime import datetime, timedelta

#yaml is used to define the logged parameters, bytes is for byte stuff, and
#  threading is so we can handle multiple threads (start the reader thread)
#  time is used so I could put pauses in various places
#  argparse is used to handle the argument parser
#  os does various filesystem/path checks
#  logging is used so we can log to an activity log
#  smtplib, ssl, and socket are all used in support of sending email
#  struct is used for some of the floating point conversions from the ECU
import yaml, threading, time, argparse, os, logging, smtplib, ssl, socket, struct, random
import json

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

#dataStream is an object that will be passed to the web GUI
dataStream = {}

   

#build the argument parser and set up the arguments
parser = argparse.ArgumentParser(description='Simos18 High Speed Logger')
parser.add_argument('--headless', action='store_true')
parser.add_argument('--filepath',help="location to be used for the parameter and the log output location")
parser.add_argument('--level',help="Log level for the activity log, valid levels include: DEBUG, INFO, WARNING, ERROR, CRITICAL")
parser.add_argument('--testing', help="testing mode, for use when not connected to a car", action='store_true')
parser.add_argument('--runserver', help="run an app server, used with the android app", action='store_true')
parser.add_argument('--interactive', help="run in interactive mode, start/stop logging with the enter key", action='store_true')




args = parser.parse_args()

#Set the global headless mode
headless = args.headless

#set the global testing mode
TESTING = args.testing

#set the global for runserver
RUNSERVER = args.runserver

#set the global for interactive mode
INTERACTIVE = args.interactive

#Set the global file path to the argument, or local
if args.filepath is not None:
    filepath = args.filepath 
else:
    filepath = "./"


#Set up the activity logging
logfile = filepath + "activity_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"


if args.level is not None:
    loglevels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    logging.basicConfig(filename=logfile, level=loglevels.get(args.level.upper(), logging.DEBUG))

else:
    logging.basicConfig(filename=logfile, level=logging.DEBUG)

logging.debug("Current filepath: " + filepath)
logging.debug("Activity log file: " + logfile)
logging.debug("Headless mode: " + str(headless))


PARAMFILE = filepath + "parameters.yaml"
logging.info("Parameter file: " + PARAMFILE)

CONFIGFILE = filepath + "config.yaml"
logging.info("Configuration file: " + CONFIGFILE)

datalogging = False
ui = None

if TESTING is False:
    params = {
      'tx_padding': 0x55
    }
    
    conn = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
    conn.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)

def stream_data():
    HOST = '0.0.0.0'  # Standard loopback interface address (localhost)
    PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

    while 1:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, PORT))
                s.listen()
                conn, addr = s.accept()
                logging.info("Listening on " + str(HOST) + ":" + str(PORT))
                with conn:
                    print('Connected by', addr)
                    while True:
                        json_data = json.dumps(dataStream) + "\n"
                        #json_data = "something\n"
                        conn.sendall(json_data.encode())
                        time.sleep(.5)
        except:
            logging.info("socket closed due to error or client disconnect")
     
#A basic helper function that just returns the minimum of two values
def minimum(a, b): 
    if a <= b: 
        return a 
    else: 
        return b 


#A function used to send raw data (so we can create the dynamic identifier etc), since udsoncan can't do it all
def send_raw(data):
    global params
    conn2 = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
    conn2.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)
    conn2.open()
    conn2.send(data)
    results = conn2.wait_frame()
    conn2.close()
    return results



#Build the user interface using dasher
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


#Update the user interface with RPM, Boost, and AFR
def updateUserInterface( rawData = "Data", rpm = 750, boost = 1010, afr = 1.0 ):
    global ui
    global datalogging
    global dataStream

    rpmGauge = ui.items[0]
    boostGauge = ui.items[1]
    afrGauge = ui.items[2]
    log = ui.items[3]
    raw = ui.items[4]

    if 'Engine speed' in dataStream:
        rpm = round(float(dataStream['Engine speed']))
    else:
        rpm = 750

    if 'Pressure upstream throttle' in dataStream:
        boost = round(float(dataStream['Pressure upstream throttle']))
    else:
        boost = 1010

    if 'Lambda value' in dataStream:
        afr = round(float(dataStream['Lambda value']),2)
    else:
        afr = 1.0

    log.append(str(datalogging))
    #raw.append()

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
    logging.info("Level " + str(level) + " security")

    logging.debug(seed)

    #the private key is used as a sum against the seed (for ED)
    private = "00 00 6D 43"

    #Convert the private key into a bytearray so we can do some math with it
    privateBytes = bytearray.fromhex(private)

    #Sum the private keey and the seed - this will be the key
    theKey = int.from_bytes(privateBytes, byteorder="big") + int.from_bytes(seed, byteorder="big")

    return theKey.to_bytes(4, 'big')


#Read the identifier from the ECU
def getValuesFromECU(client = None):
    #Define the global variables that we'll use...  They're the logging parameters
    # and the boolean used for whether or not we should be logging
    global logParams
    global datalogging
    global headless
    global filepath
    global dataStream

    logFile = None
    stopTime = None

    displayRPM = 0
    displayBoost = 0
    displayAFR = 0


    if 'notification' in configuration:
        notificationEmail(configuration['notification'], "Sucessfully connected to ECU, starting logger process.\nValues will be written to a log file when cruise control is active")


    #Start logging
    while(True):
        if stopTime is not None and headless is True:
            if datetime.now() > stopTime:
                stopTime = None
                datalogging = False

        results = (send_raw(bytes.fromhex('22F200'))).hex()

        #Make sure the result starts with an affirmative
        if results.startswith("62f200"):

            dataStreamBuffer = {}

            #Set the datetime for the beginning of the row
            row = str(datetime.now().time())
            dataStreamBuffer['timestamp'] = str(datetime.now().time())
            dataStreamBuffer['datalogging'] = {'value': str(datalogging), 'raw': ""}


            #Strip off the first 6 characters (F200) so we only have the data
            results = results[6:]

            #The data comes back as raw data, so we need the size of each variable and its
            #  factor so that we can actually parse it.  In here, we'll pull X bytes off the 
            #  front of the result, process it, add it to the CSV row, and then remove it from
            #  the result
            for parameter in logParams:
                val = results[:logParams[parameter]['length']*2]
                logging.debug(str(parameter) + " raw from ecu: " + str(val))
                rawval = int.from_bytes(bytearray.fromhex(val),'little', signed=logParams[parameter]['signed'])
                logging.debug(str(parameter) + " pre-function: " + str(rawval))
                val = round(eval(logParams[parameter]['function'], {'x':rawval, 'struct': struct}), 2)
                row += "," + str(val)
                logging.debug(str(parameter) + " scaling applied: " + str(val))

                results = results[logParams[parameter]['length']*2:]

                dataStreamBuffer[parameter] = str(val)


            dataStream = dataStreamBuffer

            if 'Cruise' in dataStream:
                if dataStream['Cruise'] != 0:
                    logging.debug("Cruise control logging enabled")
                    stopTime = None
                    datalogging = True
                elif val == 0 and datalogging == True and stopTime is None:
                    stopTime = datetime.now() + timedelta(seconds = 5)
                

            if datalogging is False and logFile is not None:
                logging.debug("Datalogging stopped, closing file")
                logFile.close()
                logFile = None

            if datalogging is True:
                if logFile is None:
                    filename = filepath + "Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
                    logging.debug("Creating new logfile at: " + filename)
                    logFile = open(filename, 'a')
                    logFile.write(csvHeader + '\n')

                logFile.write(row + '\n')
        
        #else:
        #    logging.debug("Logging not active")

        #If we're not running headless, update the display
        if headless == False:
            updateUserInterface()

def getFakeData():
    global dataStream

    while(True):
        localDataStream = {}

        localDataStream['timestamp'] = {'value': str(datetime.now().time()), 'raw': ""}
        localDataStream['datalogging'] = {'value': str(datalogging), 'raw': ""}

        for parameter in logParams:
            fakeVal = round(random.random() * 100)
            localDataStream[parameter] = {'value': str(fakeVal), 'raw': hex(fakeVal)}
        logging.debug("Populating fake data")
        dataStream = localDataStream

        #If we're not running headless, update the display
        if headless == False:
            updateUserInterface()


        time.sleep(.1)


#Main loop
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
            logging.critical("Error starting ECU thread")

    else:
        try:
            fakeData = threading.Thread(target=getFakeData)
            fakeData.start()
        except:
            logging.critical("Error starting fake data thread")

    if RUNSERVER is True:
        try:
            streamData = threading.Thread(target=stream_data)
            streamData.start()
            logging.info("Started data streaming thread")
        except:
            logging.critical("Error starting data streamer")
    
    if INTERACTIVE is True:
        #Start the loop that listens for the enter key
        while(True):
            global datalogging
            log = input()
            logging.debug("Input from user: " + log)
            datalogging = not datalogging
            logging.debug("Logging is: " + str(datalogging))


#Load default parameters, in the event that no parameter file was passed
def loadDefaultParams():
    global logParams

    if not os.path.exists("./parameters.yaml"):
        exit(1)
    else:
        try:
            with open('./parameters.yaml', 'r') as parameterFile:
                logParams = yaml.load(parameterFile)
        except:
            logging.warning("No parameter file found, or can't load file, setting defaults")

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


#Function to send notification emails out (i.e. when the logger is started, and when exceptions are thrown) 
def notificationEmail(mailsettings, msg, attachment = None):
    logging.debug("Sending email")
    #Set up all the email sever/credential information (from the configuration file)
    port = mailsettings['smtp_port']
    smtp_server = mailsettings['smtp_server']
    sender_email = mailsettings['from']
    receiver_email = mailsettings['to']

    #Set up the messge (so that attachments can be added)
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "Simos Logger Notification"
    message.attach(MIMEText(msg, "plain"))

    # Create a secure SSL context
    context = ssl.create_default_context()

    text = message.as_string()

    #Send the mail message
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(mailsettings['from'], mailsettings['password'])
        server.sendmail(sender_email, receiver_email, text)



#try to open the parameter file, if we can't, we'll work with a static
#  list of logged parameters for testing
if os.path.exists(PARAMFILE) and os.access(PARAMFILE, os.R_OK):
    try:
        logging.debug("Loading parameters from: " + PARAMFILE)
        with open(PARAMFILE, 'r') as parameterFile:
            logParams = yaml.load(parameterFile)
    except:
        logging.info("No parameter file found, or can't load file, setting defaults")
        loadDefaultParams()

if os.path.exists(CONFIGFILE) and os.access(CONFIGFILE, os.R_OK):
    try:
        logging.debug("Loading configuration file: " + CONFIGFILE)
        with open(CONFIGFILE, 'r') as configFile:
            configuration = yaml.load(configFile)
        
        if 'notification' in configuration:
            notificationEmail(configuration['notification'], "Starting logger with IP address: " + get_ip())

    except Exception as e:
        logging.info("No configuration file loaded: " + str(e))
        configuration = None
else:
    logging.info("No configuration file found")
    configuration = None


#Build the dynamicIdentifier request
if logParams is not None:
    defineIdentifier = "2C02F20014"
    csvHeader = "timestamp"
    for param in logParams:
        csvHeader += "," + param
        logging.debug("Logging parameter: " + param + "|" + str(logParams[param]['location']) + "|" + str(logParams[param]['length']))
        defineIdentifier += logParams[param]['location'].lstrip("0x")
        defineIdentifier += "0"
        defineIdentifier += str(logParams[param]['length'])

if headless == False:
    buildUserInterface()
    updateUserInterface()
 

#If testing is true, we'll run the main thread now without defining the
#  uds client
if TESTING is True:
    logging.debug("Starting main thread in testing mode")
    main()

else:
    with Client(conn,request_timeout=2, config=configs.default_client_config) as client:
        try:

            #Set up the security algorithm for the uds connection
            client.config['security_algo'] = gainSecurityAccess
            
            main(client)
    
    
        except exceptions.NegativeResponseException as e:
            logging.critical('Server refused our request for service %s with code "%s" (0x%02x)' % (e.response.service.get_name(), e.response.code_name, e.response.code))
            if configuration is not None and 'notification' in configuration:
                with open(logfile) as activityLog:
                    msg = activityLog.read()
                    notificationEmail(configuration['notification'], msg)
     
        except exceptions.InvalidResponseException as e:
            logging.critical('Server sent an invalid payload : %s' % e.response.original_payload)
            if configuration is not None and 'notification' in configuration:
                with open(logfile) as activityLog:
                    msg = activityLog.read()
                    notificationEmail(configuration['notification'], msg)
     
        except exceptions.UnexpectedResponseException as e:
            logging.critical('Server sent an invalid payload : %s' % e.response.original_payload)
            if configuration is not None and 'notification' in configuration:
                with open(logfile) as activityLog:
                    msg = activityLog.read()
                    notificationEmail(configuration['notification'], msg)
     
        except exceptions.TimeoutException as e:
            logging.critical('Timeout waiting for response on can: ' + str(e))
            if configuration is not None and 'notification' in configuration:
                with open(logfile) as activityLog:
                    msg = activityLog.read()
                    notificationEmail(configuration['notification'], msg)
        except Exception as e:
            logging.critical("Unhandled exception: " + str(e))
            if configuration is not None and 'notification' in configuration:
                with open(logfile) as activityLog:
                    msg = activityLog.read()
                    notificationEmail(configuration['notification'], msg)
            raise
            

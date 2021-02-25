#!/usr/bin/env python3

#import datetime so we can put something in the CSV, and import timedelta
# which will help us calculate the time to stop WOT logging
from datetime import datetime, timedelta

from python_j2534.connections import J2534Connection

try:
    import can
except Exception as e:
    print(e)

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



class hsl_logger():
    def __init__(self, testing = False, runserver = False, 
        interactive = False, mode = "2C", level = None, path = './', 
        callback_function = None, interface = "J2534"):
        
        self.activityLogger = logging.getLogger("SimosHSL")

        self.dataStream = {}
        self.datalogging = False
        self.TESTING = testing
        self.RUNSERVER = runserver
        self.INTERACTIVE = interactive
        self.INTERFACE = interface
        self.callback_function = callback_function
        self.MODE = mode
        self.FILEPATH = path
        self.stopTime = None
        self.configuration = {}
        self.defineIdentifier = None

        #Set up the activity logging
        self.logfile = self.FILEPATH + "activity_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"

        f_handler = logging.FileHandler(self.logfile)

        if level is not None:
            loglevels = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
    
            self.activityLogger.setLevel(level)
    
        else:
            self.activityLogger.setLevel(logging.DEBUG)
   
            f_handler.setLevel(logging.DEBUG) 
            c_handler = logging.StreamHandler()
            self.activityLogger.addHandler(f_handler)
            self.activityLogger.addHandler(c_handler)


        self.activityLogger.debug("Current path arg: " + path)
        self.activityLogger.debug("Current filepath: " + self.FILEPATH)
        self.activityLogger.debug("Activity log file: " + self.logfile)
    
        self.activityLogger.info("Connection type:  " + self.MODE)
        self.activityLogger.info("App server: " + str(self.RUNSERVER))
        self.activityLogger.info("Interactive mode: " + str(self.INTERACTIVE))
    
        self.PARAMFILE = self.FILEPATH + "parameters.yaml"
        self.activityLogger.info("Parameter file: " + self.PARAMFILE)
    
        self.CONFIGFILE = self.FILEPATH + "config.yaml"
        self.activityLogger.info("Configuration file: " + self.CONFIGFILE)

            #If we're not in testing mode, start up communication with the ECU
        if self.TESTING is False:
            if self.INTERFACE == "J2534":
                self.conn = J2534Connection(windll = 'C:/Program Files (x86)/OpenECU/OpenPort 2.0/drivers/openport 2.0/op20pt32.dll', rxid=0x7E8, txid=0x7E0)
                self.conn.open()

            else:
                params = {
                  'tx_padding': 0x55
                }
            
                self.conn = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
                self.conn.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)
                self.conn.open()
    
        #try to open the parameter file, if we can't, we'll work with a static
        #  list of logged parameters for testing
        if os.path.exists(self.PARAMFILE) and os.access(self.PARAMFILE, os.R_OK):
            try:
                self.activityLogger.debug("Loading parameters from: " + self.PARAMFILE)
                with open(self.PARAMFILE, 'r') as parameterFile:
                    self.logParams = yaml.load(parameterFile)
            except:
                self.activityLogger.info("No parameter file found, or can't load file, setting defaults")
                exit()
    
        if os.path.exists(self.CONFIGFILE) and os.access(self.CONFIGFILE, os.R_OK):
            try:
                self.activityLogger.debug("Loading configuration file: " + self.CONFIGFILE)
                with open(self.CONFIGFILE, 'r') as configFile:
                    self.configuration = yaml.load(configFile)
            
                if 'notification' in self.configuration:
                    notificationEmail(configuration['notification'], "Starting logger with IP address: " + get_ip())
    
            except Exception as e:
                self.activityLogger.info("No configuration file loaded: " + str(e))
                self.configuration = None
        else:
            self.activityLogger.info("No configuration file found")
            self.configuration = None
    
    
        #Build the dynamicIdentifier request
        if self.logParams is not None:
            self.defineIdentifier = "2C02F20014"
            self.csvHeader = "timestamp"
            for param in self.logParams:
                self.csvHeader += "," + param
                self.activityLogger.debug("Logging parameter: " + param + "|" + str(self.logParams[param]['location']) + "|" + str(self.logParams[param]['length']))
                self.defineIdentifier += self.logParams[param]['location'].lstrip("0x")
                self.defineIdentifier += "0"
                self.defineIdentifier += str(self.logParams[param]['length'])
    
        self.activityLogger.info("CSV Header for log files will be: " + self.csvHeader)

    def start_logger(self):
            #If testing is true, we'll run the main thread now without defining the
            #  uds client
            if self.TESTING:
                self.activityLogger.debug("Starting main thread in testing mode")
                self.main()
    
            else:
                with Client(self.conn,request_timeout=2, config=configs.default_client_config) as client:
                    try:
    
                        #Set up the security algorithm for the uds connection
                        client.config['security_algo'] = gainSecurityAccess
                
                        self.main(client = client)
        
        
                    except exceptions.NegativeResponseException as e:
                        self.activityLogger.critical('Server refused our request for service %s with code "%s" (0x%02x)' % (e.response.service.get_name(), e.response.code_name, e.response.code))
                        if self.configuration is not None and 'notification' in self.configuration:
                            with open(self.logfile) as activityLog:
                                msg = activityLog.read()
                                notificationEmail(self.configuration['notification'], msg)
         
                    except exceptions.InvalidResponseException as e:
                        self.activityLogger.critical('Server sent an invalid payload : %s' % e.response.original_payload)
                        if configuration is not None and 'notification' in configuration:
                            with open(logfile) as activityLog:
                                msg = activityLog.read()
                                notificationEmail(configuration['notification'], msg)
         
                    except exceptions.UnexpectedResponseException as e:
                        self.activityLogger.critical('Server sent an invalid payload : %s' % e.response.original_payload)
                        if configuration is not None and 'notification' in configuration:
                            with open(logfile) as activityLog:
                                msg = activityLog.read()
                                notificationEmail(configuration['notification'], msg)
         
                    except exceptions.TimeoutException as e:
                        self.activityLogger.critical('Timeout waiting for response on can: ' + str(e))
                        if configuration is not None and 'notification' in configuration:
                            with open(logfile) as activityLog:
                                msg = activityLog.read()
                                notificationEmail(configuration['notification'], msg)
                    except Exception as e:
                        self.activityLogger.critical("Unhandled exception: " + str(e))
                        if configuration is not None and 'notification' in configuration:
                            with open(logfile) as activityLog:
                                msg = activityLog.read()
                                notificationEmail(configuration['notification'], msg)
                        raise
 
    def main(self, client = None, callback = None, defineidentifier = None):
        
        if client is not None:
            self.activityLogger.debug("Opening extended diagnostic session...")
            client.change_session(0x4F)

            self.activityLogger.debug("Gaining level 3 security access")
            client.unlock_security_access(3)
 
            if self.MODE == "2C":
                #clear the f200 dynamic id
                send_raw(bytes.fromhex('2C03f200'))
                self.activityLogger.debug("Cleared dynamic identifier F200")
                #Initate the dynamicID with a bunch of memory addresses
                send_raw(bytes.fromhex(self.defineIdentifier))
                self.activityLogger.debug("Creted new dynamic identifier F200")

        try:
            self.activityLogger.info("Starting the data polling thread")
            readData = threading.Thread(target=self.getValuesFromECU)
            readData.daemon = True
            readData.start()
        except (KeyboardInterrupt, SystemExit):
            sys.exit()
        except:
            self.activityLogger.critical("Error starting the data reading thread")

        if self.RUNSERVER is True:
            try:
                streamData = threading.Thread(target=stream_data)
                streamData.daemon = True
                streamData.start()
                self.activityLogger.info("Started data streaming thread")
            except (KeyboardInterrupt, SystemExit):
                sys.exit()
            except:
                self.activityLogger.critical("Error starting data streamer")
    
        if self.INTERACTIVE is True:
            #Start the loop that listens for the enter key
            while(True):
                global datalogging
                log = input()
                self.activityLogger.debug("Input from user: " + log)
                datalogging = not datalogging
                self.activityLogger.debug("Logging is: " + str(datalogging))

        while 1:
            if callback:
                callback(dataStream)
            time.sleep(.5) 

    def getValuesFromECU(self):
        #Define the global variables that we'll use...  They're the logging parameters
        # and the boolean used for whether or not we should be logging
    
        self.activityLogger.debug("In the ECU Polling thread")
        self.logFile = None
        self.stopTime = None
        self.activityLogger.debug("Sending notification email")

        if 'notification' in self.configuration:
            notificationEmail(self.configuration['notification'], "Sucessfully connected to ECU, starting logger process.\nValues will be written to a log file when cruise control is active")

        self.activityLogger.info("Starting the ECU poller")

        #Start logging
        while(True):
            if self.stopTime is not None:
                if datetime.now() > self.stopTime:
                    self.stopTime = None
                    self.datalogging = False

            if self.MODE == "2C":
                self.getParams2C()
            elif self.MODE == "23":
                self.getParams23()
            else:
                self.getParams22()

    def getParams2C(self):
    
        self.activityLogger.debug("Getting values via 0x2C")

        if self.TESTING is True:
            results = "62f200"
            for parameter in self.logParams:
                fakeVal = round(random.random() * 100)
                results = results + str(hex(fakeVal)).lstrip('0x') + str(hex(fakeVal)).lstrip('0x')
            self.activityLogger.debug("Populated fake data: " + str(results))
        else:
            results = (self.send_raw(bytes.fromhex('22F200'))).hex()
 
        #Make sure the result starts with an affirmative
        if results.startswith("62f200"):
 
            self.dataStreamBuffer = {}
 
            #Set the datetime for the beginning of the row
            row = str(datetime.now().time())
            self.dataStreamBuffer['timestamp'] = {'value': str(datetime.now().time()), 'raw': ""}
            self.dataStreamBuffer['datalogging'] = {'value': str(self.datalogging), 'raw': ""}
 
 
            #Strip off the first 6 characters (F200) so we only have the data
            results = results[6:]
 
            #The data comes back as raw data, so we need the size of each variable and its
            #  factor so that we can actually parse it.  In here, we'll pull X bytes off the 
            #  front of the result, process it, add it to the CSV row, and then remove it from
            #  the result
            for parameter in self.logParams:
                val = results[:self.logParams[parameter]['length']*2]
                self.activityLogger.debug(str(parameter) + " raw from ecu: " + str(val))
                rawval = int.from_bytes(bytearray.fromhex(val),'little', signed=self.logParams[parameter]['signed'])
                self.activityLogger.debug(str(parameter) + " pre-function: " + str(rawval))
                val = round(eval(self.logParams[parameter]['function'], {'x':rawval, 'struct': struct}), 2)
                row += "," + str(val)
                self.activityLogger.debug(str(parameter) + " scaling applied: " + str(val))
 
                results = results[self.logParams[parameter]['length']*2:]
 
                self.dataStreamBuffer[parameter] = {'value': str(val), 'raw': str(rawval)}
 
 
            self.dataStream = self.dataStreamBuffer
 
            if 'Cruise' in self.dataStream:
                if self.dataStream['Cruise']['value'] != "0.0":
                    self.activityLogger.debug("Cruise control logging enabled")
                    self.stopTime = None
                    self.datalogging = True
                elif self.dataStream['Cruise']['value'] == "0.0" and self.datalogging == True and self.stopTime is None:
                    self.stopTime = datetime.now() + timedelta(seconds = 5)
            
 
            if self.datalogging is False and self.logFile is not None:
                self.activityLogger.debug("Datalogging stopped, closing file")
                self.logFile.close()
                self.logFile = None
 
            if self.datalogging is True:
                if self.logFile is None:
                    if 'logprefix' in self.configuration:
                        self.filename = self.FILEPATH + self.configuration['logprefix'] + "_Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
                    else:
                        self.filename = self.FILEPATH + "Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
                    self.activityLogger.debug("Creating new logfile at: " + self.filename)
                    self.logFile = open(self.filename, 'a')
                    self.logFile.write(self.csvHeader + '\n')
 
                self.logFile.write(row + '\n')

    #Function to send notification emails out (i.e. when the logger is started, and when exceptions are thrown) 
    def notificationEmail(self, mailsettings, msg, attachment = None):
        self.activityLogger.debug("Sending email")
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

    #A function used to send raw data (so we can create the dynamic identifier etc), since udsoncan can't do it all
    def send_raw(self,data):
        global conn
        global params

        results = None
        while results == None:
            conn.send(data)
            results = conn.wait_frame()
        return results

    def gainSecurityAccess(self, level, seed, params=None):
        self.activityLogger.info("Level " + str(level) + " security")

        self.activityLogger.debug(seed)

        #the private key is used as a sum against the seed (for ED)
        private = "00 00 6D 43"

        #Convert the private key into a bytearray so we can do some math with it
        privateBytes = bytearray.fromhex(private)

        #Sum the private keey and the seed - this will be the key
        theKey = int.from_bytes(privateBytes, byteorder="big") + int.from_bytes(seed, byteorder="big")

        return theKey.to_bytes(4, 'big')




#Stream data over a socket connection.  
#Open the socket, and if it happens to disconnect or fail, open it again
#This is used for the android app
def stream_data(callback = None):
    HOST = '0.0.0.0'  # Standard loopback interface address (localhost)
    PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

    while 1:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, PORT))
                s.listen()
                conn, addr = s.accept()
                activityLogger.info("Listening on " + str(HOST) + ":" + str(PORT))
                with conn:
                    print('Connected by', addr)
                    while True:
                        json_data = json.dumps(dataStream) + "\n"
                        activityLogger.debug("Sending json to app: " + json_data)
                        conn.sendall(json_data.encode())
                        time.sleep(.1)
        except:
            activityLogger.info("socket closed due to error or client disconnect")
    


#Read from the ECU using mode 22
def getParams22():
    global logParams
    global datalogging
    global HEADLESS
    global filepath
    global dataStream
    global logFile
    global stopTime

    activityLogger.debug("Getting values via 0x22")

    dataStreamBuffer = {}
    #Set the datetime for the beginning of the row
    row = str(datetime.now().time())
    dataStreamBuffer['timestamp'] = {'value': str(datetime.now().time()), 'raw': ""}
    dataStreamBuffer['datalogging'] = {'value': str(datalogging), 'raw': ""}
 

    for parameter in logParams:
        if TESTING is True:
            fakeVal = round(random.random() * 100)
            activityLogger.debug("Param String: " + '22' + logParams[parameter]['location'].lstrip("0x"))
            results = "62" + logParams[param]['location'].lstrip("0x") + str(hex(fakeVal)).lstrip('0x')
        else:
            results = (send_raw_2(bytes.fromhex('0322' + logParams[parameter]['location'].lstrip("0x") + "00000000"))).hex().rstrip('a')
            #print(str(results))

        if results.startswith("0562"):
        
            #Strip off the first 6 characters (63MEMORYLOCATION) so we only have the data
            results = results[8:]
 
            val = results[:logParams[parameter]['length']*2]
            activityLogger.debug(str(parameter) + " raw from ecu: " + str(val))
            #rawval = int.from_bytes(bytearray.fromhex(val),'little', signed=logParams[parameter]['signed'])
            rawval = int(val,16)
            activityLogger.debug(str(parameter) + " pre-function: " + str(rawval))
            val = round(eval(logParams[parameter]['function'], {'x':rawval, 'struct': struct}), 2)
            row += "," + str(val)
            activityLogger.debug(str(parameter) + " scaling applied: " + str(val))
 
 
            dataStreamBuffer[parameter] = {'value': str(val), 'raw': str(rawval)}
 
 
    dataStream = dataStreamBuffer
 
    if 'Cruise' in dataStream:
        if dataStream['Cruise']['value'] != "0.0":
            activityLogger.debug("Cruise control logging enabled")
            stopTime = None
            datalogging = True
        elif dataStream['Cruise']['value'] == "0.0" and datalogging == True and stopTime is None:
            stopTime = datetime.now() + timedelta(seconds = 5)
        

    if datalogging is False and logFile is not None:
        activityLogger.debug("Datalogging stopped, closing file")
        logFile.close()
        logFile = None

    if datalogging is True:
        if logFile is None:
            if 'logprefix' in configuration:
                filename = filepath + configuration['logprefix'] + "_Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
            else:
                filename = filepath + "Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"

            activityLogger.debug("Creating new logfile at: " + filename)
            activityLogger.debug("Header for CSV file: " + csvHeader)
            logFile = open(filename, 'a')
            logFile.write(csvHeader + '\n')
        activityLogger.debug(row)
        logFile.write(row + '\n')
        logFile.flush()

#Read from the ECU using mode 23
def getParams23():
    global logParams
    global datalogging
    global HEADLESS
    global filepath
    global dataStream
    global logFile
    global stopTime

    activityLogger.debug("Getting values via 0x23")

    dataStreamBuffer = {}
    #Set the datetime for the beginning of the row
    row = str(datetime.now().time())
    dataStreamBuffer['timestamp'] = {'value': str(datetime.now().time()), 'raw': ""}
    dataStreamBuffer['datalogging'] = {'value': str(datalogging), 'raw': ""}
 

    for parameter in logParams:
        if TESTING is True:
            fakeVal = round(random.random() * 100)
            activityLogger.debug("Param String: " + '2314' + logParams[parameter]['location'].lstrip("0x") + "0" + str(logParams[parameter]['length']))
            results = "63" + logParams[param]['location'].lstrip("0x") + str(hex(fakeVal)).lstrip('0x') + str(hex(fakeVal)).lstrip('0x')
        else:
            results = (send_raw(bytes.fromhex('2314' + logParams[parameter]['location'].lstrip("0x") + "0" + str(logParams[parameter]['length'])))).hex()

        if results.startswith("63"):
        
            #Strip off the first 6 characters (63MEMORYLOCATION) so we only have the data
            results = results[10:]
 
            val = results
            activityLogger.debug(str(parameter) + " raw from ecu: " + str(val))
            rawval = int.from_bytes(bytearray.fromhex(val),'little', signed=logParams[parameter]['signed'])
            activityLogger.debug(str(parameter) + " pre-function: " + str(rawval))
            val = round(eval(logParams[parameter]['function'], {'x':rawval, 'struct': struct}), 2)
            row += "," + str(val)
            activityLogger.debug(str(parameter) + " scaling applied: " + str(val))
 
 
            dataStreamBuffer[parameter] = {'value': str(val), 'raw': str(rawval)}
 
 
    dataStream = dataStreamBuffer
 
    if 'Cruise' in dataStream:
        if dataStream['Cruise']['value'] != "0.0":
            activityLogger.debug("Cruise control logging enabled")
            stopTime = None
            datalogging = True
        elif dataStream['Cruise']['value'] == "0.0" and datalogging == True and stopTime is None:
            stopTime = datetime.now() + timedelta(seconds = 5)
        

    if datalogging is False and logFile is not None:
        activityLogger.debug("Datalogging stopped, closing file")
        logFile.close()
        logFile = None

    if datalogging is True:
        if logFile is None:
            if 'logprefix' in configuration:
                filename = filepath + configuration['logprefix'] + "_Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
            else:
                filename = filepath + "Logging_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"

            activityLogger.debug("Creating new logfile at: " + filename)
            logFile = open(filename, 'a')
            logFile.write(csvHeader + '\n')

        logFile.write(row + '\n')


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



                

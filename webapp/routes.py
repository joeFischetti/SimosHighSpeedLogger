from webapp import webapp
from flask import render_template, jsonify, send_from_directory, request
import os
import re
from datetime import datetime
from operator import itemgetter
import simos_hsl
import json
import threading
import yaml

import sys
sys.path.insert(1, os.environ.get('HOME'))

from VW_Flash.lib import simos_flash_utils


logFilePath = os.environ.get('LOGFILEPATH')
aswFilePath = os.environ.get('ASWFILEPATH')
calFilePath = os.environ.get('CALFILEPATH')
flashingTaskID = None


hsl_logger = None
flasher = None
logger_thread = None
flasher_thread = None
flasher_filename = None

status = None

def update_callback(callback = None, *args, **kwargs):
    global status
    if callback:
        status = callback
        print("callback msg: " + callback)

    if kwargs:
        status = kwargs
        print("callback kwargs: " + str(kwargs))


def handle_uploaded_file(path, f):
    with open(path + str(f), 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)


@webapp.route("/")
def hello():
    return render_template('index.html', title="Simos High Speed Logger")

@webapp.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@webapp.route('/logger/filemanager')
def logfilemanager():

    logFiles = []
    for (dirpath, dirnames, filenames) in os.walk(logFilePath):
        for logfile in filenames:
            if re.match(".*\.csv$", logfile):
                logFiles.append({
                    'filename': str(logfile), 
                    'timestamp': os.path.getmtime(logFilePath + logfile), 
                    'timestampstring': str(datetime.fromtimestamp(os.path.getmtime(logFilePath + logfile)).strftime('%Y-%m-%d %H:%M:%S')),
                })
        break

    logFiles = sorted(logFiles, key=itemgetter('timestamp'), reverse=True)

    activityFiles = []
    for (dirpath, dirnames, filenames) in os.walk(logFilePath):
        for activityfile in filenames:
            if re.match(".*\.log$", activityfile):
                activityFiles.append({
                    'filename': str(activityfile), 
                    'timestamp': os.path.getmtime(logFilePath + activityfile), 
                    'timestampstring': str(datetime.fromtimestamp(os.path.getmtime(logFilePath + activityfile)).strftime('%Y-%m-%d %H:%M:%S')),
                })
        break

    activityFiles = sorted(activityFiles, key=itemgetter('timestamp'), reverse=True)



    context = {'filelist': logFiles, 'activityfiles': activityFiles} 

    return render_template('logfilemanager.html', context=context)

@webapp.route('/logger/download/<string:filename>')
def download_file(filename):
    return send_from_directory(logFilePath, filename)

@webapp.route('/logger/configuration', methods = ['GET', 'POST'])
def loggerconfig():

       
    if request.method == "POST":

        os.rename(logFilePath + "config.yaml", logFilePath + "config.yaml.bak")

        with open(logFilePath + "config.yaml", 'w') as configfile:
            yaml.dump(request.form.to_dict(), configfile, default_flow_style=False)

    with open(logFilePath + "config.yaml", 'r') as configfile:
        configuration = yaml.load(configfile, Loader = yaml.FullLoader)

    context = {'logfilepath': logFilePath,
                'configuration': configuration}

    return render_template('loggerconfig.html', context = context)



@webapp.route('/logger/delete/<string:filename>')
def delete_file(filename):

    if os.path.exists(logFilePath + filename):
        os.rename(logFilePath + filename, logFilePath + "old/" + filename)
    else:
        print("The file does not exist")


    return logfilemanager()



@webapp.route('/logger/startstop')
def startstop():
    loggingTaskID = "something"

    context = {'taskID': loggingTaskID} 
    return render_template('logger.html', context = context)   

@webapp.route('/logger/logger_status')
def logger_status():
    return jsonify(status)



@webapp.route('/logger/start_logger')
def start_logger():
    global hsl_logger
    global logger_thread
    
    if hsl_logger is not None:
        return jsonify({'taskID': "Logger already running"})

    hsl_logger = simos_hsl.hsl_logger(
        runserver=True,
        path= logFilePath,
        callback_function=update_callback,
        interface="CAN",
        singlecsv=False,
        mode="3E",
        level="INFO",
    )

    logger_thread = threading.Thread(target=hsl_logger.start_logger)
    logger_thread.daemon = True
    logger_thread.start()

    return jsonify({'taskID': "Logger Started"})


@webapp.route('/logger/stop_logger')
def stop_logger():
    global hsl_logger

    if hsl_logger is not None:
        hsl_logger.stop()
        hsl_logger = None

    return jsonify({'taskID': "Stopping Logger"})

@webapp.route('/flasher/filemanager', methods=["GET", "POST"])
def flashfilemanager():

    if request.method == "POST":
        if request.files['file']:
            request.files['file'].save(calFilePath + request.files['file'].filename)


    calFiles = []
    for (dirpath, dirnames, filenames) in os.walk(calFilePath):
        for logfile in filenames:
            if re.match(".*\.bin$", logfile):
                calFiles.append({
                    'filename': str(logfile), 
                    'timestamp': os.path.getmtime(calFilePath + logfile), 
                    'timestampstring': str(datetime.fromtimestamp(os.path.getmtime(calFilePath + logfile)).strftime('%Y-%m-%d %H:%M:%S')),
                })
        break

    calFiles = sorted(calFiles, key=itemgetter('timestamp'), reverse=True)

    aswFiles = []
    for (dirpath, dirnames, filenames) in os.walk(aswFilePath):
        for activityfile in filenames:
            if re.match(".*\.bin$", activityfile):
                aswFiles.append({
                    'filename': str(activityfile), 
                    'timestamp': os.path.getmtime(aswFilePath + activityfile), 
                    'timestampstring': str(datetime.fromtimestamp(os.path.getmtime(aswFilePath + activityfile)).strftime('%Y-%m-%d %H:%M:%S')),
                })
        break

    aswFiles = sorted(aswFiles, key=itemgetter('timestamp'), reverse=True)



    context = {'callist': calFiles, 'aswlist': aswFiles} 

    return render_template('flashfilemanager.html', context=context)

@webapp.route("/flasher/flashCal")  
def flash_calibration_picker():
    global flasher_thread
    global flasher_filename

    if flasher_thread:
        context = {'filename': flasher_filename, 'caldir': calFilePath, 'filename': calFilePath + flasher_filename, 'blocknum': 5, 'taskID': "Flashing Active"} 

        return render_template('flashcalibration.html', context = context)

    flashFiles = []
    for (dirpath, dirnames, filenames) in os.walk(calFilePath):
        for tunefile in filenames:
            if re.match("^.*\.bin$", tunefile):
                flashFiles.append({
                    'filename': str(tunefile),
                    'timestamp': os.path.getmtime(calFilePath + tunefile), 
                    'timestampstring': str(datetime.fromtimestamp(os.path.getmtime(calFilePath + tunefile)).strftime('%Y-%m-%d %H:%M:%S')),
                })

        break
    flashFiles = sorted(flashFiles, key=itemgetter('timestamp'), reverse=True)
 

    context = {'callist': flashFiles, 'caldir': calFilePath} 
    return render_template('flashcalibration.html', context = context)

@webapp.route("/system")  
def systemcommand():

    commands = ['shutdown', 'reboot', 'restart_webserver']

    context = {'commands': commands} 
    return render_template('systemcommands.html', context = context)


@webapp.route("/system/<string:command>")  
def systemcommands(command):
    if command == "shutdown":
        os.system("sudo shutdown 0")
    elif command == "reboot":
        os.system("sudo reboot")
    elif command == "restart_webserver":
        os.system("sudo systemctl restart hslwebapp.service")

    return render_template('index.html')


@webapp.route("/flasher/flashCal/<string:filename>")
def flash_calibration(filename):
    global flasher_thread
    global flasher_filename


    if flasher_thread is None:
        flasher_filename = filename
        def read_from_file(infile = None):
            f = open(infile, "rb")
            return f.read()

        blocks_infile = {}

        blocks_infile[calFilePath + filename] = {'blocknum': 5, 'binary_data': read_from_file(infile = str(calFilePath + filename))}
        flasher_thread = threading.Thread(target=simos_flash_utils.flash_bin, args=(blocks_infile, update_callback, "SocketCAN", ))
        flasher_thread.daemon = True
        flasher_thread.start()


    context = {'filename': filename, 'caldir': calFilePath, 'filename': calFilePath + filename, 'blocknum': 5, 'taskID': "Flashing Started"} 
    return render_template('flashcalibration.html', context=context)

@webapp.route("/flasher/flash_status")
def flash_status():

    return jsonify(status)






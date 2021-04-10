from webapp import webapp
from flask import render_template, jsonify, send_from_directory
import os
import re
from datetime import datetime
from operator import itemgetter
import simos_hsl
import json
import threading



logFilePath = os.environ.get('LOGFILEPATH')


hsl_logger = None
logger_thread = None
status = None

def update_callback(callback):
    global status
    status = callback


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
  
#



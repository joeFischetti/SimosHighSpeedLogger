#!/usr/bin/env python3

import argparse, simos_hsl

#build the argument parser and set up the arguments
parser = argparse.ArgumentParser(description='Simos18 High Speed Logger')
parser.add_argument('--headless', action='store_true')
parser.add_argument('--filepath',help="location to be used for the parameter and the log output location")
parser.add_argument('--level',help="Log level for the activity log, valid levels include: DEBUG, INFO, WARNING, ERROR, CRITICAL")
parser.add_argument('--testing', help="testing mode, for use when not connected to a car", action='store_true')
parser.add_argument('--runserver', help="run an app server, used with the android app", action='store_true')
parser.add_argument('--interactive', help="run in interactive mode, start/stop logging with the enter key", action='store_true')
parser.add_argument('--mode', help="set the connection mode: 2C, 23")


args = parser.parse_args()

simos_hsl.run_logger(testing = args.testing, headless = args.headless, runserver = args.runserver)

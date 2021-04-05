from flask import Flask, escape, request

webapp = Flask(__name__)


from webapp import routes

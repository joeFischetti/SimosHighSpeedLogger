import can
import argparse
from udsoncan.connections import IsoTPSocketConnection



#A function used to send raw data (so we can create the dynamic identifier etc), since udsoncan can't do it all
def send_raw(data):
    params = {
      'tx_padding': 0x55
    }


    results = None

    conn2 = IsoTPSocketConnection('can0', rxid=0x7E8, txid=0x7E0, params=params)
    conn2.tpsock.set_opts(txpad=0x55, tx_stmin=2500000)
    conn2.open()
    conn2.send(data)
    results = conn2.wait_frame()
    conn2.close()
    print(str(results))
    return results

def send_raw_2(data_bytes):
    bus = can.interface.Bus(bustype='socketcan', channel='can0', bitrate=250000)
    msg = can.Message(arbitration_id=0x7E8,
                      data=data_bytes,
                      is_extended_id=True)
    message = None

    try:
        bus.send(msg)
        print("Message sent on {}".format(bus.channel_info))
    except can.CanError:
        print("Message NOT sent")

    message = bus.recv()
    print(str(message))
    return message

#build the argument parser and set up the arguments
parser = argparse.ArgumentParser(description='udsoncan vs python-can test harness')
parser.add_argument('--testmode',help="whether you want to test python-can or udsoncan", required = True, choices=['udsoncan', 'python-can'])


args = parser.parse_args()

if args.testmode == "udsoncan":
    for i in range(0,30):
        send_raw(b'2210c0')
elif args.testmode == "python-can":
    for i in range(0,30):
        send_raw_2(b'032210c0')


import os, time, threading, json, logging
from http.server import HTTPServer, BaseHTTPRequestHandler

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length)
        print("== CAPTURE SERVER RECEIVED POST ==")
        print("PATH:", self.path)
        print("HEADERS:")
        for k, v in self.headers.items():
            print(f"  {k}: {v}")
        print("BODY:")
        try:
            print(body.decode())
        except Exception:
            print(repr(body))
        self.send_response(200)
        self.end_headers()


def serve():
    HTTPServer(('127.0.0.1', 9000), H).serve_forever()

# start capture server thread
if __name__ == '__main__':
    t = threading.Thread(target=serve, daemon=True)
    t.start()

    # configure telemetry env in-process
    os.environ['SFQ_TELEMETRY'] = '2'
    os.environ['SFQ_TELEMETRY_ENDPOINT'] = 'http://127.0.0.1:9000/telemetry'
    os.environ['SFQ_TELEMETRY_SAMPLING'] = '1.0'

    # ensure local import picks up env
    import importlib
    import sfq.telemetry as telemetry
    importlib.reload(telemetry)

    # build context payload matching your example
    ctx = {
        "method": "POST",
        "endpoint": "/services/Soap/m/65.0",
        "status": 200,
        "duration_ms": 158,
        "request_headers": {
            "User-Agent": "sfq/0.0.47",
            "Sforce-Call-Options": "client=sfq/0.0.47",
            "Accept": "application/json",
            "Content-Type": "text/xml; charset=UTF-8",
            "Authorization": "REDACTED",
            "SOAPAction": "retrieve",
        },
    }

    print('Emitting telemetry event...')
    telemetry.emit('http.request', ctx)

    # emit a log record to trigger the log handler
    log = logging.getLogger('sfq.test')
    log.setLevel(logging.DEBUG)
    log.error('Test error message containing Bearer SECRET12345 and id abcdef1234567890abcdef')

    # wait a short while for sender thread to process
    time.sleep(2)
    print('Calling telemetry.shutdown() to flush...')
    telemetry.shutdown(2.0)
    print('Done')

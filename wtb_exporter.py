"""built and tested on only WebtoB 4.1"""

import subprocess
import yaml
import argparse
import sys
from time import sleep
from socket import gethostname
import prometheus_client as prom


class WebtoBAdminConnector:
    """
    use WebtoB CLI tool 'wsadmin' to get data
    this class takes two arguments below,
     wtb_dir = webtob base directory
     wtb_svr = webtob server, check server directive in http.m file
    """

    def __init__(self, wtb_dir, wtb_svr):
        self.wtb_svr = wtb_svr
        self.wtbcmd = "export WEBTOBDIR=" + wtb_dir + "; $WEBTOBDIR/bin/wsadmin -C "

    def exec_cmd(self, subcmd="help"):
        cmd_result = subprocess.run(self.wtbcmd + subcmd, stdout=subprocess.PIPE, shell=True)
        return cmd_result.stdout.decode("utf-8")


class WebtoBExporter:
    """
    export metrics from current WebtoB status
    this class takes two arguments below,
     wtb_connect = WebtoBAdminConnector instance
     listen_port = listening port of this exporter
    """

    def __init__(self, wtb_connect, listen_port):
        self.wtb_svr = wtb_connect.wtb_svr
        self.exec_cmd = wtb_connect.exec_cmd
        self.hostname = gethostname()
        # start client and set metric attributes
        # this metric has 3 attributes
        self.gauge_req = prom.Gauge("wtb_http_requests", "number of http requests to webtob", ["webtob_server", "hostname", "http_handler"])
        self.gauge_resp = prom.Gauge("wtb_http_responses", "number of http responses to webtob", ["webtob_server", "hostname", "http_handler"])
        self.gauge_curq = prom.Gauge("wtb_http_current_queue_count", "number of waiting objects in a queue of webtob", ["webtob_server", "hostname", "http_handler"])
        self.gauge_tmoutq = prom.Gauge("wtb_http_timeout_queue_count", "number of dropped objects in a queue of  webtob", ["webtob_server", "hostname", "http_handler"])
        prom.start_http_server(listen_port)

    def get_metric(self):
        """
        get cli-format output then parse it
        then put values into metric
        """
        cmd_result_stdout = self.exec_cmd(subcmd="'svrinfo " + self.wtb_svr + "'")
        for row in cmd_result_stdout.splitlines():
            split_row = row.split()
            # rows are split into 13 values on webtob 4.1
            if len(split_row) == 13 and split_row[1] == self.wtb_svr:
                metric = {"hth": split_row[0], "req": split_row[5], "resp": split_row[6], "curq": split_row[7], "tmoutq": split_row[9]}
                self.gauge_req.labels(webtob_server=self.wtb_svr, hostname=self.hostname, http_handler=metric["hth"]).set(metric["req"])
                self.gauge_resp.labels(webtob_server=self.wtb_svr, hostname=self.hostname, http_handler=metric["hth"]).set(metric["resp"])
                self.gauge_curq.labels(webtob_server=self.wtb_svr, hostname=self.hostname, http_handler=metric["hth"]).set(metric["curq"])
                self.gauge_tmoutq.labels(webtob_server=self.wtb_svr, hostname=self.hostname, http_handler=metric["hth"]).set(metric["tmoutq"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", help="Configuration File Path")
    parser.add_argument("--web_listen_port", help="TCP Port to listen on", type=int)
    args = parser.parse_args()
    config_file = args.config_file if args.config_file is not None else "wtb_exporter.yaml"
    listen_port = args.web_listen_port if args.web_listen_port is not None else 9101

    try:
        with open(config_file, 'r') as f:
            conf = yaml.safe_load(f)
    except Exception as e:
        sys.exit(e)

    wtbcon = WebtoBAdminConnector(wtb_dir=conf["webtob_base_dir"], wtb_svr=conf["webtob_server_name"])
    xptr = WebtoBExporter(wtbcon, listen_port)

    while True:
        xptr.get_metric()
        sleep(3)

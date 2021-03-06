"""built and tested on only JEUS7"""

import subprocess
import re
import argparse
import yaml
import sys
from time import sleep
import prometheus_client as prom


class JeusadminConnector:
    """
    using JEUS CLI tool 'jeusadmin'
    this class takes 5 arguments below,
     jeus_base_dir = jeus base directory
     jeus_ms_name =  name of jeus managed server
     jeus_admin_socket = ip,port of jeus admin server
     jeus_credential_path = credential script to log in to admin
     jeus_listener_name = name of jeus listener for web connection
    """

    def __init__(self, jeus_base_dir, jeus_ms_name, jeus_admin_socket, jeus_credential_path, jeus_listener_name):
        self.jeus_ms_name = jeus_ms_name
        self.jeus_listener_name = jeus_listener_name
        self.jeuscmd = jeus_base_dir + "/bin/jeusadmin -host " + jeus_admin_socket + " -f " + jeus_base_dir + "/" + jeus_credential_path + " "

    def exec_cmd(self, cmd="help"):
        cmd_result = subprocess.run(self.jeuscmd + cmd, stdout=subprocess.PIPE, shell=True)
        return cmd_result.stdout.decode("utf-8")


class JeusExporter:
    """
    export metrics of current JEUS status
    this class takes 2 arguments below,
     jeus_connect = instance of JeusadminConnector
     listen_port = listening port of jeus exporter
    """

    def __init__(self, jeus_connect, listen_port):
        self.jeus_ms_name = jeus_connect.jeus_ms_name
        self.jeus_listener_name = jeus_connect.jeus_listener_name
        self.exec_cmd = jeus_connect.exec_cmd
        # start client and set metric attributes
        self.gauge_state = prom.Gauge("jeus_ms_state", "state of jeus managed server", ["jeus_ms"])
        self.gauge_cpu = prom.Gauge("jeus_ms_cpu_usage_percent", "cpu usage of jeus managed server", ["jeus_ms"])
        self.gauge_heap = prom.Gauge("jeus_ms_heap_usage_percent", "heap memory usage of jeus managed server", ["jeus_ms"])
        self.gauge_thread_active = prom.Gauge("jeus_active_thread_count", "active thread count of jeus managed server", ["jeus_ms"])
        self.gauge_thread_blocked = prom.Gauge("jeus_blocked_thread_count", "blocked thread count of jeus managed server", ["jeus_ms"])
        prom.start_http_server(listen_port)

    def get_metric(self):
        """
        get cli-format output then parse it
        then put values into metric
        """
        for ms in self.jeus_ms_name:
            metric = {"state": "", "cpu": 0, "heap": 0, "thread_active": 0, "thread_blocked": 0}

            # get jeus managed server state
            ms_state_stdout = self.exec_cmd(cmd="'server-info -server " + ms +" -state'")
            value_from_stdout = ms_state_stdout.splitlines()[-2]
            if re.match(r'SHUTDOWN', value_from_stdout) is not None:
                state = 0
            elif re.match(r'RUNNING', value_from_stdout) is not None:
                state = 1
            elif re.match(r'STANDBY', value_from_stdout) is not None:
                state = 2
            elif re.match(r'FAILED', value_from_stdout) is not None:
                state = 3
            else:
                # for other states
                state = 5
            metric["state"] = state

            # get cpu, memory usage from filtered row
            cpu_usage_stdout = self.exec_cmd(cmd="'system-info --cpu " + ms + "'")
            for row in cpu_usage_stdout.splitlines():
                # rows are split into 4 values on jeus 7
                split_row = row.split('|')
                if len(split_row) == 4 and split_row[1].strip() == "CPU Idle Percent":
                    metric["cpu"] = round(100-float(split_row[2].split()[0].strip()), 1)
            memory_usage_stdout = self.exec_cmd(cmd="'system-info --memory " + ms + "'")
            for row in memory_usage_stdout.splitlines():
                # rows are split into 4 values on jeus 7
                split_row = row.split('|')
                if len(split_row) == 4 and split_row[1].strip() == "Current Used Heap Memory Ratio":
                    metric["heap"] = round(100-float(split_row[2].split()[0].strip()), 1)

            # get thread status from filtered row
            thread_status_stdout = self.exec_cmd(cmd="'thread-info -server " + ms + " -li " + self.jeus_listener_name + " -os'").splitlines()
            for row in thread_status_stdout:
                # rows are split into 8 values on jeus 7
                split_row = row.split('|')
                if len(split_row) == 8 and split_row[1].strip() == "The number of threads.":
                    metric["thread_active"] += int(split_row[3])
                    metric["thread_blocked"] += int(split_row[5])

            self.gauge_state.labels(jeus_ms=ms).set(metric["state"])
            self.gauge_cpu.labels(jeus_ms=ms).set(metric["cpu"])
            self.gauge_heap.labels(jeus_ms=ms).set(metric["heap"])
            self.gauge_thread_active.labels(jeus_ms=ms).set(metric["thread_active"])
            self.gauge_thread_blocked.labels( jeus_ms=ms).set(metric["thread_blocked"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", help="Configuration File Path")
    parser.add_argument("--web_listen_port", help="TCP Port to listen on", type=int)
    args = parser.parse_args()
    config_file = args.config_file if args.config_file is not None else "jeus_exporter.yaml"
    listen_port = args.web_listen_port if args.web_listen_port is not None else 9102

    try:
        with open(config_file, 'r') as f:
            conf = yaml.safe_load(f)
    except Exception as e:
        sys.exit(e)

    jeuscon = JeusadminConnector(jeus_base_dir=conf["jeus_base_dir"], jeus_ms_name=conf["jeus_ms_name"], jeus_admin_socket=conf["jeus_admin_socket"],
                                 jeus_credential_path=conf["jeus_credential_path"], jeus_listener_name=conf["jeus_listener_name"])
    xptr = JeusExporter(jeuscon, listen_port)

    while True:
        xptr.get_metric()
        sleep(3)

import os
import sys

from ttgateway import utils
from ttgateway.config import config


def daemon():
    daemon_commands = ("start", "stop", "restart")
    if len(sys.argv) <= 1 or sys.argv[1] not in daemon_commands:
        cmd = os.path.basename(sys.argv[0])
        print("Usage: {} ({})".format(cmd, "|".join(daemon_commands)))
        sys.exit(0)

    utils.config_logger()
    utils.set_threading_exception_handler()

    from ttgateway.daemon import Daemon
    from ttgateway.server import Server
    server = Server()
    app = Daemon("ttgw", config.DAEMON_PID_FILE, server.run,
        server.clean_exit)
    if sys.argv[1] == "start":
        app.start()
    elif sys.argv[1] == "stop":
        app.stop()
    elif sys.argv[1] == "restart":
        app.restart()


def cli():
    from ttgateway.cli_client import CLIClient
    import cmd2
    import json
    app = CLIClient(persistent_history_file=f"{config.TT_DIR}/.gw_history")
    if len(sys.argv) > 1:
        try:
            app.onecmd(" ".join(sys.argv[1:]))
        except (cmd2.exceptions.Cmd2ArgparseError, json.JSONDecodeError):
            pass
    else:
        app.cmdloop()


def remote_cli():
    from ttgateway.remote_cli_client import RemoteCliClient
    app = RemoteCliClient(
        persistent_history_file=f"{config.TT_DIR}/.gw_history")
    rsp = app.select_device()
    if rsp is not None:
        app.cmdloop()


def diagnosis():
    from ttgateway.diagnosis import Diagnosis
    diagnoser = Diagnosis()
    diagnoser.run()

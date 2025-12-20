import os
import sys
import time
import fcntl
import signal
import logging


logger = logging.getLogger(__name__)
EXIT_TIMEOUT = 60


class Daemon:
    """ Deamon is responsible for managing the Unix daemon process, including
    starting, stopping, and restarting the daemon. It is the main gateway
    process. It receives and processes any events sent by the gateway
    microcontroller. It is also in charge of forwarding the snesor data through
    the different interfaces.
    """
    def __init__(self, name, pid_file, run, exit_cb=None):
        """ Initializes a Daemon instance with the given parameters.

        :param name: The name of the daemon.
        :type name: str

        :param pid_file: The path to the PID file.
        :type pid_file: str

        :param run: The function to execute as the main task of the daemon.
        :type run: Callable

        :param exit_cb: An optional callback to execute upon daemon exit.
        :type exit_cb: Callable or None
        """
        self.name = name
        self.pid_file = pid_file
        self.pid_fd = None
        self.run = run
        self.exit = exit_cb

    def demonize(self):
        """ Daemonizes the process: forks, detaches from the terminal, and
        redirects I/O to /dev/null. This method performs the necessary steps to
        run the process in the background as a daemon.
        """
        if os.fork() != 0:
            sys.exit(0) # Parent exists
        os.setsid() # Change to new session
        if os.fork() != 0:
            sys.exit(0) # Parent exists again

        os.umask(0o022) # Reset umask
        os.chdir("/") # Change to root directory

        # Redirect stdin, stdout and sterr to /dev/null
        os.close(sys.stdin.fileno())
        os.close(sys.stdout.fileno())
        os.close(sys.stderr.fileno())
        fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(fd, sys.stdout.fileno())
        os.dup2(fd, sys.stderr.fileno())

        pid = self.create_pid_file()
        logger.info(f"Daemon running with PID {pid}")

    def exit_callback(self, signum, _):
        """ Callback function to handle termination signals. Executes the exit
        callback and deletes the PID file.

        :param signum: The signal number.
        :type signum: integer
        :param _: The signal stack frame (unused).
        """
        logger.debug("Exit callback")
        self.exit()
        self.delete_pid_file()

    def create_pid_file(self) -> int:
        """ Creates and locks the PID file, and writes the current process ID to
        it.

        :return: The PID of the daemon.
        :rtype: integer
        """
        self.pid_fd = os.open(self.pid_file, os.O_RDWR|os.O_CREAT, 0o664)
        fcntl.lockf(self.pid_fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        pid = os.getpid()
        os.write(self.pid_fd, f"{pid}\n".encode())
        return pid

    def delete_pid_file(self):
        """ Unlocks and removes the PID file, if it exists.
        """
        fcntl.lockf(self.pid_fd, fcntl.LOCK_UN)
        os.close(self.pid_fd)
        os.remove(self.pid_file)

    def start(self):
        """ Starts the daemon process. Checks if the daemon is already running
        by examining the PID file. If not running, it proceeds to daemonize the
        process, set up signal handling, and execute the main task.
        """
        try:
            self.pid_fd = os.open(self.pid_file, os.O_RDWR|os.O_CREAT)
            fcntl.lockf(self.pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(self.pid_fd, fcntl.LOCK_UN)
            os.close(self.pid_fd)
        except BlockingIOError:
            print(f"PID file '{self.pid_file}' exists and it's locked.")
            print(f"Is {self.name} daemon already running?")
            sys.exit(1)

        self.demonize()
        signal.signal(signal.SIGTERM, self.exit_callback)
        try:
            self.run()
        except SystemExit:
            logger.exception("Daemon system exit exception")
        except:
            logger.exception("Deamon run exception")
            raise
        finally:
            logger.info("Daemon stopped")
            self.exit_callback(15, 0)

    def stop(self, restart=False):
        """ Stops the daemon process by sending a termination signal to the
        process ID found in the PID file. Waits for the process to exit, and
        forcefully kills it if it takes too long to stop.

        :param restart: Whether to restart the daemon after stopping it.
            Defaults to False.
        :type restart: bool
        """
        try:
            with open(self.pid_file) as f:
                pid = int(f.read())
        except FileNotFoundError:
            print(f"PID file '{self.pid_file}' doesn't exists.")
            print(f"{self.name} daemon is not running.")
            if restart:
                print("Starting...")
                return
            sys.exit(1)
        try:
            # Try to terminate process gracefully
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print("Process does not exist")

        print("Wait for proccess exit")
        count = 0
        while True:
            try:
                os.kill(pid, 0)
                count += 1
                #TODO timeout
            except OSError:
                break

            if count > EXIT_TIMEOUT:
                print("Process taking too long to exit, killing it")
                os.kill(pid, signal.SIGKILL)

            time.sleep(1)

        print("Process exited")

    def restart(self):
        """ Restarts the daemon by stopping it and then starting it again.
        """
        self.stop(restart=True)
        time.sleep(0.1)
        self.start()

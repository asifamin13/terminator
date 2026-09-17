"""
NAME
    remote.py - A Terminator plugin adding ssh and docker/podman features to
    the context menu

DESCRIPTION
    This plugin looks for a child remote session inside a terminal using the
    psutil API and adds context-menu mechanisms to:

      * Clone the current SSH/container session into a newly spawned terminal
        (horizontally or vertically). By default the CWD is inferred by
        regex-matching the PS1 in the scrollback.
      * Clone into a highlighted path: if a file path is selected before right
        clicking, "Clone Horizontally/Vertically into /the/path" items appear
        that `cd` directly into the highlighted path, no PS1/pwd detection.
      * Use pwd for CWD: a menu toggle that sends `pwd` to the remote shell to
        determine the working directory instead of regex-matching the PS1. The
        remote shell must be idle; uncheck it while a command is running.
      * SSH to Host: a submenu listing hosts from ~/.ssh/config (skipping
        wildcard patterns, honoring `Include` directives) that sends
        `ssh <host>` to the terminal. If a host has a `command` configured (see
        below) it is sent after connecting, whether the host is selected from
        the menu or typed manually.
      * Attach to Container: a submenu of running containers (via the
        Docker/Podman API) that sends `<container_command> exec -it <name>
        <container_shell>` to the terminal. Only shown when the API is
        available.
      * Apply a terminator profile based on the remote host or container name.

    Cloning sessions inspired from https://github.com/ilgarm/terminator_plugins
      * Not maintained anymore

    Host profile matching inspired from https://github.com/GratefulTony/TerminatorHostWatch
      * This finds hosts by parsing the PS1 using a regex

DOCKER/PODMAN API INTEGRATION
    The plugin talks to the Docker/Podman API directly over its unix socket
    using only the Python standard library -- no `docker` SDK or extra
    dependencies required. The API is used for two things:

      1. listing running containers for the Attach to Container submenu
         (GET /containers/json)
      2. guessing the container name after a manual `docker run` that
         omitted `--name` (picks the most recently created running
         container)

    API sockets are tried in order:
      1. `socket_path` config option (if set)
      2. `DOCKER_HOST` environment variable (if set)
      3. Rootless Podman: unix:///run/user/{uid}/podman/podman.sock
      4. Docker: unix:///var/run/docker.sock
      5. System Podman: unix:///run/podman/podman.sock

    If no socket is available, the plugin falls back to the existing
    psutil-based cmdline parsing -- no functionality is lost.
    Podman users enable the socket with: systemctl --user start podman.socket

PASSWORD AUTO-ENTRY
    When ssh sits on a password prompt, the plugin looks the secret up and
    types it in. The lookup user/host are taken from the prompt itself
    ("user@host's password:"), so hosts behind a ProxyJump work: each hop
    names itself and gets its own lookup. Prompt hostnames are mapped back
    to ssh config aliases via `ssh -G` (using the configured ssh_command),
    so config sections and lookups stay keyed by the alias. Fallbacks (key
    passphrases, bare "Password:" prompts) resolve user/host through
    `ssh -G` and the ssh cmdline. The default lookup command is:

      secret-tool lookup service ssh host {host} user {user}

    Store each password once in the standard libsecret keyring with:

      secret-tool store --label='ssh foo' service ssh host foo user $USER

    For a ProxyJump chain, store one entry per hop (e.g. both the bastion
    and the target host). If secret-tool is missing or nothing is stored,
    the lookup simply fails and ssh behaves normally — you type the
    password yourself. A different lookup command can be set globally via
    `ssh_password_command` or per host via `password_command` (the per-host
    value replaces the global one entirely; a host without one falls back
    to the global). Both accept the same two forms:

      * a full shell command with {host}/{user} placeholders, e.g.
        `secret-tool lookup service ssh host {host} user {user}`
      * a '<manager>:<path>' shorthand executed as an argv list (no shell),
        e.g. `pass:ssh/{host}` runs `pass ssh/<host>` — set it globally to
        use the same password store for every host without a per-host
        `password_command`, or per host for a specific entry path

    Registered shorthands:

      * pass:<path>  runs `pass <path>` (e.g. `pass:ssh/{host}`)
      * rbw:<name>   runs `rbw get <name>` — Bitwarden via rbw, whose
        agent keeps the vault unlocked (e.g. `rbw:ssh-{host}`)
      * bw:<name>    runs `bw get password <name> --nointeraction` —
        Bitwarden's official CLI; Terminator must be started with
        BW_SESSION exported (from `bw unlock`), otherwise lookups fail

    The lookup has no tty and times out after `ssh_password_timeout`
    seconds (15), so the manager must already be unlocked (or unlock via a
    graphical pinentry within that time) and print only the password.

    Shorthand support details: placeholders like {host}/{user} work in
    shorthands too, the set of managers is a small registry
    (PASSWORD_MANAGER_SHORTHANDS) — add an entry to support another
    password manager — and values that don't start with a registered
    prefix keep working as full shell commands.

    Guard rails: prompts containing 'sudo' never match; auto-entry only
    runs within ~60s of the ssh process starting (so later in-session
    prompts like `passwd` never get the secret); and at most
    `ssh_password_max_attempts` attempts are made per ssh process.

INSTALLATION
    Put this file in ~/.config/terminator/plugins/
    Start Terminator and enable Remote in
    Right Click -> Preferences -> Plugins

CONFIGURATION
    Plugin section in ~/.config/terminator/config:
    [plugins]
      [[Remote]]

    Configuration keys:
      * auto_clone: Clone automatically when you split a remote session,
        via keybind (split_horizontal etc.) or context menu (False)
      * infer_cwd: When cloned, parse CWD from PS1 and `cd` into it (True)
      * use_pwd: When set (via menu toggle), send `pwd` to the remote shell to
        determine CWD instead of regex-matching the PS1 (False)
      * ssh_command: SSH executable to use ("ssh"); also used for
        `ssh -G` host/user resolution in the password auto-entry feature
      * container_command: Container runtime executable to use ("docker")
      * container_shell: Shell used when cloning into a container ("sh")
      * ssh_config: Path to SSH config file, supports ~ expansion ("~/.ssh/config")
      * cd_delay: Delay in seconds before sending cd after clone (0.25)
      * ssh_default_profile: optional profile for all SSH sessions
      * container_default_profile: optional profile for all container sessions
      * socket_path: Optional Docker/Podman API socket path (default: auto-detect)
      * ssh_password_command: command run to fetch the SSH password when ssh
        prompts for one; {host} and {user} are placeholders (default uses
        secret-tool, see PASSWORD AUTO-ENTRY below). May also be a
        '<manager>:<path>' shorthand like 'pass:ssh/{host}' or
        'rbw:ssh-{host}' (same forms as
        the per-host password_command). Set to "" to disable
      * ssh_password_max_attempts: max auto-entry attempts per ssh process (3)
      * ssh_password_timeout: seconds to wait for the password command before
        giving up and leaving the prompt for manual typing (15)

    Host section:
      You can add host sections (the host name from SSH config or the container
      name) with a 'profile' key which overrides the defaults, and optionally a
      'command' sent after connecting. Per-host keys:
      * profile: terminator profile to apply for this host
      * command: command sent to the remote shell after connecting
      * command_delay: seconds to wait before sending the command (1.0)
      * command_before_cd: send the command before cd (True); False cd's first
      * password_command: overrides ssh_password_command for this host; may be
        a '<manager>:<path>' shorthand (e.g. 'pass:ssh/sp-0', run without a
        shell) or a shell command with {host}/{user} placeholders

    ex)

    [plugins]
      [[Remote]]
        ssh_default_profile = common_ssh_profile
        container_default_profile = common_docker_profile
        auto_clone = False
        infer_cwd = True
        container_shell = sh
        cd_delay = 0.25
        ssh_config = ~/.ssh/config
        [[[foo]]]
          profile = foo_profile
        [[[sp-0]]]
          profile = sp_profile
          command = source ~/users/amin/bashrc
          command_delay = 1.0
          command_before_cd = True

DEBUGGING
    To debug, start Terminator from another terminal emulator like so:

    $ terminator -d --debug-classes Remote,SSHSession,ContainerSession,RemoteProcWatch,DockerAPI -u

DEVELOPMENT
    Support for future types of "Remote Sessions" can be easily added by
    subclassing `RemoteSession` and appending an instance to `Remote.remote_session_types`

AUTHORS
    The plugin was developed by Asif Amin <asifamin@utexas.edu>
"""

import os
import time
import glob
import getopt
import argparse
import re
import json
import shlex
import socket
import subprocess
import http.client
import psutil
import asyncio
import threading
from typing import Any, Dict, Optional, List, Set, Tuple, Union

import gi
from gi.repository import Gtk, GLib, Gdk  # type: ignore
gi.require_version('Vte', '2.91')
from gi.repository import Vte  # type: ignore

from terminatorlib.plugin import MenuItem
from terminatorlib.config import Config
from terminatorlib.terminator import Terminator
from terminatorlib.util import err, dbg
from terminatorlib.translation import _

from terminatorlib.version import APP_NAME, APP_VERSION

AVAILABLE = ['Remote']

CD_CMD = "cd -- {cwd} 2>/dev/null"

# Matches an SSH password/passphrase prompt at the end of the current
# terminal line, e.g.:
#   amin@foo's password:
#   Enter passphrase for key '/home/amin/.ssh/id_ed25519':
PASSWORD_PROMPT_RE = re.compile(
    r'(?i)(?:password|passphrase)(?:\s+for\s+[^:]{0,128})?:\s*$'
)

# Matches OpenSSH's "user@host's password:" prompt, capturing the user and
# host actually being authenticated. Behind a ProxyJump/bastion each hop
# prints its own prompt naming itself, so this is more accurate than
# deriving the host from the ssh cmdline (which is always the final target).
SSH_PASSWORD_PROMPT_RE = re.compile(
    r"(?i)(\S{1,128})@(\S{1,128}?)'s password:\s*$"
)

# Auto-entry is only attempted within this many seconds of the ssh process
# starting. Password/passphrase prompts always appear during connection
# setup; the window keeps us from typing the ssh secret into unrelated
# in-session prompts much later (e.g. `passwd` asking for the current
# password). Prompts containing 'sudo' are additionally excluded by regex.
SSH_PASSWORD_WINDOW = 60.0

# Default for `ssh_password_timeout`: how long to wait for a password
# lookup command to finish. Generous enough for slow CLIs (the standalone
# Bitwarden `bw` binary takes ~5s per lookup) and a cold pinentry prompt;
# a late result is safe (stale-password guard) — it just means manual typing.
PASSWORD_FETCH_TIMEOUT = 15.0

# Delayed host commands (command_delay) must not be typed while ssh is
# sitting on a password prompt: the tty is in no-echo mode, so the text
# would be swallowed and submitted AS the password. When a prompt is on
# the cursor row the send is re-checked every
# PASSWORD_COMMAND_RETRY_INTERVAL ms, at most PASSWORD_COMMAND_MAX_RETRIES
# times (~60s, matching SSH_PASSWORD_WINDOW), before giving up.
PASSWORD_COMMAND_RETRY_INTERVAL = 500
PASSWORD_COMMAND_MAX_RETRIES = 120

# Structured shorthands for `password_command` / `ssh_password_command`:
# a value of the form '<prefix>:<path>' is executed as an argv list (no
# shell) instead of a shell command line. Extend this dict to support
# other password managers, e.g.:
#   'keepassxc-cli': lambda db_and_entry: [...]
PASSWORD_MANAGER_SHORTHANDS = {
    'pass': lambda path: ['pass', path],
    # Bitwarden via rbw (unofficial client with a background agent that
    # keeps the vault unlocked between lookups)
    'rbw': lambda name: ['rbw', 'get', name],
    # Bitwarden via the official CLI; needs BW_SESSION in Terminator's
    # environment. --nointeraction makes a locked vault fail fast instead
    # of waiting on a master password prompt nobody can answer
    'bw': lambda name: ['bw', 'get', 'password', name, '--nointeraction'],
}

# Cache VTE version check at module load instead of per-call
_VTE_VERSION = "{}.{}".format(
    Vte.get_major_version(), 
    Vte.get_minor_version()
)

def vte_get_text(vte_term, start_row, start_col, end_row, end_col):
    """ wrapper for get_text_range* based on Vte version """
    if _VTE_VERSION < "0.72":
        return vte_term.get_text_range(
            start_row=start_row,
            start_col=start_col,
            end_row=end_row,
            end_col=end_col, 
            is_selected=None, 
        )[0]
    return vte_term.get_text_range_format(
        format=Vte.Format.TEXT,
        start_row=start_row,
        start_col=start_col,
        end_row=end_row,
        end_col=end_col
    )[0]

class UnixHTTPConnection(http.client.HTTPConnection):
    """ http.client connection over a unix domain socket """
    def __init__(self, socket_path, timeout=2):
        super().__init__('localhost', timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


class DockerAPI(object):
    """
    Minimal Docker/Podman REST API client over a unix socket using only
    the standard library — no docker SDK dependency. Works with both
    Docker and Podman (Podman exposes a Docker-compatible API socket).
    Falls back gracefully when no API socket is accessible.
    """
    _instance: Optional['DockerAPI'] = None

    @classmethod
    def get_instance(cls) -> 'DockerAPI':
        """Get the singleton DockerAPI instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._socket: Optional[str] = None  # path of the working socket
        self._tried_connect = False
        self.socket_path: Optional[str] = None

    def _candidate_sockets(self, configured: Optional[str]) -> List[str]:
        """ ordered list of socket paths to try """
        uid = os.getuid()
        candidates = []

        # If a specific socket path is configured, try it first
        if configured:
            expanded = os.path.expanduser(configured)
            if expanded.startswith('unix://'):
                expanded = expanded[len('unix://'):]
            candidates.append(expanded)

        # Respect DOCKER_HOST env var if set (unix sockets only)
        docker_host = os.environ.get('DOCKER_HOST', '')
        if docker_host.startswith('unix://'):
            candidates.append(docker_host[len('unix://'):])
        elif docker_host:
            dbg(f"DOCKER_HOST '{docker_host}' is not a unix socket, skipping")

        # Rootless Podman (most common for personal workstations)
        candidates.append(f"/run/user/{uid}/podman/podman.sock")

        # Docker socket
        candidates.append("/var/run/docker.sock")

        # System Podman socket
        candidates.append("/run/podman/podman.sock")

        return candidates

    def _request(self, path: str) -> Optional[Tuple[int, bytes]]:
        """ GET `path` from the API socket, return (status, body) or None """
        if not self._socket:
            return None
        conn = UnixHTTPConnection(self._socket)
        try:
            conn.request('GET', path)
            resp = conn.getresponse()
            return resp.status, resp.read()
        except Exception as e:
            dbg(f"API request {path} failed: {e}")
            return None
        finally:
            conn.close()

    def _get_json(self, path: str) -> Optional[Any]:
        """ GET `path` and parse the JSON body, or None on any failure """
        ret = self._request(path)
        if not ret:
            return None
        status, body = ret
        if status != 200:
            dbg(f"API request {path} returned status {status}")
            return None
        try:
            return json.loads(body)
        except ValueError as e:
            dbg(f"bad JSON from {path}: {e}")
            return None

    def _connect(self) -> Optional['DockerAPI']:
        """
        Find a working Docker/Podman API socket.
        Returns self when an API is available, else None (so callers can
        keep the `if not api._connect()` guard pattern).
        """
        if self._tried_connect:
            return self if self._socket else None
        self._tried_connect = True

        for sock_path in self._candidate_sockets(self.socket_path):
            # check file existence first to avoid connection timeouts
            if not os.path.exists(sock_path):
                dbg(f"Socket file does not exist: {sock_path}")
                continue
            self._socket = sock_path
            ret = self._request('/_ping')
            if ret and ret[0] == 200:
                dbg(f"Connected to container API at {sock_path}")
                return self
            self._socket = None

        dbg("No container API socket available")
        return None

    def list_containers(self) -> List[Dict[str, Any]]:
        """
        List running containers via GET /containers/json.
        Returns list of dicts with 'name', 'image', 'created' keys
        ('created' is a unix timestamp int, suitable for sorting).
        """
        data = self._get_json('/containers/json')
        if data is None:
            return []
        containers = []
        for c in data:
            names = c.get('Names') or []
            name = names[0].lstrip('/') if names else c.get('Id', '')[:12]
            containers.append({
                'name': name,
                'image': c.get('Image', ''),
                'created': c.get('Created', 0),
            })
        return containers

    def get_container_info(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Inspect a container via GET /containers/{name}/json.
        Returns dict with 'name', 'working_dir' keys, or None if not found.
        """
        attrs = self._get_json(f'/containers/{name_or_id}/json')
        if attrs is None:
            return None
        info = {
            'name': attrs.get('Name', '').lstrip('/'),
            'working_dir': attrs.get('Config', {}).get('WorkingDir', ''),
        }
        dbg(f"Got container info via API: {info}")
        return info


class RemoteSession(object):
    """
    API representing a 'Remote Session'
    """
    def __init__(self, exe: str) -> None:
        """
        constructor, exe acts like our type
        """
        self.exe = exe

    def IsType(self, proc: psutil.Process) -> bool:
        """ check if psutil.Process matches this type of remote session """
        raise NotImplementedError()

    def GetHost(self, proc: psutil.Process) -> Optional[str]:
        """ get remote host target """
        raise NotImplementedError()

    def Clone(self, proc: psutil.Process) -> List[str]:
        """ get the command to clone session """
        raise NotImplementedError()

    def matches_by_name(self, proc: psutil.Process) -> bool:
        """
        generic check if proc matches self.exe
        https://psutil.readthedocs.io/en/latest/#find-process-by-name
        """
        if self.exe == proc.name():
            return True
        if proc.exe():
            if self.exe == os.path.basename(proc.exe()):
                return True
        if proc.cmdline():
            if self.exe == proc.cmdline()[0]:
                return True
        return False

class SSHSession(RemoteSession):
    """ SSH sessions """
    # executables that spawn ssh as a non-interactive transport
    _transport_parents = {
        'rsync', 'scp', 'sftp', 'sftp-server', 'rsync-ssl',
        'git-remote-ssh', 'git-lfs', 'svn', 'unison'
    }
    # https://github.com/openssh/openssh-portable/blob/99a2df5e1994cdcb44ba2187b5f34d0e9190be91/ssh.c#L713
    # while ((opt = getopt(ac, av, "1246ab:c:e:fgi:kl:m:no:p:qstvx"
    #     "AB:CD:E:F:GI:J:KL:MNO:P:Q:R:S:TVw:W:XYy")) != -1) { /* HUZdhjruz */
    _ssh_short_opts = (
        "1246ab:c:e:fgi:kl:m:no:p:qstvx"
        "AB:CD:E:F:GI:J:KL:MNO:P:Q:R:S:TVw:W:XYy"
    )

    def __init__(self, exe='ssh'):
        """ constructor """
        RemoteSession.__init__(self, exe)

    def _parse_ssh_args(
        self, proc: psutil.Process
    ) -> Tuple[Optional[List[Tuple[str, str]]], Optional[List[str]]]:
        """
        Parse ssh cmdline into (opts, args) using getopt.
        Returns (opts, args) or (None, None) on error.
        opts is a list of (option, value) tuples; args is the list of
        positional arguments (host, optional remote command, ...).
        """
        try:
            ssh_args = proc.cmdline()[1:]
            opts, args = getopt.getopt(ssh_args, self._ssh_short_opts)
            return opts, args
        except psutil.NoSuchProcess:
            dbg("proc has gone away")
        except Exception as e:
            dbg(f"caught error parsing ssh args: {e}")
        return None, None

    def IsType(self, proc: psutil.Process) -> bool:
        """ check if this is an interactive ssh session """
        if not self.matches_by_name(proc):
            return False
        return not self._is_transport_ssh(proc)

    def _is_transport_ssh(self, proc: psutil.Process) -> bool:
        """
        Detect non-interactive ssh processes used as transport by
        rsync/scp/sftp/etc. so we don't treat them as interactive sessions.

        Signals that this ssh is transport (not a session to track):
          * parent process is a known file-transfer tool, OR
          * ssh was given a remote command (positional args after the host)
            without a -t/--force-tty flag
        """
        try:
            # Parent process check — rsync/scp/sftp all spawn ssh as a hild
            parent = proc.parent()
            if parent is not None:
                pname = parent.name()
                if pname in self._transport_parents:
                    dbg(f"ssh proc {proc.pid} has transport parent '{pname}', skipping")
                    return True

            # Remote-command check: parse the ssh cmdline.
            # If there are positional args beyond the host AND no -t was requested,
            # this is a non-interactive one-shot (e.g. `ssh host "ls"`, rsync's
            # `ssh host rsync --server ...`).
            opts, args = self._parse_ssh_args(proc)
            if opts is None or args is None:
                # parse failed (proc gone or bad cmdline) — assume transport to
                # be safe and avoid injecting into something we can't understand
                return True
            has_tty = any(o == '-t' for o, _ in opts)
            if not has_tty and len(args) > 1:
                dbg(f"ssh proc {proc.pid} has remote command without -t, treating as transport")
                return True
            # -W host:port is direct stream forwarding — a non-interactive transport
            # used by git's ProxyCommand (e.g. `ssh -W [gitlab]:22 gw`). It forwards
            # stdio to a port and never allocates a PTY, so it is never a session.
            if any(o == '-W' for o, _ in opts):
                dbg(f"ssh proc {proc.pid} is using -W stream forwarding, treating as transport")
                return True
        except psutil.NoSuchProcess:
            dbg("proc has gone away during transport check")
            return True
        except Exception as e:
            dbg(f"error during transport check, assuming not transport: {e}")
            return False
        return False

    def GetHost(self, proc: psutil.Process) -> Optional[str]:
        """
        extract host from ssh command line
        """
        def extractHost(target: str) -> str:
            if '@' in target:
                return target.split('@')[1]
            return target

        opts, args = self._parse_ssh_args(proc)
        if args:
            return extractHost(args[0])
        return None

    def Clone(self, proc: psutil.Process) -> List[str]:
        """ ssh just needs to copy the cmdline """
        return proc.cmdline()

class ContainerSession(RemoteSession):
    """ container type sessions """
    def __init__(self, exe: str = 'docker') -> None:
        """ constructor """
        super().__init__(exe)
        # Pre-create ArgumentParser instances to avoid rebuilding on every call
        self._exec_parser = self._create_exec_parser()
        self._attach_parser = self._create_attach_parser()

    @staticmethod
    def _create_exec_parser() -> argparse.ArgumentParser:
        """ pre-create the exec argument parser """
        parser = argparse.ArgumentParser()
        parser.add_argument("container")
        parser.add_argument("command", nargs='?')
        parser.add_argument('-d', '--detach', action='store_true')
        parser.add_argument('--detach-keys')
        parser.add_argument('-e', '--env')
        parser.add_argument('--env-file')
        parser.add_argument('-i', '--interactive', action='store_true')
        parser.add_argument('-l', '--latest', action='store_true')
        parser.add_argument('--privileged')
        parser.add_argument('--preserve-fds')
        parser.add_argument('-t', '--tty', action='store_true')
        parser.add_argument('-u', '--user')
        parser.add_argument('-w', '--workdir')
        return parser

    @staticmethod
    def _create_attach_parser() -> argparse.ArgumentParser:
        """ pre-create the attach argument parser """
        parser = argparse.ArgumentParser()
        parser.add_argument("container")
        parser.add_argument('--detach-keys')
        parser.add_argument('-l', '--latest', action='store_true')
        parser.add_argument('--no-stdin', action='store_false')
        parser.add_argument('--sig-proxy', action='store_true')
        return parser

    def IsType(self, proc: psutil.Process) -> bool:
        """ check if this is a running docker session """
        if not self.matches_by_name(proc):
            return False
        # make sure this is an interactive run, exec, or attach
        return self._get_command(proc) != None

    def GetHost(self, proc: psutil.Process) -> Optional[str]:
        """ try to find container name from cmdline """
        # TODO: figure this out
        cmd = self._get_command(proc)
        if not cmd:
            return None
        try:
            if cmd == "run":
                return self._get_host_run(proc)
            elif cmd == "exec":
                return self._get_host_exec(proc)
            elif cmd == "attach":
                return self._get_host_attach(proc)
            err("unrecognized sub command?")
        except psutil.NoSuchProcess as e:
            dbg(f"proc has gone away: {e}")
        except Exception as e:
            err(f"caught exception {e}")
        return None

    def Clone(self, proc: psutil.Process, shell: Optional[str] = None) -> List[str]:  # type: ignore[override]
        """ get cmd to launch terminal into container session """
        if shell is None:
            shell = 'sh'
        cmd = self._get_command(proc)
        if not cmd:
            err("shouldnt happen?")
            return proc.cmdline()
        if cmd in ["exec" , "attach"]:
            return proc.cmdline()
        # this is a docker run
        host = self.GetHost(proc)
        if not host:
            # we dont have host info
            # just make new container
            return proc.cmdline()
        else:
            # we should exec a terminal session here
            clone_cmd = [self.exe, 'exec', '-it', host] + shell.split()
            return clone_cmd

    def _get_command(self, proc: psutil.Process) -> Optional[str]:
        """ get type of container command, we only support interactive ones """
        interactiveCmds = { 'run', 'exec', 'attach' }
        try:
            for arg in proc.cmdline():
                if arg in interactiveCmds:
                    return arg
        except psutil.NoSuchProcess as e:
            dbg(f"process has gone away: {e}")
        except Exception as e:
            err(f"unhandled exception: {e}")
        return None

    def _get_host_run(self, proc: psutil.Process) -> Optional[str]:
        """
        docker/podman run — try to find the container name.
        1. Check for --name in cmdline
        2. Fall back to Docker/Podman API — pick the most recently
           created running container
        """
        # Try --name flag first
        try:
            idxOfName = proc.cmdline().index("--name")
            name = proc.cmdline()[idxOfName + 1]
            dbg(f"parsed container name: {name}")
            return name
        except ValueError:
            pass  # --name not in cmdline
        except Exception as e:
            dbg(f"error looking for --name: {e}")

        # Fall back to Docker/Podman API — pick most recently created container
        api = DockerAPI.get_instance()
        if not api._connect():
            dbg("No API available to find run container name")
            return None

        try:
            candidates = [
                (c['name'], c['created']) for c in api.list_containers()
            ]
            if candidates:
                # Sort by creation time, pick the most recently created
                candidates.sort(key=lambda x: x[1], reverse=True)
                name = candidates[0][0]
                dbg(f"Selected most recently created container: '{name}'")
                return name

        except Exception as e:
            dbg(f"Error finding container via API: {e}")

        dbg("Could not determine container name for run command")
        return None

    def _get_host_exec(self, proc: psutil.Process) -> Optional[str]:
        """
        get container name from docker exec cmdline
        FORMAT: podman exec [options] CONTAINER [COMMAND [ARG...]]
        Options:
            -d, --detach               Run the exec session in detached mode (backgrounded)
                --detach-keys string   Select the key sequence for detaching a container. Format is a single character [a-Z] or ctrl-<value> where <value> is one of: a-z, @, ^, [, , or _ (default "ctrl-p,ctrl-q")
            -e, --env stringArray      Set environment variables
                --env-file strings     Read in a file of environment variables
            -i, --interactive          Keep STDIN open even if not attached
            -l, --latest               Act on the latest container podman is aware of
                                        Not supported with the "--remote" flag
                --preserve-fds uint    Pass N additional file descriptors to the container
                --privileged           Give the process extended Linux capabilities inside the container.  The default is false
            -t, --tty                  Allocate a pseudo-TTY. The default is false
            -u, --user string          Sets the username or UID used and optionally the groupname or GID for the specified command
            -w, --workdir string       Working directory inside the container
        """
        fullArgs = proc.cmdline()
        startIndex = fullArgs.index('exec') + 1
        args, unknown = self._exec_parser.parse_known_args(fullArgs[startIndex:])
        # dbg(f"got args: {args}, unknown: {unknown}")
        return args.container

    def _get_host_attach(self, proc: psutil.Process) -> Optional[str]:
        """
        get container name from docker attach
        FORMAT: podman attach [options] container
        OPTIONS
            --detach-keys=sequence
                Specify the key sequence for detaching a container. Format is a single character [a-Z] or one or more ctrl-<value> characters where <value> is one of: a-z, @, ^, [, , or _.
                Specifying "" disables this feature. The default is ctrl-p,ctrl-q.

                This option can also be set in containers.conf(5) file.

            --latest, -l
                Instead  of  providing  the  container  name or ID, use the last created container.  Note: the last started container can be from other users of Podman on the host machine.
                (This option is not available with the remote Podman client, including Mac and Windows (excluding WSL2) machines)

            --no-stdin
                Do not attach STDIN. The default is false.

            --sig-proxy
                Proxy received signals to the container process (non-TTY mode only). SIGCHLD, SIGSTOP, and SIGKILL are not proxied.

                The default is true.
        """
        fullArgs = proc.cmdline()
        startIndex = fullArgs.index('attach') + 1
        args, unknown = self._attach_parser.parse_known_args(fullArgs[startIndex:])
        # dbg(f"got args: {args}, unknown: {unknown}")
        return args.container

class RemoteProcWatch(object):
    """
    cache current remote sessions
    """
    def __init__(self, session_types: List[RemoteSession], poll_rate: float = 0.5) -> None:
        """ constructor """
        self.remote_session_types = session_types
        self.poll_rate = poll_rate
        # pid -> None or (psutil.Process, RemoteSession)
        self.watches: Dict[int, Optional[Tuple[psutil.Process, 'RemoteSession']]] = dict()
        # pid -> create_time (cached to avoid syscalls on UI thread)
        self.create_times: Dict[int, Optional[float]] = dict()
        self._lock = threading.Lock()

        self.quit = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None

    def _has_remote_session(
        self, pid: int
    ) -> Optional[Tuple[psutil.Process, 'RemoteSession']]:
        """ check if this PID has a direct child with remote session """
        # Try non-recursive first (cheap) — ssh/docker are typically direct children
        children = psutil.Process(pid).children(recursive=False)
        if not children:
            return None
        dbg(f"terminal PID {pid} has direct children: {children}!!")
        for child in children:
            with child.oneshot():
                for remote_session in self.remote_session_types:
                    if remote_session.IsType(child):
                        return (child, remote_session)
        # Fall back to recursive scan only if direct children had no match
        children = psutil.Process(pid).children(recursive=True)
        dbg(f"terminal PID {pid} has recursive children: {children}")
        for child in children:
            with child.oneshot():
                for remote_session in self.remote_session_types:
                    if remote_session.IsType(child):
                        return (child, remote_session)
        return None

    def Register(self, pid: int) -> None:
        """ watch PID for children """
        with self._lock:
            if pid in self.watches:
                return
            dbg(f"adding new pid {pid}")
            self.watches[pid] = None
            # cache create_time once to avoid repeated syscalls on the UI thread
            try:
                self.create_times[pid] = psutil.Process(pid).create_time()
            except psutil.NoSuchProcess:
                self.create_times[pid] = None
        self._ensure_thread()

    def _ensure_thread(self) -> None:
        """
        (re)start the poll thread if it isn't running.
        A threading.Thread object can only be started once, so if a
        previous poller exited (all watches were removed), build a
        fresh loop + thread instead of calling start() again.
        """
        if self.thread is not None and self.thread.is_alive():
            return
        self.quit = False
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._external_thread, daemon=True)
        self.thread.start()

    def GetPIDProcInfo(
        self, pid: int
    ) -> Optional[Tuple[psutil.Process, 'RemoteSession']]:
        """ get current remote proc info """
        with self._lock:
            if pid not in self.watches:
                return None
            return self.watches[pid]

    def GetCreateTime(self, pid: int) -> Optional[float]:
        """ get cached create_time for pid, avoiding syscall on UI thread """
        with self._lock:
            return self.create_times.get(pid)

    async def _poll(self) -> None:
        """ check psutil proc info """
        while not self.quit:
            with self._lock:
                pids = list(self.watches.keys())
            for procPid in pids:
                try:
                    # Skip expensive re-scan if previously found child is still alive
                    with self._lock:
                        prev = self.watches.get(procPid)
                    if prev is not None:
                        child_proc, _ = prev
                        if child_proc.is_running():
                            continue
                    ret = self._has_remote_session(procPid)
                    with self._lock:
                        self.watches[procPid] = ret
                except psutil.NoSuchProcess as e:
                    dbg(f"removing proc: {procPid}")
                    with self._lock:
                        self.watches.pop(procPid, None)
                        self.create_times.pop(procPid, None)
                except Exception as e:
                    dbg(f"caught generic exception: {e}")
            with self._lock:
                if len(self.watches) == 0:
                    dbg(f"no watches, leaving!")
                    self.quit = True
                    break
            await asyncio.sleep(self.poll_rate)

    async def _async_main(self) -> None:
        """ async stuff """
        loop = self.loop
        if loop is None:
            return
        task = loop.create_task(self._poll())
        await task

    def _external_thread(self) -> None:
        """ external event loop """
        loop = self.loop
        if loop is None:
            return
        loop.run_until_complete(self._async_main())
        loop.close()

class Remote(MenuItem):
    """
    Add remote commands to the terminal menu

    NOTE: Terminator can instantiate this plugin multiple times (e.g. each
    time the terminal context menu is built). All long-lived state is kept
    on the class so every instance shares one RemoteProcWatch poller, one
    GLib watch timer, and one terminal->profile tracking dict.
    """
    capabilities = ['terminal_menu']

    remote_session_types = [
        SSHSession(),
        ContainerSession('docker'),
        ContainerSession('podman')
    ]

    # ---- shared (class-level) state, singletons across plugin instances ----
    # global plugin config
    config: Optional[Dict[str, Any]] = None
    # single proc watch poller shared by all instances
    remote_proc_watch: Optional[RemoteProcWatch] = None
    # current terminals with a remote session found via polling
    currRemoteTerminals: Dict[Any, Any] = dict() # terminal -> last profile
    # terminals that have already received a host command (prevents double-sending
    # when the dropdown menu already scheduled one before the poller detects it)
    sent_host_commands: Set[Any] = set()
    # terminals with split signals connected for clone-on-split
    split_hooked: Set[Any] = set()
    # True while our own clone flow emits a split signal (its _poll_new_terminals
    # does the spawning — the split-signal handler must not also clone)
    split_suppress: bool = False
    # terminal -> {'pid', 'attempts', 'armed', 'row'} state for ssh password auto-entry
    password_states: Dict[Any, Dict[str, Any]] = {}
    # alias -> (hostname, user) resolved via `ssh -G`, cached
    ssh_g_cache: Dict[str, Optional[Tuple[str, str]]] = {}
    # ssh config path -> (mtime, sorted host aliases), cached
    ssh_config_cache: Dict[str, Tuple[float, List[str]]] = {}
    # single GLib watch timer shared by all instances
    watch_id: Optional[int] = None

    # I hate using regex, got this from ChatGPT 3.5
    # This should try to match a sane linux file path that can
    # have alphanumeric characters, ~, underscores, hyphens, and dots
    cwd_regex = re.compile(
        r'(\/(?:[\w.-]+\/)*[\w.-]+|\~(?:\/[\w.-]+)*)+(?:\.\w+)?'
    )

    def __init__(self) -> None:
        """ constructor """
        MenuItem.__init__(self)
        dbg("Remote instance created")

        # logged here rather than in the get_config classmethod: dbg() names
        # the class from the first argument, which is `type` for a classmethod
        dbg(f"read user config: "
            f"{Config().plugin_get_config(self.__class__.__name__)}")
        config = Remote._get_config()
        dbg(f"using config: {config}")

        self.terminator = Terminator()

        # current terminal instance data
        self.peers: Set[Any] = set()
        self.remote_proc: Optional[psutil.Process] = None
        self.remote_type: Optional[RemoteSession] = None
        self.remote_cwd: Optional[str] = None
        self.timeout_id: Optional[Union[bool, int]] = None

        # Proc watch poller — create exactly once
        Remote._get_proc_watch()

        # Watch timer + one-time API pre-connect — install exactly once
        if Remote.watch_id is None:
            Remote.watch_id = GLib.timeout_add(
                500,
                self._update_watches,
                None
            )

            # Pre-connect to Docker/Podman API at plugin load time
            # so the first right-click menu doesn't have a delay
            api = DockerAPI.get_instance()
            socket_path = config.get('socket_path', '')
            if socket_path:
                api.socket_path = socket_path
            api._connect()

    def _isNewlySpawned(self, pid: int) -> bool:
        create_time = Remote._get_proc_watch().GetCreateTime(pid)
        if create_time is None:
            return False
        return abs(time.time() - create_time) < 3

    def _update_watches(self, _data: Any = None) -> bool:
        """
        Watch for new terminals in background
        """
        proc_watch = Remote._get_proc_watch()
        if self._get_config()['auto_clone']:
            # keep a fresh snapshot so the split-signal handler can diff it
            # against the post-split terminals to find the new one. Don't
            # touch it while a clone poll (timeout_id) is diffing its own.
            if not self.timeout_id:
                self.peers = self._get_all_terminals()
        for terminal in (self.terminator.terminals or []):
            if self._get_config()['auto_clone'] and \
                    terminal not in Remote.split_hooked:
                # keybind AND context-menu splits both emit these signals;
                # connect once per terminal (RUN_LAST + connect_after means
                # our handler runs after the split has completed)
                for sig in ('split-auto', 'split-horiz', 'split-vert'):
                    terminal.connect_after(sig, self._on_split_signal, terminal)
                Remote.split_hooked.add(terminal)
            proc_watch.Register(terminal.pid)
            ret = proc_watch.GetPIDProcInfo(terminal.pid)
            if ret:
                child, remoteType = ret
                if isinstance(remoteType, SSHSession):
                    self._maybe_feed_password(terminal, remoteType, child)
                if terminal not in self.currRemoteTerminals:
                    dbg(f"poller: remote session first detected on "
                        f"terminal pid={terminal.pid}, "
                        f"type={type(remoteType).__name__}, "
                        f"proc pid={child.pid} ({child.name()})")
                    self._apply_host_settings(
                        terminal=terminal,
                        proc=child,
                        proc_type=remoteType
                    )
                    self._send_host_command(terminal, child, remoteType)
            else:
                Remote.password_states.pop(terminal, None)
                if terminal in self.currRemoteTerminals and not self._isNewlySpawned(terminal.pid):
                    dbg(f"restoring original profile: {self.currRemoteTerminals[terminal]}")
                    terminal.set_profile(None, profile=self.currRemoteTerminals[terminal])
                    self.currRemoteTerminals.pop(terminal)
                    Remote.sent_host_commands.discard(terminal)
        # drop hooks for terminals that have gone away
        Remote.split_hooked.intersection_update(self.terminator.terminals or [])
        return True

    def _on_split_signal(self, widget: Any, cwd: str, terminal: Any) -> None:
        """
        Clone the source terminal's remote session into the newly created
        terminal after a split. Fires for keybind splits (key_split_horiz /
        key_split_vert / key_split_auto) and context-menu splits alike —
        both emit the Terminal split signals. Runs after the default
        handler, so the new terminal already exists.
        """
        if not self._get_config()['auto_clone']:
            return
        if Remote.split_suppress:
            # our own Clone flow emitted this split to create the terminal;
            # its _poll_new_terminals is already spawning the session
            dbg("split signal from our own clone flow, not re-cloning")
            return
        # only clone when the SOURCE terminal actually has a remote session
        # (this fires for every split of every terminal, local shells too)
        ret = Remote._get_proc_watch().GetPIDProcInfo(terminal.pid)
        if not ret:
            dbg(f"split source terminal pid={terminal.pid} has no remote "
                f"session, not cloning")
            return
        self.remote_proc, self.remote_type = ret
        # find the new terminal. Prefer the split sibling: split_axis makes
        # the source terminal's parent a fresh Paned holding exactly source
        # + sibling. The peers diff is only a fallback, because split_axis
        # runs a nested main loop (Gtk.main_iteration_do) in which the
        # poller can refresh the snapshot BEFORE this handler diffs —
        # making the new terminal look "already known".
        newTerminal = None
        parent = terminal.get_parent()
        if parent is not None and hasattr(parent, 'get_child1'):
            for child in (parent.get_child1(), parent.get_child2()):
                if (child is not None and child is not terminal and
                        getattr(child, 'uuid', None) is not None):
                    newTerminal = self.terminator.find_terminal_by_uuid(
                        child.uuid.urn
                    )
                    dbg(f"split clone: found new terminal via sibling "
                        f"lookup pid={newTerminal.pid if newTerminal else '?'}")
                    break
        if newTerminal is None:
            currPeers = self._get_all_terminals()
            newPeers = [x for x in currPeers if x not in self.peers]
            self.peers = currPeers
            if len(newPeers) == 1:
                newTerminal = self.terminator.find_terminal_by_uuid(
                    newPeers[0].urn
                )
            else:
                err(f"split clone: expected 1 new terminal, "
                    f"found {len(newPeers)}")
                return
        if newTerminal is None:
            err("split clone: could not identify the new terminal")
            return
        # resolve the CWD to cd into. use_pwd takes precedence: type `pwd`
        # into the (idle) source session and parse the answer — the most
        # reliable value, since the signal's cwd and the PS1 regex can both
        # reflect the LOCAL shell instead of the remote session. Spawn the
        # clone from the callback once the answer arrives.
        if self._get_config()['use_pwd']:
            dbg(f"split clone: use_pwd set, probing source session "
                f"pid={terminal.pid} for CWD")
            self.remote_cwd = None
            self._get_cwd_via_pwd(
                terminal,
                lambda cwd: self._finish_split_clone(
                    newTerminal, cwd, terminal
                )
            )
            return
        self._set_split_clone_cwd(cwd, terminal)
        dbg(f"split clone: spawning remote session into new terminal "
            f"pid={newTerminal.pid}")
        self._spawn_remote_session(newTerminal)

    def _set_split_clone_cwd(self, signal_cwd: Optional[str], terminal: Any) -> None:
        """ pick the clone CWD: signal cwd first, then PS1 inference """
        if signal_cwd:
            self.remote_cwd = signal_cwd
        elif self._get_config()['infer_cwd']:
            self.remote_cwd = self._get_cwd_from_lines(terminal)
        else:
            self.remote_cwd = None

    def _finish_split_clone(
        self, newTerminal: Any, cwd: Optional[str], terminal: Any
    ) -> bool:
        """ continue a use_pwd split clone after the pwd answer arrives """
        if not cwd:
            dbg("split clone: pwd probe failed, falling back to "
                "signal cwd / PS1 inference")
            self._set_split_clone_cwd(None, terminal)
        else:
            dbg(f"split clone: got CWD via pwd: {cwd}")
            self.remote_cwd = cwd
        dbg(f"split clone: spawning remote session into new terminal "
            f"pid={newTerminal.pid}")
        self._spawn_remote_session(newTerminal)
        return False  # GLib idle callback, run once

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """ return configuration dict, ensure we have proper keys """
        config: Dict[str, Any] = {
            'ssh_default_profile': "",
            'container_default_profile': "",
            'auto_clone': "False",
            'infer_cwd': "True",
            'use_pwd': "False",
            'container_shell': "sh",
            'ssh_config': "~/.ssh/config",
            'cd_delay': "0.25",
            'ssh_command': "ssh",
            'container_command': "docker",
            'socket_path': "",
            'ssh_password_command':
                "secret-tool lookup service ssh host {host} user {user}",
            'ssh_password_max_attempts': "3",
            'ssh_password_timeout': str(PASSWORD_FETCH_TIMEOUT)
        }
        user_config = Config().plugin_get_config(cls.__name__)
        if user_config:
            config.update(user_config)

        def get_as_bool(cfg: Dict[str, Any], key: str) -> None:
            try:
                cfg[key] = str(cfg[key]).lower() == 'true'
            except Exception as e:
                err(f"problem parsing {key} as bool: {e}")
                cfg[key] = False

        get_as_bool(config, 'auto_clone')
        get_as_bool(config, 'infer_cwd')
        get_as_bool(config, 'use_pwd')
        return config

    @classmethod
    def _get_config(cls) -> Dict[str, Any]:
        """ return the shared config dict, loading it on first use """
        if cls.config is None:
            cls.config = cls.get_config()
        return cls.config

    @classmethod
    def _get_proc_watch(cls) -> RemoteProcWatch:
        """ return the shared proc watch poller, creating it on first use """
        if cls.remote_proc_watch is None:
            cls.remote_proc_watch = RemoteProcWatch(cls.remote_session_types)
        return cls.remote_proc_watch

    @classmethod
    def _get_host_config(cls, host: str) -> Dict[str, Any]:
        """
        return the per-host/container config section.
        Configobj may hand us a plain string instead of a section, so
        anything that isn't a dict is treated as "no host specific config".
        """
        entry = cls._get_config().get(host, {})
        return entry if isinstance(entry, dict) else {}

    def _get_cwd_from_lines(self, terminal, N=3):
        """
        get last N lines in terminal and try to infer the CWD
        by finding the last sane linux file path. This assumes there
        is a PS1 which outputs the working directory
        """
        vte = terminal.get_vte()
        currCol, currRow = vte.get_cursor_position()
        lines = vte_get_text(
            vte_term=vte,
            start_row=max(0, currRow - N),
            start_col=0,
            end_row=currRow,
            end_col=currCol
        )
        if lines:
            matches = list(self.cwd_regex.finditer(lines))
            if matches:
                lastMatch = matches[-1]
                dbg(f"Inferred remote cwd: {lastMatch.group()}")
                return lastMatch.group()
        dbg(f"cant find remote cwd in '{lines}'")
        return None

    def _get_cwd_via_pwd(self, terminal, callback):
        """
        Send 'pwd' to the terminal and parse the output to get the CWD.
        This is more reliable than regex-based detection but requires the
        shell to be idle. Calls callback(cwd_string_or_None) when done.
        """
        vte = terminal.get_vte()
        currCol, currRow = vte.get_cursor_position()

        # Send pwd command
        vte.feed_child(b'pwd\n')

        GLib.timeout_add(
            500, self._read_pwd_output, vte, currRow, currCol, callback
        )

    def _read_pwd_output(self, vte, currRow, currCol, callback) -> bool:
        """
        GLib timeout callback for _get_cwd_via_pwd: parse the `pwd` output
        printed since (currRow, currCol) and hand the CWD to callback.
        """
        newCol, newRow = vte.get_cursor_position()
        text = vte_get_text(
            vte_term=vte,
            start_row=currRow,
            start_col=currCol,
            end_row=newRow,
            end_col=newCol
        )
        cwd = None
        if text:
            dbg(f"pwd output text: '{text}'")
            for line in text.split('\n'):
                line = line.strip()
                # pwd outputs the absolute path followed by a newline
                # take the first non-empty line
                if line and line != 'pwd':
                    cwd = line
                    break
        if cwd:
            dbg(f"Got CWD via pwd: {cwd}")
        else:
            dbg(f"Could not parse pwd output from '{text}'")
        callback(cwd)
        return False  # run once

    def _get_selected_path(self, terminal):
        """
        Get the currently selected text from the terminal and check if it
        looks like a file path. Returns the path string or None.
        Uses the primary selection (highlight buffer), not the clipboard.
        When the user explicitly highlights text that starts with / or ~/,
        trust it verbatim rather than running it through the regex (which
        can mangle paths with underscores or other characters).
        """
        vte = terminal.get_vte()
        if not vte.get_has_selection():
            return None
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clipboard.wait_for_text()
        if not text:
            return None
        text = text.strip()
        # Trust user selection directly if it looks like an absolute or home path
        if text.startswith('/') or text.startswith('~/'):
            dbg(f"Using raw selection as path: {text}")
            return text
        # Fall back to regex for paths embedded in other text
        match = self.cwd_regex.search(text)
        if match:
            path = match.group()
            dbg(f"Found path in selection via regex: {path}")
            return path
        dbg(f"Selection does not look like a path: '{text}'")
        return None

    def _get_prompt_line(self, terminal: Any) -> Tuple[str, int]:
        """ get the cursor row's text up to the cursor, plus the row number """
        vte = terminal.get_vte()
        if vte is None:
            return ("", 0)
        col, row = vte.get_cursor_position()
        return (
            vte_get_text(
                vte_term=vte,
                start_row=row,
                start_col=0,
                end_row=row,
                end_col=col
            ) or "",
            row
        )

    def _get_ssh_user(
        self, remote_session: 'SSHSession', ssh_proc: psutil.Process
    ) -> Optional[str]:
        """ get the remote user from the ssh cmdline, if any """
        try:
            _, args = remote_session._parse_ssh_args(ssh_proc)
        except Exception as e:
            dbg(f"error parsing ssh cmdline for user: {e}")
            return None
        if args and '@' in args[0]:
            return args[0].split('@', 1)[0]
        return None

    def _maybe_feed_password(
        self,
        terminal: Any,
        remote_session: 'SSHSession',
        ssh_proc: psutil.Process
    ) -> None:
        """
        If ssh is sitting on a password/passphrase prompt, look the secret up
        with the configured command (secret-tool by default) and type it in.

        The user/host to look up come from the prompt itself
        ("user@host's password:") whenever available, so hosts behind a
        ProxyJump work: each hop names itself and gets its own lookup.
        Fallbacks (key passphrases, bare "Password:" prompts) use the
        target parsed from the ssh cmdline.

        Guard rails:
          * prompts containing 'sudo' never match
          * only active within SSH_PASSWORD_WINDOW seconds of the ssh
            process starting (excludes later prompts like `passwd`)
          * at most ssh_password_max_attempts typed attempts per prompt
            row, per ssh process
        """
        pid = ssh_proc.pid
        state = Remote.password_states.get(terminal)
        if state is None or state['pid'] != pid:
            # new ssh process -> fresh state
            dbg(f"password auto-entry: new ssh process pid={pid}, "
                f"resetting state")
            state = {'pid': pid, 'attempts': 0, 'armed': True, 'row': None}
            Remote.password_states[terminal] = state

        # give up after too many attempts (bad secret in the keyring, etc)
        try:
            max_attempts = int(self._get_config()['ssh_password_max_attempts'])
        except Exception:
            max_attempts = 3
        if state['attempts'] >= max_attempts:
            dbg(f"password auto-entry: giving up, "
                f"{state['attempts']}/{max_attempts} attempts used "
                f"for pid={pid}")
            return

        # only during connection setup, never deep into an established session
        try:
            age = time.time() - ssh_proc.create_time()
        except psutil.NoSuchProcess:
            dbg(f"password auto-entry: ssh pid={pid} exited")
            return
        if age > SSH_PASSWORD_WINDOW:
            # log this once per ssh process, not on every poll tick
            if not state.get('window_expired'):
                dbg(f"password auto-entry: ssh pid={pid} is {age:.0f}s old, "
                    f"past the {SSH_PASSWORD_WINDOW:.0f}s window; "
                    f"auto-entry disabled for this process")
                state['window_expired'] = True
            return

        line, row = self._get_prompt_line(terminal)
        target: Optional[Tuple[str, str]] = None
        m = SSH_PASSWORD_PROMPT_RE.search(line)
        if m:
            # the prompt names the host actually being authenticated
            target = (m.group(1), m.group(2))
        elif PASSWORD_PROMPT_RE.search(line) and 'sudo' not in line.lower():
            # passphrase / bare password prompt: the prompt doesn't name the
            # target, so fall back to the cmdline host and let `ssh -G`
            # resolve the effective username from the ssh config
            host = remote_session.GetHost(ssh_proc) or ''
            user = (
                self._get_ssh_user(remote_session, ssh_proc)
                or self._get_resolved_user(host)
                or ''
            )
            target = (user, host)
            dbg(f"password auto-entry: generic prompt on row {row}, "
                f"falling back to cmdline target '{user}@{host}'")

        if target is None:
            # no prompt on screen right now; re-arm for the next one
            if not state['armed'] or state['row'] is not None:
                dbg(f"password auto-entry: no prompt on screen "
                    f"(cursor row {row}), re-armed for the next one")
            state['armed'] = True
            state['row'] = None
            return
        if not state['armed'] and state['row'] == row:
            # already typed for this exact prompt (cursor still on its row);
            # a redraw/retry appears on a new row and re-arms
            return

        state['armed'] = False
        state['row'] = row
        state['attempts'] += 1
        user, host = target
        # prompts show the resolved Hostname (e.g. an IP); map it back to
        # the ssh config alias so per-host config and secret lookups match
        canon = host
        host = self._canonicalize_host(host)
        if host != canon:
            dbg(f"password auto-entry: canonicalized prompt host "
                f"'{canon}' -> '{host}' (attempt {state['attempts']})")
        # resolve the lookup command (per-host override wins)
        host_config = self._get_host_config(host) if host else {}
        template = host_config.get('password_command', '') or \
            self._get_config()['ssh_password_command']
        if template and host_config.get('password_command'):
            dbg(f"password auto-entry: using per-host password_command "
                f"for '{host}'")
        if not template:
            dbg(f"no password command configured for '{user}@{host}'")
            return

        dbg(f"password prompt detected for '{user}@{host}' on row {row}, "
            f"attempt {state['attempts']}/{max_attempts}, "
            f"fetching secret via '{template}'")
        self._fetch_and_feed_password(terminal, host, user, template)

    def _build_password_cmd(
        self, template: str, host: str, user: str
    ) -> Tuple[Optional[List[str]], Optional[str]]:
        """
        Turn a password_command template into either an argv list (for a
        '<manager>:<path>' shorthand, e.g. 'pass:ssh/sp-0') or a shell
        command line with {host}/{user} placeholders filled in.
        Returns (argv, shell_cmd) — exactly one is non-None.
        """
        for prefix, builder in PASSWORD_MANAGER_SHORTHANDS.items():
            marker = prefix + ':'
            if template.startswith(marker):
                path = template[len(marker):].format(host=host, user=user)
                dbg(f"password lookup: shorthand '{prefix}' with "
                    f"path '{path}' (argv, no shell)")
                return builder(path), None
        dbg(f"password lookup: shell command "
            f"'{template.format(host=host, user=user)}'")
        return None, template.format(host=host, user=user)

    def _fetch_and_feed_password(
        self, terminal: Any, host: str, user: str, template: str
    ) -> None:
        """
        Run the password lookup off the UI thread and type the result into
        the terminal when it arrives. The lookup may be a '<manager>:<path>'
        shorthand (executed without a shell) or a shell command line.
        """
        try:
            timeout = float(self._get_config()['ssh_password_timeout'])
        except Exception:
            timeout = PASSWORD_FETCH_TIMEOUT

        threading.Thread(
            target=self._password_lookup_worker,
            args=(terminal, host, user, template, timeout),
            daemon=True
        ).start()

    def _password_lookup_worker(
        self, terminal: Any, host: str, user: str, template: str,
        timeout: float
    ) -> None:
        """
        Background thread body for _fetch_and_feed_password. A method rather
        than a closure so dbg() attributes its output to Remote (and it
        survives --debug-classes Remote).
        """
        password = None
        t0 = time.time()
        dbg(f"password lookup: worker thread started for "
            f"'{user}@{host}' (timeout {timeout}s)")
        try:
            argv, shell_cmd = self._build_password_cmd(template, host, user)
            if argv is not None:
                result = subprocess.run(
                    argv, capture_output=True, text=True,
                    timeout=timeout
                )
            elif shell_cmd is not None:
                result = subprocess.run(
                    shell_cmd, shell=True, capture_output=True,
                    text=True, timeout=timeout
                )
            else:  # unreachable: exactly one of argv/shell_cmd is set
                raise RuntimeError("password command not resolved")
            elapsed = time.time() - t0
            if result.returncode == 0 and result.stdout:
                password = result.stdout.rstrip('\r\n')
                dbg(f"password lookup: got secret for "
                    f"'{user}@{host}' in {elapsed:.2f}s "
                    f"({len(password)} chars)")
            else:
                dbg(f"password command rc={result.returncode}, "
                    f"no secret (elapsed {elapsed:.2f}s, "
                    f"stderr: {result.stderr.strip()[:200] or 'none'})")
        except KeyError as e:
            err(f"unknown placeholder in password command: {e}")
        except Exception as e:
            dbg(f"password lookup failed after "
                f"{time.time() - t0:.2f}s: {e}")
        if password:
            GLib.idle_add(self._feed_password, terminal, password)
            dbg(f"password lookup: dispatched typing callback "
                f"to UI thread for '{user}@{host}'")
        else:
            dbg(f"no password found for '{user}@{host}', "
                f"manual typing required")

    def _feed_password(self, terminal: Any, password: str) -> bool:
        """ type the password + enter into the terminal (GLib idle callback) """
        # the fetch was async; the screen may have moved on since (user
        # pressed enter, auth already completed via buffered input, etc).
        # Only type if a prompt is still on the cursor row.
        line, row = self._get_prompt_line(terminal)
        if not PASSWORD_PROMPT_RE.search(line):
            state = Remote.password_states.get(terminal) or {}
            dbg(f"password prompt gone before typing, skipping stale "
                f"password (cursor row {row} now reads "
                f"'{line.strip()[:80] or '<empty>'}')")
            return False
        vte = terminal.get_vte()
        if vte is not None:
            dbg(f"typing password into terminal "
                f"({len(password)} chars + enter)")
            vte.feed_child((password + '\n').encode())
        return False  # run once

    def _parse_ssh_config(self) -> List[str]:
        """
        Parse the configured ssh_config and return a sorted list of host
        aliases (wildcard patterns and negations skipped). Follows Include
        directives. Tokenizes each line properly (inline comments, quoted
        arguments, `Host=name` form) and caches the result on the file's
        mtime. Only used to ENUMERATE aliases for the menu — all semantic
        resolution (hostname, user, proxy) goes through `ssh -G`.
        """
        path = os.path.expanduser(self._get_config()['ssh_config'])
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            dbg(f"SSH config file not found: {path}")
            return []
        cached = Remote.ssh_config_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]

        hosts: List[str] = []
        seen: Set[str] = set()
        self._parse_ssh_config_file(path, hosts, seen)
        hosts.sort()
        Remote.ssh_config_cache[path] = (mtime, hosts)
        return hosts

    def _parse_ssh_config_file(
        self, filepath: str, hosts: List[str], seen: Set[str]
    ) -> None:
        """ parse one ssh config file into the host alias list """
        try:
            with open(os.path.expanduser(filepath), 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        # handles inline comments and quoted arguments
                        tokens = shlex.split(line, comments=True)
                    except ValueError as e:
                        dbg(f"skipping malformed ssh config line: {e}")
                        continue
                    if not tokens:
                        continue
                    keyword = tokens[0].lower()
                    # support the `Host=name` / `Include=...` keyword=value form
                    if '=' in keyword:
                        key, _, arg = keyword.partition('=')
                        tokens = [key, arg] + tokens[1:]
                    if len(tokens) < 2:
                        continue
                    key = tokens[0].lower()
                    args = tokens[1:]
                    if key == 'host':
                        for h in args:
                            # skip wildcards and negation patterns
                            if '*' in h or '?' in h or h.startswith('!'):
                                continue
                            if h not in seen:
                                seen.add(h)
                                hosts.append(h)
                    elif key == 'include':
                        for pattern in args:
                            for fpath in sorted(
                                glob.glob(os.path.expanduser(pattern))
                            ):
                                self._parse_ssh_config_file(
                                    fpath, hosts, seen
                                )
        except FileNotFoundError:
            dbg(f"SSH config file not found: {filepath}")
        except Exception as e:
            dbg(f"Error parsing SSH config {filepath}: {e}")

    def _ssh_g_hostinfo(self, host: str) -> Optional[Tuple[str, str]]:
        """
        Query `ssh -G host` using the configured ssh binary and return
        (hostname, user) — ssh's own fully-resolved view of the target,
        honoring Includes, Match blocks, wildcards and User directives.
        Respects the configured ssh_config file (passed via -F) and the
        ssh_command executable. Returns None if the query fails. Results
        are cached per host.
        """
        if host in Remote.ssh_g_cache:
            return Remote.ssh_g_cache[host]
        info: Optional[Tuple[str, str]] = None
        ssh_exe = self._get_config()['ssh_command']
        cmd = [ssh_exe, '-G']
        # honor the plugin's ssh_config option; only pass -F when the file
        # exists so a missing file can't make ssh -G error out entirely
        config_path = os.path.expanduser(self._get_config()['ssh_config'])
        if os.path.exists(config_path):
            cmd += ['-F', config_path]
        cmd.append(host)
        result = None
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=5
            )
        except OSError as e:
            # some ssh_command values (e.g. shell scripts without a shebang)
            # can't be exec'd directly by the kernel; an interactive shell
            # falls back to interpreting them as scripts, so do the same
            dbg(f"ssh -G direct exec of '{ssh_exe}' failed ({e}), retrying via shell")
            try:
                cmd_str = ' '.join(shlex.quote(c) for c in cmd)
                result = subprocess.run(
                    cmd_str, shell=True,
                    capture_output=True, text=True, timeout=5
                )
            except Exception as e2:
                dbg(f"ssh -G shell retry failed: {e2}")
        except Exception as e:
            dbg(f"ssh -G query for '{host}' failed: {e}")
        if result is not None:
            hostname = None
            user = None
            for line in result.stdout.splitlines():
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                key = parts[0].lower()
                if key == 'hostname' and hostname is None:
                    hostname = parts[1].strip()
                elif key == 'user' and user is None:
                    user = parts[1].strip()
            if hostname is not None:
                info = (hostname, user or '')
        Remote.ssh_g_cache[host] = info
        return info

    def _canonicalize_host(self, host: str) -> str:
        """
        Map a hostname/IP from a password prompt back to its ssh config
        alias ('192.168.1.100' -> 'sp-0'), resolving each known alias via
        `ssh -G`. Aliases and unknown hosts are returned unchanged.
        """
        if not host:
            return host
        aliases = self._parse_ssh_config()
        if host in aliases:
            return host  # already an alias
        for alias in aliases:
            info = self._ssh_g_hostinfo(alias)
            if info and info[0] == host:
                dbg(f"canonicalized prompt host '{host}' -> '{alias}'")
                return alias
        return host

    def _get_resolved_user(self, host: str) -> Optional[str]:
        """ effective username ssh would use for `host`, per its config """
        info = self._ssh_g_hostinfo(host)
        return info[1] or None if info else None

    def _get_running_containers(self):
        """
        Get list of running containers via Docker/Podman API.
        Returns list of (name, image) tuples, sorted by name.
        """
        api = DockerAPI.get_instance()
        if not api._connect():
            return []
        
        try:
            containers = [
                (c['name'], c['image']) for c in api.list_containers()
            ]
            containers.sort(key=lambda x: x[0])
            return containers
        except Exception as e:
            dbg(f"Error listing containers: {e}")
            return []

    def _send_delayed_command(self, terminal, command, delay_ms):
        """Send a command to the terminal after a delay"""
        self._send_after_delay(terminal, f"{command}\n", delay_ms)

    def _send_after_delay(self, terminal, text, delay_ms, then=None):
        """Feed text into the terminal after delay_ms, but ONLY once no
        password prompt sits on the cursor row.

        Typing into an active password prompt would corrupt auth: the tty
        is in no-echo mode, so the text (and its trailing newline) is
        consumed by ssh AS the password and submitted ("Permission
        denied"), and the real secret fetched by the auto-entry then
        finds no prompt left to answer. When a prompt IS on the cursor
        row the send is re-checked every PASSWORD_COMMAND_RETRY_INTERVAL
        ms — the prompt disappears once the auto-entered (or manually
        typed) password is accepted — at most PASSWORD_COMMAND_MAX_RETRIES
        times before giving up. Optional `then` callback runs after the
        text is fed (used to chain cd after the host command).
        """
        GLib.timeout_add(
            delay_ms, self._send_when_no_prompt, terminal, text, then,
            PASSWORD_COMMAND_MAX_RETRIES
        )
        dbg(f"scheduled delayed command {text.strip()!r} for "
            f"{delay_ms}ms from now")

    def _send_when_no_prompt(self, terminal, text, then, retries) -> bool:
        """
        GLib timeout callback for _send_after_delay: feed `text` unless a
        password prompt is on the cursor row, in which case re-check every
        PASSWORD_COMMAND_RETRY_INTERVAL ms while `retries` remain. A method
        rather than a closure so dbg() attributes its output to Remote.
        """
        line, _row = self._get_prompt_line(terminal)
        if PASSWORD_PROMPT_RE.search(line):
            if retries > 0:
                dbg(f"delayed send {text.strip()!r}: password prompt "
                    f"still active, deferring "
                    f"({PASSWORD_COMMAND_MAX_RETRIES - retries + 1}/"
                    f"{PASSWORD_COMMAND_MAX_RETRIES})")
                GLib.timeout_add(
                    PASSWORD_COMMAND_RETRY_INTERVAL,
                    self._send_when_no_prompt, terminal, text, then,
                    retries - 1
                )
                return False
            dbg(f"delayed send {text.strip()!r}: password prompt "
                f"persisted too long "
                f"({PASSWORD_COMMAND_MAX_RETRIES} retries), giving up")
            return False
        vte = terminal.get_vte()
        if vte is None:
            dbg(f"delayed send {text.strip()!r}: terminal has no vte, "
                f"skipping")
            return False
        dbg(f"Sending delayed command {text.strip()!r}")
        vte.feed_child(text.encode())
        if then is not None:
            then()
        return False  # run once

    def _send_host_command(self, terminal, child, remote_session):
        """
        Send the configured host command when a manually-started remote
        session is first detected by the poller. This covers the case where
        the user types `ssh foo` or `docker exec ...` directly instead of
        using the dropdown menu.

        Uses sent_host_commands to avoid double-sending when the dropdown
        menu (or clone) already scheduled the command before the poller
        detected the remote session.
        """
        if terminal in Remote.sent_host_commands:
            dbg(f"Host command already sent or scheduled for this terminal, skipping")
            return

        try:
            if child.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                dbg(f"Process {child.pid} is {child.status()}, skipping host command")
                return
        except psutil.NoSuchProcess:
            dbg(f"Process {child.pid} no longer exists, skipping host command")
            return

        remoteHost = remote_session.GetHost(child)
        if not remoteHost:
            dbg("cannot determine host for manually-started session, skipping command")
            return
        dbg(f"manually-started remote session detected on pid={child.pid}, "
            f"host '{remoteHost}'")
        host_config = self._get_host_config(remoteHost)
        command = host_config.get('command', '')
        if not command:
            dbg(f"no 'command' in host config for '{remoteHost}', "
                f"nothing to send")
            return

        delay = float(host_config.get('command_delay', 1.0))
        dbg(f"Manually-started session detected for '{remoteHost}', will send command '{command}' after {delay}s")
        Remote.sent_host_commands.add(terminal)
        self._send_delayed_command(terminal, command, int(delay * 1000))

    def _ssh_to_host(self, terminal: Any, host: str) -> None:
        """Send ssh command to terminal, optionally followed by a post-connect command"""
        vte = terminal.get_vte()
        ssh_exe = self._get_config()['ssh_command']
        cmd = f"{ssh_exe} {host}\n"
        dbg(f"Sending '{cmd.strip()}' to terminal")
        host_config = self._get_host_config(host)
        dbg(f"host config for '{host}': "
            f"command={host_config.get('command', '')!r}, "
            f"command_delay={host_config.get('command_delay', '<default>')!r}, "
            f"password_command={'set' if host_config.get('password_command') else 'not set'}")
        vte.feed_child(cmd.encode())

        # Check host config for a post-connect command
        command = host_config.get('command', '')
        if command:
            delay = float(host_config.get('command_delay', 1.0))
            dbg(f"Will send command '{command}' after {delay}s (host config for '{host}')")
            self._send_delayed_command(terminal, command, int(delay * 1000))
            # Mark as sent so the poller doesn't double-send when it detects the SSH process
            Remote.sent_host_commands.add(terminal)
            dbg(f"marked terminal as host-command-scheduled (pid={terminal.pid})")

    def _attach_to_container(self, terminal: Any, name: str) -> None:
        """Send exec command to terminal using configured shell, optionally followed by a post-connect command"""
        vte = terminal.get_vte()
        config = self._get_config()
        shell = config['container_shell']
        container_exe = config['container_command']
        cmd = f"{container_exe} exec -it {name} {shell}\n"
        dbg(f"Sending '{cmd.strip()}' to terminal")
        vte.feed_child(cmd.encode())

        # Check container host config for a post-connect command
        host_config = self._get_host_config(name)
        command = host_config.get('command', '')
        if command:
            delay = float(host_config.get('command_delay', 1.0))
            dbg(f"Will send command '{command}' after {delay}s (host config for '{name}')")
            self._send_delayed_command(terminal, command, int(delay * 1000))
            # Mark as sent so the poller doesn't double-send when it detects the container process
            Remote.sent_host_commands.add(terminal)

    def callback(self, menuitems: List[Any], menu: Any, terminal: Any) -> None:
        """ Add our menu items to the menu """

        def get_image_menuitem(title: str, horiz: bool) -> Any:
            item = Gtk.ImageMenuItem.new_with_mnemonic(title)
            image = Gtk.Image()
            image.set_from_icon_name(
                "{}_{}".format(APP_NAME, "horiz" if horiz else "vert"),
                Gtk.IconSize.MENU
            )
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            return item

        # Check for existing remote session
        ret = Remote._get_proc_watch().GetPIDProcInfo(terminal.pid)

        if not ret:
            # No remote session — show options to launch new sessions
            ssh_hosts = self._parse_ssh_config()
            containers = self._get_running_containers()

            if ssh_hosts or containers:
                menuitems.append(Gtk.SeparatorMenuItem())

            if ssh_hosts:
                ssh_menu = Gtk.Menu()
                ssh_item = Gtk.MenuItem(_('SSH to Host'))
                ssh_item.set_submenu(ssh_menu)
                for host in ssh_hosts:
                    host_item = Gtk.MenuItem(host)
                    host_item.connect('activate', lambda w, h=host: self._ssh_to_host(terminal, h))
                    ssh_menu.append(host_item)
                ssh_menu.show_all()
                menuitems.append(ssh_item)

            if containers:
                container_menu = Gtk.Menu()
                container_item = Gtk.MenuItem(_('Attach to Container'))
                container_item.set_submenu(container_menu)
                for name, image in containers:
                    label = f"{name} ({image})" if image else name
                    c_item = Gtk.MenuItem(label)
                    c_item.connect('activate', lambda w, n=name: self._attach_to_container(terminal, n))
                    container_menu.append(c_item)
                container_menu.show_all()
                menuitems.append(container_item)

            return

        child, remote_session = ret
        dbg(f"Found remote session {child}")

        # separator before clone commands
        menuitems.append(Gtk.SeparatorMenuItem())
        
        # if we have split-auto signal
        if APP_VERSION >= '2.1.3':
            item = Gtk.MenuItem.new_with_mnemonic(_('Clone Auto'))
            item.connect(
                'activate',
                self._menu_item_activated,
                ('split-auto', terminal)
            )
            menuitems.append(item)

        # normal split buttons
        item = get_image_menuitem(_('Clone Horizontally'), horiz=True)
        item.connect(
            'activate',
            self._menu_item_activated,
            ('split-horiz', terminal)
        )
        menuitems.append(item)

        item = get_image_menuitem(_('Clone Vertically'), horiz=False)
        item.connect(
            'activate',
            self._menu_item_activated,
            ('split-vert', terminal)
        )
        menuitems.append(item)

        # "Clone into <path>" items — only shown when a path is selected
        selected_path = self._get_selected_path(terminal)
        if selected_path:
            item = get_image_menuitem(
                _('Clone Horizontally into %s') % selected_path, horiz=True
            )
            item.connect(
                'activate',
                self._menu_item_activated_into,
                ('split-horiz', terminal, selected_path)
            )
            menuitems.append(item)

            item = get_image_menuitem(
                _('Clone Vertically into %s') % selected_path, horiz=False
            )
            item.connect(
                'activate',
                self._menu_item_activated_into,
                ('split-vert', terminal, selected_path)
            )
            menuitems.append(item)

        # toggle to use pwd for CWD detection instead of regex
        item = Gtk.CheckMenuItem(_('Use pwd for CWD'))
        item.set_active(self._get_config()['use_pwd'])
        item.connect(
            'toggled',
            self._on_use_pwd,
            None
        )
        menuitems.append(item)

        # add option to clone on split
        item = Gtk.CheckMenuItem(_('Clone On Split'))
        item.set_active(self._get_config()['auto_clone'])
        item.connect(
            'toggled',
            self._on_clone_on_split,
            None
        )
        menuitems.append(item)

        # Clone On Split is driven by the Terminal split signals
        # (split-auto/split-horiz/split-vert), hooked in _update_watches —
        # this covers keybind splits and context-menu splits uniformly.
        # Prime the peers snapshot here so a split within the first poll
        # tick still diffs correctly.
        if self._get_config()['auto_clone']:
            self.peers = self._get_all_terminals()

    def _on_clone_on_split(self, widget: Any, _data: Any = None) -> None:
        """ handle check text box """
        self._get_config()['auto_clone'] = widget.get_active()

    def _on_use_pwd(self, widget: Any, _data: Any = None) -> None:
        """ handle use pwd toggle """
        self._get_config()['use_pwd'] = widget.get_active()

    def _menu_item_activated_into(self, _, args):
        """
        clone callback with explicit CWD from selected text,
        args: ( signal, terminal, cwd_path )
        Bypasses regex/pwd detection — uses the highlighted path directly.
        """
        signal, terminal, cwd_path = args

        ret = Remote._get_proc_watch().GetPIDProcInfo(terminal.pid)
        if not ret:
            err("lost remote session seen on context menu?")
            return
        child, remoteType = ret
        if not self.timeout_id:
            self.remote_proc = child
            self.remote_type = remoteType
            self._continue_clone(signal, terminal, cwd_path)
        else:
            err("already waiting for a terminal?")

    def _poll_new_terminals(self, start_time):
        """
        Watch for new terminals
        TODO: I'd rather have a signal for when the new terminal is spawned
        """
        currPeers = self._get_all_terminals()
        if len(currPeers) != len(self.peers):
            # parent container changed, get the added child
            newPeers = [ x for x in currPeers if x not in self.peers ]
            if not len(newPeers):
                err("container removed children?!")
                return False
            dbg(f"Container has new children: {newPeers}")
            if len(newPeers) != 1:
                err("container has more than one child?!")
            newTermUUID = newPeers[0]
            newTerminal = self.terminator.find_terminal_by_uuid(newTermUUID.urn)
            self._spawn_remote_session(newTerminal)
            self.timeout_id = None
            self.newPeers = None
            return False

        # check if we have been polling too long
        if abs(time.time() - start_time) > 0.1:
            err("timeout polling for terminals")
            self.timeout_id = None
            self.newPeers = None
            return False

        dbg("polling for new terminals...")
        return True

    def _get_all_terminals(self) -> Set[Any]:
        """ get all unique terminal instances """
        peers: Set[Any] = set()
        try:
            peers = { x.uuid for x in (self.terminator.terminals or []) }
        except Exception as e:
            err(f"caught exception getting terminals: {e}")
        return peers

    def _spawn_remote_session(self, terminal: Any) -> None:
        """ spawn user session into terminal """
        remote_type = self.remote_type
        remote_proc = self.remote_proc
        if remote_type is None or remote_proc is None:
            err("no remote session to clone, skipping")
            return

        config = self._get_config()
        if isinstance(remote_type, ContainerSession):
            remote_cmd = remote_type.Clone(
                remote_proc,
                shell=config['container_shell']
            )
        else:
            remote_cmd = remote_type.Clone(remote_proc)

        spawn_cmd = " ".join(remote_cmd) # get as full string, not list of strings
        cmd = f"{spawn_cmd}{os.linesep}" # make sure we press "enter"

        dbg(f"will launch '{cmd}' into new terminal")
        vte = terminal.get_vte()
        vte.feed_child(cmd.encode())

        # Check host config for a post-connect command
        remoteHost = remote_type.GetHost(remote_proc)
        host_command = None
        host_command_delay = 1.0
        command_before_cd = True
        if remoteHost:
            host_config = self._get_host_config(remoteHost)
            host_command = host_config.get('command', '')
            host_command_delay = float(host_config.get('command_delay', 1.0))
            command_before_cd = str(
                host_config.get('command_before_cd', 'true')
            ).lower() == 'true'

        has_cd = self.remote_cwd not in (None, "", "~")
        cd_delay_ms = int(float(config['cd_delay']) * 1000)
        command_delay_ms = int(host_command_delay * 1000)

        if not has_cd:
            # No cd to send — just schedule the post-connect command if any
            if host_command:
                dbg(f"Will send command '{host_command}' after {host_command_delay}s (host config for '{remoteHost}')")
                self._send_delayed_command(terminal, host_command, command_delay_ms)
        elif command_before_cd and host_command:
            # Command first, then cd — both gated on no password prompt
            dbg(f"Will send command '{host_command}' after {host_command_delay}s, then cd after {cd_delay_ms}ms more (host config for '{remoteHost}')")
            self._send_after_delay(
                terminal, f"{host_command}\n", command_delay_ms,
                then=lambda: GLib.timeout_add(
                    cd_delay_ms, self._send_cd_after_command, terminal
                )
            )
        elif host_command:
            # Cd first, then command — both gated on no password prompt
            snippet = CD_CMD.format(cwd=self.remote_cwd) + os.linesep
            dbg(f"Will send cd after {cd_delay_ms}ms, then command '{host_command}' after {command_delay_ms}ms more (host config for '{remoteHost}')")
            def send_command_later() -> bool:
                remaining_delay = max(0, command_delay_ms - cd_delay_ms)
                self._send_delayed_command(terminal, host_command, remaining_delay)
                return False
            self._send_after_delay(terminal, snippet, cd_delay_ms, then=send_command_later)
        else:
            # Only cd, no command
            snippet = CD_CMD.format(cwd=self.remote_cwd) + os.linesep
            dbg(f"will send snippet '{snippet}' into new terminal after {cd_delay_ms}ms")
            self._send_after_delay(terminal, snippet, cd_delay_ms)

        # Mark as sent so the poller doesn't double-send when it detects the cloned session
        if host_command:
            Remote.sent_host_commands.add(terminal)

        self._apply_host_settings(terminal)

    def _send_cd_after_command(self, terminal) -> bool:
        """ GLib timeout callback: cd into remote_cwd once the host command ran """
        snippet = CD_CMD.format(cwd=self.remote_cwd) + os.linesep
        dbg(f"Sending cd after command")
        self._send_after_delay(terminal, snippet, 0)
        return False

    def _get_default_profile(self, remote_type: Optional[RemoteSession]) -> str:
        """
        get default profile from config
        maybe more useful in the future...
        """
        config = self._get_config()
        if isinstance(remote_type, SSHSession):
            return config['ssh_default_profile']
        if isinstance(remote_type, ContainerSession):
            return config['container_default_profile']
        return ''

    def _apply_host_settings(
        self,
        terminal: Any,
        proc: Optional[psutil.Process] = None,
        proc_type: Optional[RemoteSession] = None
    ) -> None:
        """ setup terminal if host is in config """
        remote_proc = self.remote_proc if proc is None else proc
        remote_type = self.remote_type if proc_type is None else proc_type

        if remote_proc is None or remote_type is None:
            dbg("no remote session to apply host settings for, skipping")
            return

        # Guard: skip if process is terminated
        try:
            if remote_proc.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                dbg(f"Process {remote_proc.pid} is {remote_proc.status()}, skipping host settings")
                return
        except psutil.NoSuchProcess:
            dbg(f"Process {remote_proc.pid} no longer exists, skipping host settings")
            return

        profile = self._get_default_profile(remote_type)
        if not profile:
            dbg("no default profile specified in config")
        # check host entry in config
        remoteHost = remote_type.GetHost(remote_proc)
        if not remoteHost:
            dbg(f"cannot determine host for proc {remote_proc}")
        else:
            hostSettings = self._get_host_config(remoteHost)
            if 'profile' in hostSettings:
                profile = hostSettings['profile']
            # else:
            #     dbg(f"no profile entry for {remoteHost}")
        if not profile:
            dbg("cant find a profile in config")
            # Still track this terminal so we don't re-process it every poll cycle
            if terminal not in self.currRemoteTerminals:
                self.currRemoteTerminals[terminal] = terminal.get_profile()
            return
        if terminal.get_profile() != profile:
            dbg(f"applying profile: {profile}")
            self.currRemoteTerminals[terminal] = terminal.get_profile()
            terminal.set_profile(None, profile=profile)

    def _continue_clone(self, signal, terminal, remote_cwd):
        """Continue the clone process after CWD has been determined"""
        self.remote_cwd = remote_cwd
        # get list of current terminals, we will watch for a new one
        self.peers = self._get_all_terminals()
        dbg("First peer list: {}".format(self.peers))
        # launch idle callback to poll for new terminals
        self.timeout_id = GLib.idle_add(
            self._poll_new_terminals,
            time.time()
        )
        self._apply_host_settings(terminal)
        # launch new terminal. Suppress the split-signal handler while we
        # do: this emit creates the terminal and would otherwise also
        # trigger _on_split_signal, double-spawning the session
        Remote.split_suppress = True
        try:
            terminal.emit(signal, terminal.get_cwd())
        finally:
            Remote.split_suppress = False

    def _menu_item_activated(self, _, args):
        """
        clone callback, args: ( signal, terminal )
        """
        signal, terminal = args

        ret = Remote._get_proc_watch().GetPIDProcInfo(terminal.pid)
        if not ret:
            err("lost remote session seen on context menu?")
            return
        child, remoteType = ret
        if not self.timeout_id: # check if we are already waiting
            self.remote_proc = child
            self.remote_type = remoteType
            if self._get_config()['use_pwd']:
                # Use pwd for CWD detection (requires idle shell)
                self.timeout_id = True  # sentinel to prevent re-entry
                self._get_cwd_via_pwd(
                    terminal,
                    lambda cwd: self._continue_clone(signal, terminal, cwd)
                )
            elif self._get_config()['infer_cwd']:
                remote_cwd = self._get_cwd_from_lines(terminal)
                self._continue_clone(signal, terminal, remote_cwd)
            else:
                self._continue_clone(signal, terminal, None)
        else:
            err("already waiting for a terminal?")
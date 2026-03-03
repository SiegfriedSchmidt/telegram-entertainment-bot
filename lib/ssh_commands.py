import asyncio
import json
import paramiko
import time
from typing import Tuple, List, Callable, Awaitable
from lib.config_reader import config
from lib.init import keys_folder_path
from lib.logger import ssh_logger
from lib.models import HostModel

proj = "/home/DockerProjects"


class SSHCommands:
    def __init__(self, host: HostModel):
        self.name = host.name.get_secret_value()
        self.hostname = host.hostname.get_secret_value()
        self.port = int(host.port.get_secret_value())
        self.username = host.username.get_secret_value()
        self.key = paramiko.Ed25519Key.from_private_key_file(keys_folder_path / host.key_name.get_secret_value())
        self.ssh: paramiko.SSHClient | None = None
        self.following_file: str = ''
        ssh_logger.info(f"SSH commands module for {self.name} created!")

    def get_running_containers(self) -> dict:
        result = self.run_single_command("docker ps -s --format json")
        return json.loads(f'[{','.join(result[0].splitlines())}]')

    def get_stats(self) -> tuple[dict, dict, str, str, str]:
        results = self.run_multiple_commands([
            "docker ps -s --format json",
            "docker stats --no-stream --format json",
            "free -h | awk '/Mem:/ {printf \"%s/%s\n\", $3, $2}'",
            "top -bn1 | grep \"Cpu(s)\" | awk '{print 100 - $8 \"%\"}'",
            "uptime -p"
        ])
        docker_ps = json.loads(f'[{','.join(results[0][0].splitlines())}]')
        docker_stats = json.loads(f'[{','.join(results[1][0].splitlines())}]')
        return docker_ps, docker_stats, results[2][0], results[3][0], results[4][0]

    def get_docker_projects(self) -> List[str]:
        result, error = self.run_single_command(f"ls {proj}")
        return result.splitlines()

    def up_project(self, project_name: str) -> str:
        result, error = self.run_single_command(f"cd {proj}/{project_name} && docker compose up -d")
        return error

    def down_project(self, project_name: str) -> str:
        result, error = self.run_single_command(f"cd {proj}/{project_name} && docker compose down")
        return error

    def update(self):
        result, error = self.run_single_command(f"""
nohup sh -c '
    cd {proj}/telegram-ssh-bot &&
    docker compose pull &&
    docker compose down &&
    docker compose up -d
' >/tmp/bot_update.log 2>&1 &
""")
        return result

    # youruser ALL=(ALL) NOPASSWD: /usr/sbin/reboot
    def reboot(self):
        result, error = self.run_single_command(f"""
        nohup sh -c '
            sudo reboot
        ' >/tmp/bot_update.log 2>&1 &
        """)
        return result

    def docker_prune(self):
        result, error = self.run_single_command("docker system prune -f")
        return result

    def curl(self, args: str):
        return self.run_single_command(f"curl {args}")

    def wakeonlan(self, mac: str):
        return self.run_single_command(f"wakeonlan {mac}")

    async def follow_file(self, location: str, callback: Callable[[str], Awaitable[None]]) -> None:
        if self.following_file:
            raise RuntimeError(f"You are following file '{self.following_file}' right now!")

        self.connect()
        stdin, stdout, stderr = self.ssh.exec_command(f"tail -n 1 -F {location}", get_pty=True, timeout=None)
        stdin.close()
        self.following_file = location

        try:
            while True:
                if not self.following_file:
                    break

                if stdout.channel.recv_ready():
                    line = stdout.readline()
                    if line:
                        await callback(line)
                    else:
                        break
                else:
                    await asyncio.sleep(1)
        except Exception as e:
            ssh_logger.error("Error in file following", exc_info=e)
        finally:
            stdout.channel.close()
            self.disconnect()

    def unfollow(self):
        self.following_file = ''

    def openconnect(self, action: str):
        return self.run_single_command(f"sudo systemctl {action} openconnect.service")

    def connect(self) -> None:
        if self.ssh is None:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.hostname, self.port, username=self.username, pkey=self.key)

    def disconnect(self) -> None:
        if self.ssh:
            self.ssh.close()
            self.ssh = None

    def run_multiple_commands(self, commands: List[str], delay: float = 1) -> List[Tuple[str, str]]:
        if self.following_file:
            raise RuntimeError(f"You are following file '{self.following_file}' right now!")

        if not commands:
            return []

        results = []
        with self:
            for i, command in enumerate(commands):
                ssh_logger.info(f"Running command on {self.name}: {command}")
                try:
                    stdin, stdout, stderr = self.ssh.exec_command(command)

                    # Add timeout to prevent hanging
                    stdout.channel.settimeout(30)

                    result = stdout.read().decode().strip()
                    error = stderr.read().decode().strip()
                    results.append((result, error))

                    if i < len(commands) - 1:
                        time.sleep(delay)

                except Exception as e:
                    results.append(('', f"Command failed on {self.name}: {str(e)}"))

        return results

    def run_single_command(self, command: str) -> Tuple[str, str]:
        return self.run_multiple_commands([command])[0]

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def __del__(self):
        self.disconnect()
        ssh_logger.info(f"SSH commands module for {self.name} destroyed!")


if __name__ == '__main__':
    ssh_commands = SSHCommands(config.hosts[0])
    ssh_commands.get_stats()

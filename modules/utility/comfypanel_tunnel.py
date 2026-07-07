import re
import os
import subprocess
import platform
import signal
import threading
import tempfile
import urllib.request
import tarfile
import zipfile
import shutil

class TunnelManager:
    _instance = None
    _process = None
    _status = "disconnected"
    _version = "0.51.3"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TunnelManager, cls).__new__(cls)
        return cls._instance

    def get_bin_path(self):
        """Get the corresponding frpc binary path based on the OS"""
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        system = platform.system().lower()
        arch = platform.machine().lower()

        bin_name = f"frpc_{system}"
        if "arm" in arch or "aarch64" in arch:
            bin_name += "_arm64"
        else:
            bin_name += "_amd64"

        if system == "windows":
            bin_name += ".exe"

        return os.path.join(base_path, "bin", bin_name)

    def _ensure_binary(self):
        """Ensure the binary exists, download if not"""
        bin_path = self.get_bin_path()
        if os.path.exists(bin_path):
            return True

        system = platform.system().lower()
        arch = platform.machine().lower()

        plat_name = "linux" if system == "linux" else ("darwin" if system == "darwin" else "windows")
        arch_name = "arm64" if ("arm" in arch or "aarch64" in arch) else "amd64"

        ext = "zip" if system == "windows" else "tar.gz"
        folder_name = f"frp_{self._version}_{plat_name}_{arch_name}"

        urls = [
            f"https://github.com/fatedier/frp/releases/download/v{self._version}/{folder_name}.{ext}",
            f"https://ghp.ci/https://github.com/fatedier/frp/releases/download/v{self._version}/{folder_name}.{ext}",
            f"https://mirror.ghproxy.com/https://github.com/fatedier/frp/releases/download/v{self._version}/{folder_name}.{ext}"
        ]

        bin_dir = os.path.dirname(bin_path)
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir)

        temp_file = os.path.join(bin_dir, f"temp_frp.{ext}")

        success = False
        for url in urls:
            print(f"[Tunnel] Trying to download from {url}...")
            try:

                subprocess.run(["curl", "-k", "-L", "-o", temp_file, url],
                             check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(temp_file) and os.path.getsize(temp_file) > 1000000:
                    success = True
                    break
            except:
                pass

            try:

                urllib.request.urlretrieve(url, temp_file)
                if os.path.exists(temp_file) and os.path.getsize(temp_file) > 1000000:
                    success = True
                    break
            except:
                pass

        if not success:
            print(f"[Tunnel] All download sources failed.")
            return False

        try:
            if ext == "zip":
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(bin_dir)
                src_bin = os.path.join(bin_dir, folder_name, "frpc.exe")
            else:
                with tarfile.open(temp_file, "r:gz") as tar_ref:
                    tar_ref.extractall(bin_dir)
                src_bin = os.path.join(bin_dir, folder_name, "frpc")

            if os.path.exists(src_bin):
                shutil.move(src_bin, bin_path)
                if system != "windows":
                    os.chmod(bin_path, 0o755)

                if os.path.exists(temp_file):
                    os.remove(temp_file)
                extracted_dir = os.path.join(bin_dir, folder_name)
                if os.path.exists(extracted_dir):
                    shutil.rmtree(extracted_dir)

                print(f"[Tunnel] Dependency installed to {bin_path}")
                return True
            else:
                print(f"[Tunnel] Error: Could not find binary in extracted package.")
                return False
        except Exception as e:
            print(f"[Tunnel] Installation failed: {str(e)}")
            return False

    def start(self, server_addr, server_port, token, remote_port=None, local_port=8188, subdomain=None):

        server_addr = server_addr.replace("https://", "").replace("http://", "").split("/")[0].strip()

        if self._process:
            self.stop()

        config_content = f"[common]\nserver_addr = {server_addr}\nserver_port = {server_port}\ntoken = {token}\n\n[comfyui_tunnel]\n"
        if subdomain:
            config_content += f"type = http\nlocal_ip = 127.0.0.1\nlocal_port = {local_port}\nsubdomain = {subdomain}\n"
        else:
            config_content += f"type = tcp\nlocal_ip = 127.0.0.1\nlocal_port = {local_port}\nremote_port = {remote_port}\n"

        if not self._ensure_binary():
            return {"success": False, "error": "Failed to download tunnel dependency (frpc). Please check internet connection."}

        bin_path = self.get_bin_path()

        fd, config_path = tempfile.mkstemp(suffix=".ini", prefix="frpc_")
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)

        if not os.path.exists(bin_path):
            print(f"[ComfyPanel ERROR] Binary NOT FOUND at: {bin_path}")
            return {"success": False, "error": "Binary not found"}

        try:
            os.chmod(bin_path, 0o755)
        except:
            pass

        self._config_path = config_path

        try:
            self._last_error = ""
            self._is_ready = False
            self._status = "connecting"

            self._process = subprocess.Popen(
                [bin_path, "-c", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            threading.Thread(target=self._monitor_logs, daemon=True).start()

            import re
            is_ip = bool(re.match(r'^[\d\.]+$', server_addr))
            protocol = "http"

            if not is_ip and str(remote_port) in ["443", "2053", "2083", "2087", "2096", "8443"]:
                protocol = "https"

            if subdomain:
                web_port = "8443"
                self._remote_url = f"https://{subdomain}.{server_addr}:{web_port}"
            elif protocol == "http" and str(remote_port) == "80":
                self._remote_url = f"http://{server_addr}"
            elif protocol == "https" and str(remote_port) == "443":
                self._remote_url = f"https://{server_addr}"
            else:
                self._remote_url = f"{protocol}://{server_addr}:{remote_port}"

            return {"success": True, "remote_url": self._remote_url}
        except Exception as e:
            self._status = "error"

            if os.path.exists(config_path):
                try: os.remove(config_path)
                except: pass
            print(f"[ComfyPanel ERROR] Failed to start frpc: {e}")
            return {"success": False, "error": str(e)}

    def stop(self):
        if self._process:
            self._process.terminate()
            self._process = None
            self._status = "disconnected"

            if hasattr(self, '_config_path') and os.path.exists(self._config_path):
                try:
                    os.remove(self._config_path)
                    print(f"[Tunnel] Cleaned up temporary config.")
                except Exception as e:
                    print(f"[Tunnel] Error cleaning up config: {e}")

            return True
        return False

    def _monitor_logs(self):
        if not self._process or not self._process.stdout:
            return
        try:
            for line in iter(self._process.stdout.readline, ''):
                if not line:
                    break
                line_str = line.strip()
                if "start proxy success" in line_str:
                    print(f"[Tunnel] Connected to official relay successfully.")
                    self._is_ready = True
                    self._status = "connected"

                if "login to server failed" in line_str or "error" in line_str.lower() or "[W]" in line_str or "[E]" in line_str:
                    print(f"[Tunnel ERROR] {line_str}")
                    parts = line_str.split("] ", 2)
                    err_msg = parts[-1] if len(parts) >= 2 else line_str
                    if "EOF" in err_msg:
                        err_msg += " (Possible port/protocol mismatch or CDN interception)"
                    self._last_error = err_msg
        except Exception as e:
            pass

    def get_status_info(self):
        if self._process:
            if self._process.poll() is not None:
                self._status = "error"

        return {
            "status": self._status,
            "running": self._status == "connected" and getattr(self, "_is_ready", False),
            "error": getattr(self, "_last_error", ""),
            "remote_url": getattr(self, "_remote_url", "")
        }

tunnel_manager = TunnelManager()
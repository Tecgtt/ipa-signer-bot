import os
import shutil
import zipfile
import subprocess
import tempfile
import plistlib
from typing import Optional, Dict, Any, Tuple
from bot.services.icon_replacer import IconReplacer


class IPASigner:
    def __init__(self, zsign_bin: str = "zsign"):
        self.zsign_bin = zsign_bin

    def check_zsign_available(self) -> bool:
        """Checks whether zsign is available in system PATH or configured path."""
        try:
            res = subprocess.run([self.zsign_bin, "-v"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0 or b"zsign" in res.stdout or b"zsign" in res.stderr
        except FileNotFoundError:
            return False

    def sign(
        self,
        ipa_path: str,
        p12_path: str,
        p12_password: str,
        mobileprovision_path: str,
        output_ipa_path: str,
        new_bundle_id: Optional[str] = None,
        new_app_name: Optional[str] = None,
        custom_icon_path: Optional[str] = None,
        dylib_path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Signs the IPA file using zsign.
        """
        if not os.path.exists(ipa_path):
            return False, f"IPA file not found: {ipa_path}"
        if not os.path.exists(p12_path):
            return False, f"Certificate (.p12) not found: {p12_path}"
        if not os.path.exists(mobileprovision_path):
            return False, f"Mobileprovision profile not found: {mobileprovision_path}"

        if not self.check_zsign_available():
            return False, (
                "zsign binary not found on the server!\n"
                "Please install zsign to enable signing. Run `./install_zsign.sh`."
            )

        work_dir = tempfile.mkdtemp(prefix="ipa_sign_")
        try:
            target_to_sign = ipa_path

            # If we need to replace app icon or inspect app name/plist
            if (custom_icon_path and os.path.exists(custom_icon_path)) or new_app_name:
                extract_dir = os.path.join(work_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(ipa_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                payload_dir = os.path.join(extract_dir, "Payload")
                if not os.path.exists(payload_dir):
                    return False, "Invalid IPA structure: Payload directory not found."

                app_dirs = [d for d in os.listdir(payload_dir) if d.endswith(".app")]
                if not app_dirs:
                    return False, "Invalid IPA structure: No .app bundle found inside Payload."

                app_path = os.path.join(payload_dir, app_dirs[0])

                # Replace icon if requested
                if custom_icon_path and os.path.exists(custom_icon_path):
                    IconReplacer.replace_app_icons(app_path, custom_icon_path)

                # Replace app display name in Info.plist if requested
                if new_app_name:
                    info_plist_path = os.path.join(app_path, "Info.plist")
                    if os.path.exists(info_plist_path):
                        try:
                            with open(info_plist_path, "rb") as fp:
                                plist_data = plistlib.load(fp)
                            plist_data["CFBundleDisplayName"] = new_app_name
                            plist_data["CFBundleName"] = new_app_name
                            with open(info_plist_path, "wb") as fp:
                                plistlib.dump(plist_data, fp)
                        except Exception as pe:
                            print(f"[IPASigner] Failed to update Info.plist: {pe}")

                target_to_sign = app_path

            # Build zsign command
            cmd = [
                self.zsign_bin,
                "-k", p12_path,
                "-p", p12_password,
                "-m", mobileprovision_path,
                "-o", output_ipa_path,
                "-z", "9",  # maximum compression
            ]

            if new_bundle_id and new_bundle_id.strip():
                cmd.extend(["-b", new_bundle_id.strip()])

            if new_app_name and new_app_name.strip() and target_to_sign == ipa_path:
                cmd.extend(["-n", new_app_name.strip()])

            if dylib_path and os.path.exists(dylib_path):
                cmd.extend(["-l", dylib_path])

            cmd.append(target_to_sign)

            print(f"[IPASigner] Executing: {' '.join(cmd)}")
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=work_dir
            )

            if res.returncode != 0:
                err_output = res.stderr or res.stdout
                return False, f"Signing failed with code {res.returncode}:\n{err_output}"

            if not os.path.exists(output_ipa_path) or os.path.getsize(output_ipa_path) == 0:
                return False, f"Signing finished but output file was not created.\n{res.stdout}"

            return True, "Successfully signed IPA!"

        except Exception as e:
            return False, f"Unexpected error during signing: {str(e)}"
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

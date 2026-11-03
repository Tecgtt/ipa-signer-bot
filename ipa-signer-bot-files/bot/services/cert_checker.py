import os
import plistlib
import subprocess
import datetime
from typing import Dict, Any, Optional

try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CertificateChecker:
    @staticmethod
    def inspect_p12(p12_path: str, password: str = "") -> Dict[str, Any]:
        """
        Inspects a .p12 certificate file and returns parsed info.
        """
        if not os.path.exists(p12_path):
            return {"success": False, "error": "P12 file not found on disk."}

        # Try with cryptography first
        if HAS_CRYPTOGRAPHY:
            try:
                with open(p12_path, "rb") as f:
                    data = f.read()
                
                pass_bytes = password.encode("utf-8") if password else None
                try:
                    private_key, cert, additional_certs = pkcs12.load_key_and_certificates(data, pass_bytes)
                except Exception as e:
                    # Password error or corruption
                    err_msg = str(e).lower()
                    if "mac" in err_msg or "password" in err_msg or "pkcs12" in err_msg:
                        return {"success": False, "error": "Invalid P12 password or corrupted certificate."}
                    raise e

                if cert is None:
                    return {"success": False, "error": "No certificate found inside the P12 file."}

                common_name = "Unknown"
                org_name = "Unknown"
                org_unit = "Unknown"

                for attr in cert.subject:
                    oid = attr.oid.dotted_string
                    if oid == "2.5.4.3":  # Common Name
                        common_name = attr.value
                    elif oid == "2.5.4.10":  # Organization
                        org_name = attr.value
                    elif oid == "2.5.4.11":  # Organizational Unit / Team ID
                        org_unit = attr.value

                now = datetime.datetime.now(datetime.timezone.utc)
                
                # Check dates
                try:
                    not_before = cert.not_valid_before_utc
                    not_after = cert.not_valid_after_utc
                except AttributeError:
                    not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
                    not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)

                is_expired = now > not_after
                days_left = (not_after - now).days

                return {
                    "success": True,
                    "common_name": common_name,
                    "organization": org_name,
                    "team_id": org_unit,
                    "valid_from": not_before.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "valid_to": not_after.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "days_left": days_left,
                    "is_expired": is_expired,
                    "has_private_key": private_key is not None,
                }
            except Exception as ex:
                pass

        # Fallback to openssl command line tool
        try:
            cmd = [
                "openssl", "pkcs12", "-in", p12_path, "-passin", f"pass:{password}",
                "-nokeys"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                if "invalid password" in res.stderr.lower() or "mac verify failure" in res.stderr.lower():
                    return {"success": False, "error": "Invalid P12 password."}
                return {"success": False, "error": f"OpenSSL error: {res.stderr.strip()}"}

            cert_text = res.stdout

            # Parse with openssl x509
            x509_cmd = ["openssl", "x509", "-noout", "-subject", "-dates", "-issuer"]
            res_x509 = subprocess.run(x509_cmd, input=cert_text, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_x509.returncode != 0:
                return {"success": False, "error": "Failed to parse certificate."}

            out = res_x509.stdout
            lines = out.strip().split("\n")
            details = {}
            for line in lines:
                if "=" in line:
                    k, v = line.split("=", 1)
                    details[k.strip().lower()] = v.strip()

            subject = details.get("subject", "")
            not_before_str = details.get("notbefore", "")
            not_after_str = details.get("notafter", "")

            # Extract CN from subject
            cn = "Unknown"
            if "CN" in subject:
                parts = subject.split("/")
                for p in parts:
                    if p.startswith("CN="):
                        cn = p[3:]

            return {
                "success": True,
                "common_name": cn,
                "organization": "",
                "team_id": "",
                "valid_from": not_before_str,
                "valid_to": not_after_str,
                "days_left": 0,
                "is_expired": False,
                "has_private_key": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to inspect P12: {str(e)}"}

    @staticmethod
    def inspect_mobileprovision(prov_path: str) -> Dict[str, Any]:
        """
        Extracts and parses the embedded plist inside an Apple .mobileprovision file.
        """
        if not os.path.exists(prov_path):
            return {"success": False, "error": "Mobileprovision file not found on disk."}

        try:
            with open(prov_path, "rb") as f:
                content = f.read()

            start = content.find(b"<?xml")
            end = content.find(b"</plist>")

            if start == -1 or end == -1:
                return {"success": False, "error": "No valid XML plist found in mobileprovision."}

            xml_data = content[start : end + len(b"</plist>")]
            plist = plistlib.loads(xml_data)

            name = plist.get("Name", "Unknown Profile")
            app_id_name = plist.get("AppIDName", "Unknown")
            team_name = plist.get("TeamName", "Unknown Team")
            team_ids = plist.get("TeamIdentifier", [])
            team_id = team_ids[0] if team_ids else "Unknown"
            uuid = plist.get("UUID", "Unknown")
            created_at = plist.get("CreationDate")
            expires_at = plist.get("ExpirationDate")
            provisions_all = plist.get("ProvisionsAllDevices", False)
            devices = plist.get("ProvisionedDevices", [])
            entitlements = plist.get("Entitlements", {})
            app_id = entitlements.get("application-identifier", "*")

            now = datetime.datetime.now(datetime.timezone.utc)
            if expires_at:
                if expires_at.tzinfo is None:
                    exp_tz = expires_at.replace(tzinfo=datetime.timezone.utc)
                else:
                    exp_tz = expires_at
                is_expired = now > exp_tz
                days_left = (exp_tz - now).days
            else:
                is_expired = False
                days_left = 0

            return {
                "success": True,
                "name": name,
                "app_id_name": app_id_name,
                "app_id": app_id,
                "team_name": team_name,
                "team_id": team_id,
                "uuid": uuid,
                "created_at": str(created_at),
                "expires_at": str(expires_at),
                "is_expired": is_expired,
                "days_left": days_left,
                "is_enterprise": provisions_all,
                "devices_count": len(devices),
                "devices": devices[:10]  # First 10 UDIDs sample
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to parse mobileprovision: {str(e)}"}

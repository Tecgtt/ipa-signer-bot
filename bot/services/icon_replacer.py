import os
import shutil
import glob
from typing import Optional

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class IconReplacer:
    @staticmethod
    def replace_app_icons(app_dir: str, new_icon_path: str) -> bool:
        """
        Replaces all existing app icons inside the extracted .app directory with the new icon.
        """
        if not os.path.exists(app_dir) or not os.path.exists(new_icon_path):
            return False

        if not HAS_PIL:
            # Fallback: simple copy over common icon names
            common_icon_names = [
                "AppIcon60x60@2x.png",
                "AppIcon60x60@3x.png",
                "AppIcon76x76@2x~ipad.png",
                "AppIcon83.5x83.5@2x~ipad.png",
                "icon.png",
                "Icon.png",
                "Icon@2x.png",
            ]
            for icon_name in common_icon_names:
                dst = os.path.join(app_dir, icon_name)
                if os.path.exists(dst):
                    shutil.copy2(new_icon_path, dst)
            return True

        try:
            with Image.open(new_icon_path) as src_img:
                src_img = src_img.convert("RGBA")

                # Find all png files with 'icon' in the name inside app_dir
                matched_icons = []
                for root, dirs, files in os.walk(app_dir):
                    for file in files:
                        lower = file.lower()
                        if lower.endswith(".png") and ("icon" in lower or "appicon" in lower):
                            matched_icons.append(os.path.join(root, file))

                if not matched_icons:
                    # Create standard icons
                    targets = [
                        ("AppIcon60x60@2x.png", (120, 120)),
                        ("AppIcon60x60@3x.png", (180, 180)),
                        ("AppIcon76x76@2x~ipad.png", (152, 152)),
                    ]
                    for name, size in targets:
                        resized = src_img.resize(size, Image.Resampling.LANCZOS)
                        resized.save(os.path.join(app_dir, name), "PNG")
                    return True

                for icon_file in matched_icons:
                    try:
                        with Image.open(icon_file) as orig:
                            w, h = orig.size
                        resized = src_img.resize((w, h), Image.Resampling.LANCZOS)
                        resized.save(icon_file, "PNG")
                    except Exception:
                        pass

                return True
        except Exception as e:
            print(f"[IconReplacer] Error replacing icon: {e}")
            return False

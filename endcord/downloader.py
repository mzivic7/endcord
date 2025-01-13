import os
import urllib.parse

import urllib3
from endcord import peripherals

CHUNK_SIZE = 1024 * 1024   # load max 1MB data in RAM when downloading


def convert_tenor_gif_type(url, content_type):
    """
    Convert tenor video link between types:
    0 - gif HD
    1 - gif UHD
    2 - mp4 Video
    """
    if content_type == 1:
        return url.replace("AAAPo/", "AAAAC/")[:-3] + "gif"
    if content_type == 2:
        return url
    return url.replace("AAAPo/", "AAAAd/")[:-3] + "gif"


class Downloader:
    """Downloader class"""

    def __init__(self):
        self.downloading = True
        self.active = 0


    def download(self, url):
        """Download that downloads file and stores it in temp folder"""
        if not os.path.exists(peripherals.temp_path):
            os.makedirs(os.path.expanduser(os.path.dirname(peripherals.temp_path)), exist_ok=True)
        url_object = urllib.parse.urlparse(url)
        filename = os.path.basename(url_object.path)
        http = urllib3.PoolManager()
        response = http.request("GET", url, preload_content=False)
        extension = response.headers.get("Content-Type", None).split("/")[-1].replace("jpeg", "jpg")
        destination = os.path.join(peripherals.temp_path, filename)
        if os.path.splitext(destination)[-1] == "" and extension:
            destination = destination + "." + extension
        self.active += 1
        self.downloading = True
        complete = False
        with open(destination, "wb") as out:
            while self.downloading:
                data = response.read(CHUNK_SIZE)
                if not data:
                    complete = True
                    break
                out.write(data)
        response.release_conn()
        self.active -= 1
        if self.active == 0:
            self.downloading = True
        if complete:
            return destination
        return None

    def cancel(self):
        """Stops all active downloads"""
        self.downloading = False

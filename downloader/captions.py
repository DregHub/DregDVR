import asyncio
import subprocess
import xml.etree.ElementTree as ET
import os

class CaptionManager:
    XML_FILE = "video_data.xml"

    @classmethod
    async def _init_xml(cls):
        if not os.path.exists(cls.XML_FILE):
            root = ET.Element("videos")
            tree = ET.ElementTree(root)
            await asyncio.to_thread(tree.write, cls.XML_FILE)

    @classmethod
    async def _video_exists(cls, url):
        tree = await asyncio.to_thread(ET.parse, cls.XML_FILE)
        root = tree.getroot()
        return any(video.find("url").text == url for video in root.findall("video"))

    @classmethod
    async def _add_video(cls, url, has_subtitles):
        if await cls._video_exists(url):
            return

        tree = await asyncio.to_thread(ET.parse, cls.XML_FILE)
        root = tree.getroot()

        video = ET.SubElement(root, "video")
        ET.SubElement(video, "url").text = url
        ET.SubElement(video, "has_subtitles").text = str(has_subtitles)
        ET.SubElement(video, "downloaded").text = "false"
        ET.SubElement(video, "attempts").text = "0"

        await asyncio.to_thread(tree.write, cls.XML_FILE)

    @classmethod
    async def monitor_channel(cls, channel_url):
        await cls._init_xml()

        async def monitor():
            while True:
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", channel_url],
                        capture_output=True, text=True
                    )
                    video_ids = result.stdout.strip().split("\n")
                    for vid in video_ids:
                        video_url = f"https://www.youtube.com/watch?v={vid}"
                        sub_check = await asyncio.to_thread(
                            subprocess.run,
                            ["yt-dlp", "--list-subs", video_url],
                            capture_output=True, text=True
                        )
                        has_subtitles = "Available subtitles" in sub_check.stdout
                        await cls._add_video(video_url, has_subtitles)
                except Exception as e:
                    print(f"Error monitoring channel: {e}")
                await asyncio.sleep(300)  # 5 minutes

        asyncio.create_task(monitor())

    @classmethod
    async def download_captions(cls):
        await cls._init_xml()
        tree = await asyncio.to_thread(ET.parse, cls.XML_FILE)
        root = tree.getroot()

        for video in root.findall("video"):
            url = video.find("url").text
            has_subtitles = video.find("has_subtitles").text == "True"
            downloaded = video.find("downloaded").text == "true"
            attempts = int(video.find("attempts").text)

            if has_subtitles and not downloaded:
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["yt-dlp", "--write-subs", "--skip-download", url]
                    )
                    video.find("downloaded").text = "true"
                except Exception as e:
                    print(f"Failed to download subtitles for {url}: {e}")
                finally:
                    video.find("attempts").text = str(attempts + 1)

        await asyncio.to_thread(tree.write, cls.XML_FILE)

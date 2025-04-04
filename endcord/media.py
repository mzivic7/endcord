import curses
import logging
import threading
import time

import av
import magic
import sounddevice
from PIL import Image, ImageEnhance

from endcord import xterm256

logger = logging.getLogger(__name__)


class CursesMedia():
    """Methods for showing and playing media in termial with curses"""

    def __init__(self, screen, config, start_color_id):
        logging.getLogger("libav").setLevel(logging.ERROR)
        self.screen = screen
        self.font_scale = config["font_scale"]   # 2.25
        self.ascii_palette = config["ascii_palette"]   # "  ..',;:c*loexk#O0XNW"
        self.saturation = config["saturation"]   # 1.2
        self.default_fps = config["target_fps"]   # 30
        self.color_media_bg = config["color_media_bg"]   # -1
        self.mute_video = config["mute_video"]   # false
        self.start_color_id = start_color_id
        self.ascii_palette_len = len(self.ascii_palette) - 1
        self.xterm_256_palette = xterm256.palette_short
        self.playing = False
        self.screen_size = self.screen.getmaxyx()
        # self.init_colrs()
        # https://github.com/python/cpython/issues/119138
        # as temporary fix, old color pairs are cached and replaced, later restored
        self.start_color_id = 0


    def init_colrs(self):
        """Initialize 255 colors for drawing picture, from starting color ID"""
        for i in range(0, 255):
            curses.init_pair(self.start_color_id + i, i, self.color_media_bg)


    def cache_colors(self):
        """Cache existing first 255 colors"""
        pass


    def restore_colors(self):
        """Restore cached 255 colors"""
        pass


    def pil_img_to_curses(self, img, remove_alpha=True):
        """Convert pillow inage to ascii art and display it with curses"""
        screen_height, screen_width = self.screen.getmaxyx()
        height, width = self.screen.getmaxyx()

        # scale image
        wpercent = (width / (float(img.size[0] * self.font_scale)))
        hsize = int((float(img.size[1]) * float(wpercent)))
        if hsize > height:
            hpercent = (height / float(img.size[1]))
            wsize = int((float(img.size[0] * self.font_scale) * float(hpercent)))
            width = wsize
        else:
            height = hsize
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        img_gray = img.convert("L")

        # get filler sizes
        filler_h = int((screen_height - height) / 2)
        filler_w = int((screen_width - width) / 2)

        # increase saturation
        if self.saturation:
            sat = ImageEnhance.Color(img)
            img = sat.enhance(self.saturation)

        if remove_alpha and img.mode != "RGB" and img.mode != "L":
            background = Image.new("RGB", img.size, (0, 0, 0))
            background.paste(img, mask=img.split()[3])
            img = background

        # apply xterm256 palette
        img_palette = Image.new("P", (16, 16))
        img_palette.putpalette(self.xterm_256_palette)
        img = img.quantize(palette=img_palette, dither=0)

        # draw with curses
        pixels = img.load()
        pixels_gray = img_gray.load()
        for y_fill in range(filler_h):
            self.screen.insstr(y_fill, 0, " " * screen_width, curses.color_pair(self.start_color_id+1))
        for y in range(height):
            if filler_w > 0:
                self.screen.insstr(y + filler_h, 0, " " * filler_w, curses.color_pair(self.start_color_id+1))
            for x in range(width):
                character = self.ascii_palette[round(pixels_gray[x, y] * self.ascii_palette_len / 255)]
                color = self.start_color_id + pixels[x, y] + 16
                self.screen.insch(y + filler_h, x + filler_w, character, curses.color_pair(color))
            if x + filler_w + 1 < screen_width:
                self.screen.insstr(y + filler_h, x + filler_w + 1, " " * (screen_width - (x + filler_w + 1)) + "/n", curses.color_pair(self.start_color_id+1))
        for y_fill in range(filler_h + 1):
            self.screen.insstr(screen_height - 1 - y_fill, 0, " " * screen_width, curses.color_pair(self.start_color_id+1))
        self.screen.refresh()


    def play_img(self, img_path):
        """
        Convert image to colored ascii art and draw it with curses.
        If image is animated (eg apng) send it to play_anim instead.
        """
        img = Image.open(img_path)
        if hasattr(img, "is_animated") and img.is_animated:
            self.play_anim(img_path)
            return
        self.init_colrs()
        self.pil_img_to_curses(img)
        while self.playing:
            self.screen.refresh()
            screen_size = self.screen.getmaxyx()
            if self.screen_size != screen_size:
                self.pil_img_to_curses(img)
                self.screen_size = screen_size
            time.sleep(0.1)


    def play_anim(self, gif_path):
        """Convert animated image to colored ascii art and draw it with curses"""
        self.init_colrs()
        gif = Image.open(gif_path)
        frame = 0
        loop = bool(gif.info.get("loop", 1))
        while self.playing:
            try:
                start_time = time.time()
                frame_duration = gif.info["duration"] / 1000
                gif.seek(frame)
                img = Image.new("RGB", gif.size)
                img.paste(gif)
                self.pil_img_to_curses(img, remove_alpha=False)
                frame += 1
                time.sleep(max(frame_duration - (time.time() - start_time), 0))
            except EOFError:
                if loop:
                    break
                frame = 0


    def play_video(self, path):
        """Play video"""
        self.init_colrs()
        container = av.open(path)

        # prepare video
        self.video_fps = container.streams.video[0].guessed_rate   # instead base_rate
        frame_duration = 1 / self.video_fps
        self.target_fps = self.default_fps
        self.target_frames = max(int(self.video_fps / self.target_fps), 1)
        self.audio_time = 0
        self.video_time = 0

        # prepare audio
        if not self.mute_video:
            audio_container = av.open(path)
            all_audio_streams = audio_container.streams.audio
            if all_audio_streams:   # in case of a muted video
                audio_stream = all_audio_streams[0]
                stream = sounddevice.RawOutputStream(
                    samplerate=audio_stream.rate,
                    channels=audio_stream.channels,
                    dtype="float32",
                )
                self.audio_thread = threading.Thread(target=self.play_sync_audio, daemon=True, args=(audio_container, stream))
                self.audio_thread.start()

        for index, frame in enumerate(container.decode(video=0)):
            if not self.playing:
                container.close()
                break
            start_time = time.time()
            if not index % self.target_frames:
                img = frame.to_image()
                self.pil_img_to_curses(img, remove_alpha=False)
            if self.video_time >= self.audio_time:
                # if all is fine or video is ahead of audio
                time.sleep(max(max(frame_duration, self.video_time - self.video_time) - (time.time() - start_time), 0))
                self.target_fps = min(self.target_fps + 1, self.default_fps)   # increase fps
                self.target_frames = max(int(self.video_fps / self.target_fps), 1)
            self.video_time += frame_duration
        self.audio_thread.join()


    def play_sync_audio(self, container, stream):
        """Play audio synchronized with video"""
        stream.start()
        start_time = time.time()
        for frame in container.decode(audio=0):
            if not self.playing:
                break
            if self.audio_time - self.video_time > 0.1:
                # if audio is ahead of video
                self.target_fps = max(self.target_fps - 1, 1)   # decrease fps
                self.target_frames = max(int(self.video_fps / self.target_fps), 1)
            stream.write(frame.to_ndarray().astype("float32").T.flatten())
            self.audio_time = time.time() - start_time
        stream.close()


    def play(self, path):
        """Select runner based on file type"""
        file_type = magic.from_file(path, mime=True).split("/")
        self.playing = True
        try:
            if file_type[0] == "image":
                if file_type[1] == "gif":
                    self.play_anim(path)
                else:
                    self.play_img(path)
            elif file_type[0] == "video":
                self.play_video(path)
            else:
                logger.warn(f"Unsupported media format: {file_type}")
        except Exception as e:
            logger.error(e)


    def stop(self):
        """Stop playing media"""
        self.playing = False
        self.redraw_img = False

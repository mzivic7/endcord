import curses
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
from queue import Queue

import av
import magic
import soundcard
from PIL import Image, ImageEnhance

from endcord import xterm256

logger = logging.getLogger(__name__)
speaker = soundcard.default_speaker()
match_youtube = re.compile(r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)[a-zA-Z0-9_-]{11}")


class CursesMedia():
    """Methods for showing and playing media in termial with curses"""

    def __init__(self, screen, config, start_color_id):
        logging.getLogger("libav").setLevel(logging.ERROR)
        self.screen = screen
        self.font_scale = config["media_font_scale"]   # 2.25
        self.ascii_palette = config["media_ascii_palette"]   # "  ..',;:c*loexk#O0XNW"
        self.saturation = config["media_saturation"]   # 1.2
        self.cap_fps = config["media_cap_fps"]   # 30
        self.color_media_bg = config["media_color_bg"]   # -1
        self.mute_video = config["media_mute"]   # false
        self.bar_ch = config["media_bar_ch"]
        self.default_color = config["color_default"][0]   # all 255 colors already init in order
        self.yt_dlp_path = config["yt_dlp_path"]
        self.yt_dlp_format = config["yt_dlp_format"]
        if self.default_color == -1:
            self.default_color = 0
        self.start_color_id = start_color_id
        self.ascii_palette_len = len(self.ascii_palette) - 1
        self.xterm_256_palette = xterm256.palette_short
        self.run = False
        self.playing = False
        self.ended = False
        self.pause = False
        self.pause_after_seek = False
        self.path = None
        self.media_type = None

        self.need_update = threading.Event()
        self.show_ui()

        self.media_screen_size = self.media_screen.getmaxyx()
        # self.init_colrs()   # 255_curses_bug - enable this
        self.start_color_id = 0   # 255_curses_bug


    def init_colrs(self):
        """Initialize 255 colors for drawing picture, from starting color ID"""
        for i in range(1, 255):
            curses.init_pair(self.start_color_id + i, i, self.color_media_bg)


    def screen_update(self):
        """Thread that updates drawn content on physical screen"""
        while self.run:
            self.need_update.wait()
            # here must be delay, otherwise output gets messed up
            time.sleep(0.005)   # lower delay so video is not late
            curses.doupdate()
            self.need_update.clear()


    def pil_img_to_curses(self, img, remove_alpha=True):
        """Convert pillow image to ascii art and display it with curses"""
        screen_height, screen_width = self.media_screen.getmaxyx()
        height, width = self.media_screen.getmaxyx()

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
            self.media_screen.insstr(y_fill, 0, " " * screen_width, curses.color_pair(self.start_color_id+1))
        for y in range(height):
            if filler_w > 0:
                self.media_screen.insstr(y + filler_h, 0, " " * filler_w, curses.color_pair(self.start_color_id+1))
            for x in range(width):
                character = self.ascii_palette[round(pixels_gray[x, y] * self.ascii_palette_len / 255)]
                color = self.start_color_id + pixels[x, y] + 16
                self.media_screen.insch(y + filler_h, x + filler_w, character, curses.color_pair(color))
            if x + filler_w + 1 < screen_width:
                self.media_screen.insstr(y + filler_h, x + filler_w + 1, " " * (screen_width - (x + filler_w + 1)) + "/n", curses.color_pair(self.start_color_id+1))
        if screen_height != height:
            for y_fill in range(filler_h + 1):
                self.media_screen.insstr(screen_height - 1 - y_fill, 0, " " * screen_width, curses.color_pair(self.start_color_id+1))
        self.media_screen.noutrefresh()
        self.need_update.set()


    def play_img(self, img_path):
        """
        Convert image to colored ascii art and draw it with curses.
        If image is animated (eg apng) send it to play_anim instead.
        """
        img = Image.open(img_path)
        if hasattr(img, "is_animated") and img.is_animated:
            self.media_type = "gif"
            self.play_anim(img_path)
            return
        self.init_colrs()   # 255_curses_bug
        self.hide_ui()
        self.pil_img_to_curses(img)
        while self.playing:
            self.media_screen.noutrefresh()
            self.need_update.set()
            screen_size = self.media_screen.getmaxyx()
            if self.media_screen_size != screen_size:
                self.pil_img_to_curses(img)
                self.media_screen_size = screen_size
            time.sleep(0.1)


    def play_anim(self, gif_path):
        """Convert animated image to colored ascii art and draw it with curses"""
        self.init_colrs()   # 255_curses_bug
        self.hide_ui()
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


    def play_audio(self, path, seek=None):
        """Play only audio"""
        self.init_colrs()   # 255_curses_bug
        self.show_ui()
        container = av.open(path)
        self.ended = False
        self.video_time = 0   # using video_time to simplify controls
        if seek is None:
            self.seek = None

        # fill screen
        self.media_screen.clear()
        h, w = self.media_screen.getmaxyx()
        for y in range(h):
            self.media_screen.insstr(y, 0, " " * w, curses.color_pair(self.start_color_id+1))
        self.media_screen.noutrefresh()
        self.need_update.set()

        all_audio_streams = container.streams.audio
        if not all_audio_streams:   # no audio?
            return
        audio_stream = all_audio_streams[0]

        if audio_stream.duration:
            self.video_duration = float(audio_stream.duration * audio_stream.time_base)
        else:
            self.video_duration = audio_stream.frames / audio_stream.average_rate * audio_stream.time_base
        if self.video_duration == 0:
            self.video_duration = 1   # just in case

        frame_duration = 1 / container.streams.audio[0].codec_context.sample_rate

        with speaker.player(samplerate=audio_stream.rate, channels=audio_stream.channels, blocksize=1152) as stream:
            for frame in container.decode(audio=0):
                if self.seek and self.seek > self.video_time:
                    self.video_time += frame.samples * frame_duration
                    if self.pause_after_seek:
                        self.pause_after_seek = False
                        self.pause = True
                    continue
                if not self.playing:
                    break
                stream.play(frame.to_ndarray().astype("float32").T)
                self.video_time += frame.samples * frame_duration
                if self.pause:
                    self.draw_ui()
                    while self.pause:
                        time.sleep(0.1)
        self.ended = True


    def audio_player(self, audio_queue, samplerate, channels, audio_ready):
        """Play audio frames from the queue"""
        with speaker.player(samplerate=samplerate, channels=channels, blocksize=1152) as stream:
            audio_ready.set()
            while True:
                frame = audio_queue.get()
                if frame is None:
                    break
                stream.play(frame.to_ndarray().astype("float32").T)
                while self.pause:
                    time.sleep(0.1)


    def video_player(self, video_queue, audio_queue, frame_duration):
        """Play video frames from the queue"""
        while True:
            frame = video_queue.get()
            if frame is None:
                break
            start_time = time.time()
            img = frame.to_image()
            if audio_queue.qsize() >= 1:
                self.pil_img_to_curses(img, remove_alpha=False)
            if audio_queue.qsize() >= 3:
                time.sleep(max(frame_duration - (time.time() - start_time), 0))
            while self.pause:
                time.sleep(0.1)


    def play_video(self, path, seek=None):
        """Decode video and audio frames and manage queues"""
        self.init_colrs()   # 255_curses_bug
        self.show_ui()
        container = av.open(path)
        self.ended = False
        if seek is None:
            self.seek = None
        self.video_time = 0

        video_stream = container.streams.video[0]
        if container.streams.video[0].duration:
            self.video_duration = float(video_stream.duration * video_stream.time_base)
        else:
            self.video_duration = video_stream.frames / video_stream.average_rate * video_stream.time_base
        if self.video_duration == 0:
            self.video_duration = 1   # just in case
        frame_duration = 1 / container.streams.video[0].guessed_rate

        # prepare audio
        audio_queue = Queue(maxsize=10)
        have_audio = False
        if not self.mute_video:
            all_audio_streams = container.streams.audio
            if all_audio_streams:   # in case of a muted video
                audio_ready = threading.Event()
                have_audio = True
                audio_stream = all_audio_streams[0]
                audio_thread = threading.Thread(target=self.audio_player, args=(audio_queue, audio_stream.rate, audio_stream.channels, audio_ready), daemon=True)
                audio_thread.start()
                audio_ready.wait()   # wait for adudio to decrease desyncing
                audio_ready.clear()

        # prepare video
        video_queue = Queue(maxsize=10)
        video_thread = threading.Thread(target=self.video_player, args=(video_queue, audio_queue, frame_duration), daemon=True)
        video_thread.start()

        for frame in container.decode():
            if self.seek and self.seek > self.video_time:
                if isinstance(frame, av.video.frame.VideoFrame):
                    self.video_time += frame_duration
                if self.pause_after_seek:
                    self.pause_after_seek = False
                    self.pause = True
                continue
            if not self.playing:
                container.close()
                break
            if isinstance(frame, av.audio.frame.AudioFrame) and have_audio:
                audio_queue.put(frame)
            if isinstance(frame, av.video.frame.VideoFrame):
                video_queue.put(frame)
                self.video_time += frame_duration
            if self.pause:
                self.draw_ui()
                while self.pause:
                    time.sleep(0.1)

        audio_queue.put(None)
        video_queue.put(None)
        if have_audio:
            audio_thread.join()
        video_thread.join()
        self.ended = True


    def play(self, path):
        """Select runner based on file type"""
        if not path:
            return
        self.path = path
        self.run = True
        self.screen_update_thread = threading.Thread(target=self.screen_update, daemon=True)
        self.screen_update_thread.start()
        self.playing = True
        try:
            yt_match = re.search(match_youtube, path)
            if yt_match:
                self.play_youtube(yt_match.group())
            elif "https://" in path:
                self.media_type = "video"
                self.start_ui_thread()
                self.play_video(path)
            else:
                file_type = magic.from_file(path, mime=True).split("/")
                if file_type[0] == "image":
                    if file_type[1] == "gif":
                        self.media_type = "gif"
                        self.play_anim(path)
                    else:
                        self.media_type = "img"
                        self.play_img(path)
                elif file_type[0] == "video":
                    self.media_type = "video"
                    self.start_ui_thread()
                    self.play_video(path)
                elif file_type[0] == "audio":
                    self.media_type = "audio"
                    self.start_ui_thread()
                    self.play_audio(path)
                else:
                    logger.warn(f"Unsupported media format: {file_type}")
                    self.run = False
            while self.run:   # dont exit when video ends
                time.sleep(0.2)
        except Exception as e:
            logger.error("".join(traceback.format_exception(e)))
        self.run = False
        self.playing = False
        self.need_update.set()
        self.screen_update_thread.join()


    def play_youtube(self, url):
        """Get youtube video stream and play video"""
        if shutil.which(self.yt_dlp_path):
            command = [self.yt_dlp_path, "-f", str(self.yt_dlp_format), "-g", url]
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            stream_url = proc.communicate()[0].decode().strip("\n")
            self.path = stream_url
            self.media_type = "video"
            self.start_ui_thread()
            self.play_video(stream_url)
        else:
            logger.warn("Cant play youtube link, yt-dlp path is invalid")


    def control_codes(self, code):
        """Handle controls from TUI"""
        if code == 100:   # quit media player
            self.pause = False
            self.run = False
            self.playing = False
        elif code == 101 and self.media_type in ("audio", "video"):   # pause
            self.show_ui()
            self.pause = not self.pause
        elif code == 102 and self.media_type in ("audio", "video"):   # replay
            self.show_ui()
            self.pause = False
            self.playing = False
            while not self.ended:
                time.sleep(0.1)
            self.playing = True
            if self.media_type == "video":
                self.player_thread = threading.Thread(target=self.play_video, daemon=True, args=(self.path, ))
                self.player_thread.start()
            elif self.media_type == "audio":
                self.player_thread = threading.Thread(target=self.play_audio, daemon=True, args=(self.path, ))
                self.player_thread.start()
        elif code == 103 and self.media_type in ("audio", "video") and not self.ended:   # seek forward
            self.show_ui()
            if self.pause:
                self.pause = False
                self.pause_after_seek = True
            self.seek = min(self.video_time + 5, self.video_duration)
        elif code == 104 and self.media_type in ("audio", "video") and not self.ended:   # seek backward
            self.show_ui()
            pause = self.pause
            if pause:
                self.pause = False
            self.playing = False
            while not self.ended:
                time.sleep(0.1)
            if pause:
                self.pause = True
            self.playing = True
            self.seek = max(self.video_time - 5, 0)
            if self.media_type == "video":
                self.player_thread = threading.Thread(target=self.play_video, daemon=True, args=(self.path, self.seek))
                self.player_thread.start()
            elif self.media_type == "audio":
                self.player_thread = threading.Thread(target=self.play_audio, daemon=True, args=(self.path, self.seek))
                self.player_thread.start()
        elif code == 105:
            self.screen.clear()


    def start_ui_thread(self):
        """Start UI drawing thread"""
        self.ui_thread = threading.Thread(target=self.draw_ui_loop, daemon=True)
        self.ui_thread.start()


    def show_ui(self):
        """Show UI after its been hidden"""
        self.ui_timer = 0
        h, w = self.screen.getmaxyx()
        media_screen_hwyx = (h - 1, w, 0, 0)
        self.media_screen = self.screen.derwin(*media_screen_hwyx)
        ui_line_hwyx = (1, w, h - 1, 0)
        self.ui_line = self.screen.derwin(*ui_line_hwyx)


    def hide_ui(self):
        """Hide UI"""
        h, w = self.screen.getmaxyx()
        self.media_screen = self.screen
        self.ui_line = None


    def draw_ui_loop(self):
        """Continuously draw UI line at bottom of the screen"""
        if self.media_type == "video":
            self.video_duration = 1
            self.video_time = 0
            self.ui_timer = 0
            while self.run:
                if self.ui_timer <= 25:
                    self.draw_ui()
                    if self.ui_timer == 25:
                        self.hide_ui()
                    if not (self.pause or self.ended):
                        self.ui_timer += 1
                time.sleep(0.2)
        elif self.media_type == "audio":
            self.video_duration = 1
            self.video_time = 0
            self.ui_timer = 0
            while self.run:
                self.draw_ui()
                time.sleep(0.2)


    def draw_ui(self):
        """Draw UI line at bottom of the screen"""
        if self.ui_line:
            total_time = f"{int(self.video_duration) // 60:02d}:{int(self.video_duration) % 60:02d}"
            current_time = f"{int(self.video_time) // 60:02d}:{int(self.video_time) % 60:02d}"
            bar_len = self.screen.getmaxyx()[1] - 20   # minus len of all other elements and spaces
            filled = int(bar_len * min(self.video_time / self.video_duration, 1))
            bar = self.bar_ch * filled + " " * (bar_len - filled)
            if self.pause:
                pause = "|"
            else:
                pause = ">"
            ui_line = f"   {pause} {current_time} {bar} {total_time}  "
            self.ui_line.addstr(0, 0, ui_line, curses.color_pair(self.default_color))
            self.ui_line.noutrefresh()
            self.need_update.set()


def wait_input(screen, keybindings, curses_media):
    """Handle input from user"""
    keybindings = {key: (val,) if not isinstance(val, tuple) else val for key, val in keybindings.items()}
    run = True
    while run:
        key = screen.getch()
        if key == 27:   # ESCAPE
            screen.nodelay(True)
            key = screen.getch()
            if key in (-1, 27):
                screen.nodelay(False)
                curses_media.control_codes(100)
            screen.nodelay(False)
            run = False
        elif key in keybindings["media_pause"]:
            curses_media.control_codes(101)
        elif key in keybindings["media_replay"]:
            curses_media.control_codes(102)
        elif key in keybindings["media_seek_forward"]:
            curses_media.control_codes(103)
        elif key in keybindings["media_seek_backward"]:
            curses_media.control_codes(104)
        elif key in keybindings["redraw"]:
            curses_media.control_codes(105)
        elif key == curses.KEY_RESIZE:
            pass


def ascii_runner(screen, path, config, keybindings):
    """Main function"""
    path = os.path.expanduser(path)
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses_media = CursesMedia(screen, config, 0)
    input_thread = threading.Thread(target=wait_input, args=(screen, keybindings, curses_media), daemon=True)
    input_thread.start()
    curses_media.play(path)

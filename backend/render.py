"""Real offline MP4 preview from mock storyboard cards using FFmpeg."""
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter

FONTS = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
BOLD_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def font(size, bold=False):
    for path in (BOLD_FONTS if bold else FONTS):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def get_ffmpeg():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, FileNotFoundError) as exc:
        raise RuntimeError('Không tìm được FFmpeg. Hãy cài imageio-ffmpeg theo requirements.txt hoặc cài ffmpeg vào PATH.') from exc


def wrap_text(draw, content, f, width):
    lines = []
    for section in (content or '').split('\n'):
        line = ''
        for w in section.split():
            candidate = (line + ' ' + w).strip()
            if draw.textbbox((0,0), candidate, font=f)[2] > width and line:
                lines.append(line)
                line = w
            else:
                line = candidate
        lines.append(line)
    return lines


def preview_card(shot, char_paths, out: Path, story_title):
    W, H = 540, 960
    theme = [(11,18,34),(11,32,40),(35,21,49),(22,35,53)][(shot['index']-1)%4]
    im = Image.new('RGB', (W,H), theme)
    p = im.load()
    for y in range(H):
        pct = y / H
        for x in range(W):
            glow = max(0, 1-abs(x/W-.65)*1.5) * max(0, 1-abs(y/H-.28)*1.1)
            p[x,y] = tuple(min(255, int(c+(15 if k<2 else 20)*glow + (19 if k==2 else 9)*pct)) for k,c in enumerate(theme))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((20,18,520,925),radius=25,outline=(65,86,104),width=2)
    person_file = None
    for cid in shot['characters']:
        if cid in char_paths and Path(char_paths[cid]).exists():
            person_file = Path(char_paths[cid]); break
    if person_file:
        face = Image.open(person_file).convert('RGB')
        face = ImageOps.fit(face,(440,610),method=Image.Resampling.LANCZOS,centering=(0.5,0.23))
        mask=Image.new('L',(440,610)); d=ImageDraw.Draw(mask); d.rounded_rectangle((0,0,439,609),radius=28,fill=255)
        im.paste(face,(50,100),mask)
    else:
        draw.rounded_rectangle((50,100,490,710),radius=28,fill=(42,58,72))
        for i in range(5):
            x=105+i*70
            draw.line((x,145,x,655),fill=(54,79,98),width=2)
        draw.ellipse((215,360,325,470),outline=(140,172,190),width=7)
    overlay=Image.new('RGBA',(W,H),(0,0,0,0)); od=ImageDraw.Draw(overlay)
    for y in range(520,960):
        a=int(min(249, max(0,(y-520)/280*255)))
        od.line((0,y,W,y),fill=(8,13,22,a))
    im=Image.alpha_composite(im.convert('RGBA'),overlay)
    draw=ImageDraw.Draw(im)
    draw.rounded_rectangle((38,36,185,74),radius=12,fill=(216,123,68))
    draw.text((54,46),'AI FILM • MOCK',font=font(16,True),fill='white')
    draw.text((42,735),f"{shot['id']}  •  {shot['duration_seconds']} GIÂY",font=font(17,True),fill=(99,197,216))
    yy=772
    for line in wrap_text(draw,shot['title'],font(27,True),454)[:2]:
        draw.text((42, yy),line,font=font(27,True),fill=(248,250,250)); yy+=39
    yy=max(834,yy+4)
    desc=shot['dialogue'] or shot['action']
    for line in wrap_text(draw, desc,font(17),452)[:4]:
        draw.text((42,yy),line,font=font(17),fill=(216,225,233));yy+=25
    im.convert('RGB').save(out,'JPEG',quality=89,optimize=True)


def fmt_srt_time(seconds):
    ms=round(seconds*1000)
    h, ms = divmod(ms,3600000)
    m, ms = divmod(ms,60000)
    s, ms = divmod(ms,1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def create_subtitles(shots, dest):
    lines=[]; t=0; ix=1
    for shot in shots:
        dialogue = shot.get('dialogue') or ''
        if dialogue:
            lines.extend([str(ix),f"{fmt_srt_time(t)} --> {fmt_srt_time(t+shot['duration_seconds'])}",dialogue,""])
            ix+=1
        t+=shot['duration_seconds']
    Path(dest).write_text('\n'.join(lines),encoding='utf-8-sig')


def render_clip(image_path: Path, duration: int, out_path: Path):
    exe=get_ffmpeg()
    cmd=[exe,'-hide_banner','-loglevel','error','-y','-loop','1','-framerate','16','-i',str(image_path),'-t',str(duration),'-vf','scale=432:768,fps=16,format=yuv420p','-an','-c:v','libx264','-preset','ultrafast','-crf','27','-movflags','+faststart',str(out_path)]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    if proc.returncode!=0:
        raise RuntimeError('FFmpeg không tạo được clip: '+(proc.stderr[-600:] or 'lỗi không xác định'))


def concat_clips(clips, dest:Path, total_duration):
    exe=get_ffmpeg()
    concat_file=dest.parent/'concat.txt'
    # Paths escaped for concat demuxer on both Windows and Unix
    concat_file.write_text(''.join("file '"+str(Path(p).resolve()).replace('\\','/').replace("'", "'\\''")+"'\n" for p in clips),encoding='utf-8')
    cmd=[exe,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat_file),'-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=44100','-t',str(total_duration),'-c:v','copy','-c:a','aac','-b:a','64k','-movflags','+faststart','-shortest',str(dest)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    if p.returncode!=0:
        raise RuntimeError('FFmpeg không ghép được video: '+(p.stderr[-600:] or 'lỗi không xác định'))
    return dest

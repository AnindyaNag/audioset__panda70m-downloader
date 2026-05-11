"""
AudioSet Video Clip Downloader
================================
Downloads and trims audio/video clips from an AudioSet CSV
(eval_segments.csv / balanced_train_segments.csv / unbalanced_train_segments.csv)
using yt-dlp + ffmpeg directly.

KEY OPTIMIZATION: Downloads each YouTube video ONCE, then cuts the clip
from it before deleting the temp file. No redundant downloads.

CSV format expected (3 comment lines then data):
    # ...
    # ...
    # YTID, start_seconds, end_seconds, positive_labels
    --4gqARaEJE, 0.000, 10.000, "/m/068hy,/m/07q6cd_"

Usage:
    python download_audioset.py --n_videos 10
    python download_audioset.py --csv eval_segments.csv --n_videos 10
    python download_audioset.py --csv eval_segments.csv --n_videos 0
"""

import argparse
import os
import random
import subprocess
import sys
import time
import pandas as pd

# All paths relative to the folder this script lives in
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(SCRIPT_DIR, "eval_segments.csv")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "audioset_clips")
TEMP_DIR    = os.path.join(SCRIPT_DIR, "temp")
COOKIES     = os.path.join(SCRIPT_DIR, "cookies.txt")

# Call yt-dlp via python -m to avoid PATH issues on Windows
YT_DLP = [sys.executable, "-m", "yt_dlp"]


def check_dependencies():
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: ffmpeg not found. Please install it and make sure it is in PATH.")
        print("  Windows : winget install ffmpeg")
        print("  Ubuntu  : sudo apt install ffmpeg")
        sys.exit(1)

    result = subprocess.run(YT_DLP + ["--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: yt-dlp not found. Run: pip install yt-dlp")
        sys.exit(1)

    print("OK: ffmpeg and yt-dlp found\n")


def download_full_video(url, video_id, temp_dir, cookies_file=None):
    """Download the full YouTube video once and return path to temp file."""
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = os.path.join(temp_dir, video_id + ".mkv")

    # Clean up any leftover from a previous run
    for ext in [".mkv", ".mp4", ".webm"]:
        leftover = os.path.join(temp_dir, video_id + ext)
        if os.path.exists(leftover):
            os.remove(leftover)

    print("   [DOWNLOAD] Fetching full video...")
    yt_cmd = YT_DLP + [
        url,
        "--format", "bv*+ba/b",
        "--output", temp_file,
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--merge-output-format", "mkv",
        "--js-runtimes", "deno",
        "--remote-components", "ejs:github",
        "--sleep-requests", "2",
        "--sleep-interval", "3",
        "--max-sleep-interval", "6",
    ]

    if cookies_file and os.path.exists(cookies_file):
        yt_cmd += ["--cookies", cookies_file]

    result = subprocess.run(yt_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()[:200]
        print("   [ERROR] yt-dlp: " + err)
        if "rate-limited" in err or "rate limited" in err.lower():
            print("   [WAIT] Rate limited — sleeping 90 seconds...")
            time.sleep(90)
        return None

    # yt-dlp may adjust extension — find actual file
    if not os.path.exists(temp_file):
        matches = [f for f in os.listdir(temp_dir) if f.startswith(video_id)]
        if matches:
            temp_file = os.path.join(temp_dir, matches[0])
        else:
            print("   [ERROR] temp file not found after download")
            return None

    size_mb = os.path.getsize(temp_file) / (1024 * 1024)
    print("   [OK] downloaded full video (" + str(round(size_mb, 1)) + " MB)")
    return temp_file


def cut_clip(temp_file, start, end, out_path):
    """Cut a single clip from an already-downloaded temp file using ffmpeg."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    duration = round(end - start, 3)

    ff_cmd = [
        "ffmpeg",
        "-ss", str(start),
        "-i", temp_file,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "libmp3lame",
        "-q:a", "2",
        "-y",
        "-loglevel", "warning",
        out_path,
    ]
    result = subprocess.run(ff_cmd, capture_output=True, text=True)

    if result.stderr.strip():
        for line in result.stderr.strip().split("\n"):
            if line.strip():
                print("      ffmpeg: " + line.strip())

    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Download AudioSet clips")
    parser.add_argument("--csv",        default=DEFAULT_CSV,
                        help="Path to AudioSet CSV (default: eval_segments.csv in script folder)")
    parser.add_argument("--n_videos",   type=int, default=10,
                        help="Number of videos to process (0 = all)")
    parser.add_argument("--output_dir", default=OUTPUT_DIR,
                        help="Folder to save clips (default: audioset_clips/)")
    parser.add_argument("--temp_dir",   default=TEMP_DIR,
                        help="Temp folder for full video downloads (default: temp/)")
    parser.add_argument("--cookies",    default=COOKIES,
                        help="Path to cookies.txt exported from browser (default: cookies.txt in script folder)")
    args = parser.parse_args()

    check_dependencies()

    if not os.path.exists(args.cookies):
        print("WARNING: cookies.txt not found at: " + args.cookies)
        print("         YouTube may block some downloads. See README for how to export cookies.\n")
    else:
        print("OK: using cookies from " + args.cookies + "\n")

    print("Reading CSV: " + args.csv)

    # AudioSet CSVs have 3 comment lines at the top — skip them
    # The labels column contains quoted comma-separated values, so use
    # the python engine with quotechar to parse correctly.
    df = pd.read_csv(
        args.csv,
        skiprows=3,
        header=None,
        names=["YTID", "start_seconds", "end_seconds", "positive_labels"],
        skipinitialspace=True,
        quotechar='"',
        engine="python",
    )

    if args.n_videos and args.n_videos > 0:
        df = df.head(args.n_videos)

    label = "first " + str(args.n_videos) if args.n_videos else "all"
    print("Processing " + label + " videos (" + str(len(df)) + " rows)\n")

    total_clips   = 0
    success_clips = 0
    failed_clips  = []

    for idx, row in df.iterrows():
        video_id  = str(row["YTID"]).strip()
        start_sec = float(row["start_seconds"])
        end_sec   = float(row["end_seconds"])
        labels    = str(row["positive_labels"]).strip().strip('"')
        url       = "https://www.youtube.com/watch?v=" + video_id
        clip_name = video_id + "_clip.mp4"
        out_path  = os.path.join(args.output_dir, clip_name)

        total_clips += 1
        print("[" + str(idx + 1) + "/" + str(len(df)) + "] " + video_id +
              "  [" + str(start_sec) + "s -> " + str(end_sec) + "s]")
        print("   labels: " + labels[:80])

        # Skip if already downloaded
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print("   [SKIP] already exists\n")
            success_clips += 1
            continue

        # Download the full video
        temp_file = download_full_video(url, video_id, args.temp_dir, args.cookies)
        if temp_file is None:
            failed_clips.append(clip_name)
            print()
            continue

        # Cut the clip
        print("   [CUT]  " + str(round(end_sec - start_sec, 1)) + "s clip...")
        ok = cut_clip(temp_file, start_sec, end_sec, out_path)

        if ok:
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print("   [OK]   " + clip_name + "  (" + str(round(size_mb, 1)) + " MB)")
            success_clips += 1
        else:
            print("   [FAIL] " + clip_name)
            failed_clips.append(clip_name)

        # Delete temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print("   [DEL]  temp file removed")

        print()

        # Random sleep between videos to avoid rate limiting
        sleep_time = random.uniform(3, 7)
        time.sleep(sleep_time)

    print("=" * 60)
    print("Success : " + str(success_clips) + " / " + str(total_clips) + " clips")
    if failed_clips:
        print("Failed  : " + str(len(failed_clips)) + " clips")
        for f in failed_clips:
            print("     - " + f)
    print("Output  : " + args.output_dir)


if __name__ == "__main__":
    main()

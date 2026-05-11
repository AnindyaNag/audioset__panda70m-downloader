"""
Panda-70M Video Clip Downloader
================================
Downloads and trims video clips from the Panda-70M dataset CSV
using yt-dlp + ffmpeg directly.

KEY OPTIMIZATION: Downloads each YouTube video ONCE, then cuts ALL
clips from it before deleting the temp file. No redundant downloads.

Usage:
    python download_panda70m.py --n_videos 10
    python download_panda70m.py --csv panda70m_training_2m.csv --n_videos 10
    python download_panda70m.py --csv panda70m_training_2m.csv --n_videos 0
"""

import argparse
import ast
import os
import random
import subprocess
import sys
import time
import pandas as pd

# All paths relative to the folder this script lives in
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(SCRIPT_DIR, "panda70m_testing_with_additional_annotation.csv")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "panda70m_clips")
TEMP_DIR    = os.path.join(SCRIPT_DIR, "temp")
COOKIES     = os.path.join(SCRIPT_DIR, "cookies.txt")

# Call yt-dlp via python -m to avoid PATH issues on Windows
YT_DLP = [sys.executable, "-m", "yt_dlp"]


def ts_to_seconds(ts: str) -> float:
    parts = ts.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


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

    # Clean up any leftover from previous run
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

    # Add cookies if file exists
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

    # yt-dlp may adjust extension, find actual file
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
    parser = argparse.ArgumentParser(description="Download Panda-70M clips")
    parser.add_argument("--csv",        default=DEFAULT_CSV,
                        help="Path to the Panda-70M annotation CSV (default: testing CSV in script folder)")
    parser.add_argument("--n_videos",   type=int, default=10,
                        help="Number of videos to process (0 = all)")
    parser.add_argument("--output_dir", default=OUTPUT_DIR,
                        help="Folder to save clips (default: panda70m_clips/)")
    parser.add_argument("--temp_dir",   default=TEMP_DIR,
                        help="Temp folder for full video downloads (default: temp/)")
    parser.add_argument("--cookies",    default=COOKIES,
                        help="Path to cookies.txt exported from browser (default: cookies.txt in script folder)")
    args = parser.parse_args()

    check_dependencies()

    # Warn if cookies file not found
    if not os.path.exists(args.cookies):
        print("WARNING: cookies.txt not found at: " + args.cookies)
        print("         YouTube may block some downloads. See README for how to export cookies.\n")
    else:
        print("OK: using cookies from " + args.cookies + "\n")

    print("Reading CSV: " + args.csv)
    df = pd.read_csv(args.csv)
    if args.n_videos and args.n_videos > 0:
        df = df.head(args.n_videos)

    label = "first " + str(args.n_videos) if args.n_videos else "all"
    print("Processing " + label + " videos (" + str(len(df)) + " rows)\n")

    total_clips   = 0
    success_clips = 0
    failed_clips  = []

    for video_idx, row in df.iterrows():
        video_id   = row["videoID"]
        url        = row["url"]
        timestamps = ast.literal_eval(row["timestamp"])
        captions   = ast.literal_eval(row["caption"])
        n_clips    = len(timestamps)

        print("[" + str(video_idx + 1) + "/" + str(len(df)) + "] " + video_id + "  (" + str(n_clips) + " clips)")

        # If all clips already exist skip download entirely
        all_exist = all(
            os.path.exists(os.path.join(args.output_dir, video_id + "_clip" + str(i).zfill(2) + ".mp4")) and
            os.path.getsize(os.path.join(args.output_dir, video_id + "_clip" + str(i).zfill(2) + ".mp4")) > 0
            for i in range(n_clips)
        )
        if all_exist:
            print("   [SKIP] all clips already exist\n")
            success_clips += n_clips
            total_clips   += n_clips
            continue

        # Download the full video ONCE
        temp_file = download_full_video(url, video_id, args.temp_dir, args.cookies)
        if temp_file is None:
            for i in range(n_clips):
                failed_clips.append(video_id + "_clip" + str(i).zfill(2) + ".mp4")
            total_clips += n_clips
            print()
            continue

        # Cut ALL clips from the single downloaded file
        for clip_idx, (ts, caption) in enumerate(zip(timestamps, captions)):
            start_sec = ts_to_seconds(ts[0])
            end_sec   = ts_to_seconds(ts[1])
            clip_name = video_id + "_clip" + str(clip_idx).zfill(2) + ".mp4"
            out_path  = os.path.join(args.output_dir, clip_name)
            total_clips += 1

            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                print("   [SKIP] " + clip_name + " already exists")
                success_clips += 1
                continue

            print("   [CUT]  clip" + str(clip_idx).zfill(2) +
                  "  [" + ts[0] + " -> " + ts[1] + "]  " + caption[:55])

            ok = cut_clip(temp_file, start_sec, end_sec, out_path)

            if ok:
                size_mb = os.path.getsize(out_path) / (1024 * 1024)
                print("   [OK]   " + clip_name + "  (" + str(round(size_mb, 1)) + " MB)")
                success_clips += 1
            else:
                print("   [FAIL] " + clip_name)
                failed_clips.append(clip_name)

        # Delete temp file after ALL clips are cut
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
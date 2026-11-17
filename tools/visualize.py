# Owner: Roger
"""Check the submission against the video: overlay clips and a whole-match timeline.

    python tools/visualize.py clip --start 11185 --seconds 60     # MP4 in outputs/
    python tools/visualize.py timeline                            # PNG in outputs/

The clip draws, on the tactical video:

* every tracked player, projected with the per-frame homography (red home, blue away),
* the ball in yellow, and a ring on the nearest player of the team we say has it,
* a banner with our label, the match clock and whether the ball is tracked,
* a mini pitch and a strip of our labels 30 s either side of the cursor.

With --gt a frame,label CSV (for example the public 5-minute ground truth) is drawn next to our
labels. It is only for looking: no parameter is chosen from it.

Everything goes to outputs/, which is gitignored. The clips contain match video and the terms of
use forbid redistributing it: watch them locally, never publish them.

Needs opencv-python and matplotlib (requirements-viz.txt). The submission itself does not.
"""

import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from possession import config, loading  # noqa: E402

OUT_DIR = os.path.join(ROOT, "outputs")
FPS = config.FPS

# Same colours as the web viewer. OpenCV wants BGR.
HEX = {"H": "#c8102e", "A": "#1f4e9c", "D": "#9a9a9a", "X": "#3c3c3c"}
BGR = {k: (int(v[5:7], 16), int(v[3:5], 16), int(v[1:3], 16)) for k, v in HEX.items()}
BALL = (0, 230, 255)
WHITE = (230, 230, 230)
NAMES = {"H": "HOME (H)", "A": "AWAY (A)", "D": "DEAD BALL (D)", "X": "NO ANSWER (X)"}


def read_labels(path):
    """Labels of a frame,label CSV as an array of single letters."""
    with open(path) as handle:
        next(handle)
        return np.array([line.rstrip().split(",")[1].strip().upper() for line in handle])


def match_clock(frame):
    """Match time shown on screen, from the graded halves in config."""
    for half, (first, last) in enumerate(config.HALVES):
        if first <= frame <= last:
            seconds = (frame - first) / FPS + 45 * 60 * half
            return "{}' {:02d}\"".format(int(seconds // 60), int(seconds % 60))
    return "--"


def project(hom, x, y):
    """Normalised pitch coordinates to video pixels."""
    q = hom @ np.stack([x, y, np.ones_like(x)])
    return q[0] / q[2], q[1] / q[2]


def controller(ball, players, team_of_slot, label):
    """Slot of the nearest player of the labelled team if close enough to control the ball."""
    if label not in ("H", "A") or np.isnan(ball[0]):
        return -1
    team = config.H if label == "H" else config.A
    d = np.hypot(players[:, 0] - ball[0], players[:, 1] - ball[1])
    d = np.where((team_of_slot == team) & ~np.isnan(d), d, np.inf)
    slot = int(np.argmin(d))
    return slot if d[slot] <= config.CONTROL_RADIUS else -1


def draw_strip(cv2, img, labels, frame, y0, h, title, span=30 * FPS):
    """Bar of labels 30 s either side of the current frame, with a white cursor in the middle."""
    x0 = 20
    width = img.shape[1] - 2 * x0
    xs = np.linspace(frame - span, frame + span, width).astype(int)
    for i, f in enumerate(xs):
        lab = labels[f] if 0 <= f < len(labels) else "X"
        cv2.line(img, (x0 + i, y0), (x0 + i, y0 + h), BGR.get(lab, BGR["X"]), 1)
    cx = x0 + width // 2
    cv2.line(img, (cx, y0 - 4), (cx, y0 + h + 4), (255, 255, 255), 2)
    cv2.putText(img, title, (x0 + 4, y0 + h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)


def draw_minimap(cv2, img, ball, players, team_of_slot, slot, x0, y0, w=315, h=204):
    """Small top-down pitch in the corner with every player, the ball and a ring on the controller."""
    length, width = config.PITCH
    overlay = img.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + w, y0 + h), (40, 110, 40), -1)
    cv2.addWeighted(overlay, 0.8, img, 0.2, 0, img)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), WHITE, 1)
    cv2.line(img, (x0 + w // 2, y0), (x0 + w // 2, y0 + h), WHITE, 1)
    cv2.circle(img, (x0 + w // 2, y0 + h // 2), int(9.15 / width * h), WHITE, 1)
    box_w = int(16.5 / length * w)
    box_top = y0 + int((width / 2 - 20.16) / width * h)
    box_bottom = y0 + int((width / 2 + 20.16) / width * h)
    for bx in (x0, x0 + w - box_w):
        cv2.rectangle(img, (bx, box_top), (bx + box_w, box_bottom), WHITE, 1)

    def to_px(x, y):
        """Metres on the pitch to pixels inside the mini pitch rectangle."""
        return int(x0 + x / length * w), int(y0 + y / width * h)

    for s in range(len(players)):
        if np.isnan(players[s, 0]):
            continue
        p = to_px(players[s, 0], players[s, 1])
        cv2.circle(img, p, 4, BGR["H"] if team_of_slot[s] == config.H else BGR["A"], -1)
        if s == slot:
            cv2.circle(img, p, 7, BALL, 1)
    if not np.isnan(ball[0]):
        cv2.circle(img, to_px(ball[0], ball[1]), 3, BALL, -1)


def label_box(cv2, img, x, text, label):
    """Coloured box in the top banner with a label written in plain words."""
    cv2.rectangle(img, (x, 12), (x + 500, 60), BGR.get(label, BGR["X"]), -1)
    cv2.putText(img, text, (x + 12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (255, 255, 255), 2,
                cv2.LINE_AA)


def clip(csv, data_dir, cache_dir, start, seconds, out, scale, gt_path=None):
    """Write an MP4 of the tactical video from start for seconds, with our labels drawn on top.

    Reads the video frame by frame with OpenCV, projects tracking with the per-frame homography and
    writes to out. Returns the output path."""
    import cv2

    labels = read_labels(csv)
    gt = read_labels(gt_path) if gt_path else None
    match = loading.load_match(data_dir, cache_dir)
    file_paths = match["paths"]
    loading.check_files(file_paths, required=("video", "homography"))
    homographies = loading.read_homography(file_paths["homography"])
    ball, players, team_of_slot = match["ball"], match["players"], match["team_of_slot"]
    length, width = config.PITCH

    cap = cv2.VideoCapture(file_paths["video"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    size = (int(src_w * scale), int(src_h * scale))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), FPS, size)

    end = min(len(labels), start + int(seconds * FPS))
    for f in range(start, end):
        ok, img = cap.read()
        if not ok:
            break
        ours = labels[f]
        slot = controller(ball[f], players[f], team_of_slot, ours)
        hom = homographies[f] if f < len(homographies) else np.full((3, 3), np.nan)

        if not np.any(np.isnan(hom)):
            px, py = project(hom, players[f, :, 0] / length, players[f, :, 1] / width)
            for s in range(len(team_of_slot)):
                if np.isnan(px[s]):
                    continue
                c = (int(px[s]), int(py[s]))
                colour = BGR["H"] if team_of_slot[s] == config.H else BGR["A"]
                cv2.ellipse(img, c, (16, 6), 0, 0, 360, colour, 3)
                if s == slot:
                    cv2.ellipse(img, c, (24, 10), 0, 0, 360, BALL, 3)
            if not np.isnan(ball[f, 0]):
                bx, by = project(hom, np.array([ball[f, 0] / length]),
                                 np.array([ball[f, 1] / width]))
                cv2.circle(img, (int(bx[0]), int(by[0])), 9, BALL, 3)

        cv2.rectangle(img, (0, 0), (src_w, 70), (20, 20, 20), -1)
        label_box(cv2, img, 20, "OURS: " + NAMES.get(ours, ours), ours)
        has_gt = gt is not None and f < len(gt) and gt[f] != "X"
        if has_gt:
            label_box(cv2, img, 540, "GT: " + NAMES.get(gt[f], gt[f]), gt[f])
            mark = "OK" if gt[f] == ours else "MISS"
            cv2.putText(img, mark, (1060, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (80, 220, 80) if mark == "OK" else (60, 60, 240), 2, cv2.LINE_AA)
        status = "ball tracked" if not np.isnan(ball[f, 0]) else "ball NOT tracked"
        cv2.putText(img, "{}   frame {}   {}".format(match_clock(f), f, status), (1180, 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, WHITE, 2, cv2.LINE_AA)

        cv2.rectangle(img, (0, src_h - 90), (src_w, src_h), (20, 20, 20), -1)
        draw_strip(cv2, img, labels, f, src_h - 80, 30, "ours (30 s either side)")
        if gt is not None:
            draw_strip(cv2, img, gt, f, src_h - 42, 30, "ground truth")
        draw_minimap(cv2, img, ball[f], players[f], team_of_slot, slot,
                     src_w - 335, src_h - 90 - 214)

        if scale != 1.0:
            img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        writer.write(img)

    writer.release()
    cap.release()
    return out


def timeline(csv, out, gt_path=None):
    """Write a PNG with one colour strip per half (and the ground truth window when gt_path is given)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    labels = read_labels(csv)
    code = {"H": 0, "A": 1, "D": 2, "X": 3}
    cmap = ListedColormap([HEX["H"], HEX["A"], HEX["D"], "#ffffff"])

    rows = len(config.HALVES) + (1 if gt_path else 0)
    fig, axes = plt.subplots(rows, 1, figsize=(16, 1.8 * rows))
    for half, ((first, last), ax) in enumerate(zip(config.HALVES, axes)):
        seg = np.array([code.get(x, 3) for x in labels[first:last + 1]])[None, :]
        ax.imshow(seg, aspect="auto", cmap=cmap, vmin=0, vmax=3, interpolation="nearest",
                  extent=[0, (last - first + 1) / FPS / 60, 0, 1])
        ax.set_yticks([])
        ax.set_title("half {}: our labels (minutes)".format(half + 1), loc="left", fontsize=10)

    if gt_path:
        gt = read_labels(gt_path)
        window = np.flatnonzero(gt != "X")
        lo, hi = (window[0], window[-1] + 1) if len(window) else (0, 1)
        ours = [code.get(x, 3) for x in labels[lo:hi]]
        true = [code.get(x, 3) for x in gt[lo:hi]]
        ax = axes[-1]
        ax.imshow(np.vstack([ours, true]), aspect="auto", cmap=cmap, vmin=0, vmax=3,
                  interpolation="nearest", extent=[0, (hi - lo) / FPS / 60, 0, 2])
        ax.set_yticks([0.5, 1.5])
        ax.set_yticklabels(["ground truth", "ours"])
        ax.set_title("ground truth window: ours against it", loc="left", fontsize=10)
        ax.set_xlabel("minutes")

    fig.legend(handles=[Patch(color=HEX["H"], label="H  home"),
                        Patch(color=HEX["A"], label="A  away"),
                        Patch(color=HEX["D"], label="D  dead ball")],
               loc="upper right", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    """Command line entry point: the clip and timeline subcommands."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", default=os.path.join(ROOT, "submission", "diables.csv"))
    parser.add_argument("--gt", default=None, help="optional frame,label CSV to draw alongside")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clip")
    c.add_argument("--data", default=os.environ.get("MTAH_DATA_DIR", os.path.join(ROOT, "data")))
    c.add_argument("--cache", default=os.path.join(ROOT, ".cache"))
    c.add_argument("--start", type=int, default=config.HALVES[0][0], help="first video frame")
    c.add_argument("--seconds", type=float, default=60)
    c.add_argument("--scale", type=float, default=0.5, help="output size relative to the video")
    c.add_argument("--out", default=None)

    t = sub.add_parser("timeline")
    t.add_argument("--out", default=os.path.join(OUT_DIR, "timeline.png"))

    args = parser.parse_args()
    if args.cmd == "clip":
        out = args.out or os.path.join(
            OUT_DIR, "clip_{}_{}s.mp4".format(args.start, int(args.seconds)))
        path = clip(args.csv, args.data, args.cache, args.start, args.seconds, out, args.scale,
                    args.gt)
    else:
        path = timeline(args.csv, args.out, args.gt)
    print("wrote {}".format(path))


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    main()

"""Provenance stamped into every file the exporters write.

glTF: the `asset` block (generator, copyright, extras). STEP: the Part 21
header (FILE_DESCRIPTION, FILE_NAME). Both name the tool, its commit, the
repository, the source CAD file with its sha256, and the DJI / RoboMaster
usage notice.
"""
import datetime
import os
import re
import subprocess

REPOSITORY = "https://github.com/hxyulin/rm-map-tools"
COPYRIGHT = (
    "Geometry derived from DJI / RoboMaster's RMUC2026 competition CAD releases; "
    "for building and simulating RoboMaster robots only. See NOTICE.md in " + REPOSITORY
)


def commit():
    """Short git describe of the tool, or 'unknown' outside a checkout."""
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def generator(script):
    return f"rm-map-tools {script} {commit()} ({REPOSITORY})"


def glb_asset(script, source_file, source_sha256, **extras):
    """The glTF `asset` object for a file derived from one source STEP."""
    return {
        "version": "2.0",
        "generator": generator(script),
        "copyright": COPYRIGHT,
        "extras": {
            "tool": "rm-map-tools",
            "script": script,
            "commit": commit(),
            "repository": REPOSITORY,
            "source_file": os.path.basename(source_file),
            "source_sha256": source_sha256,
            **extras,
        },
    }


def _p21(text):
    """A Part 21 string literal; non-ASCII goes through the \\X2\\ directive."""
    out, run = [], []

    def flush():
        if run:
            out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in run) + "\\X0\\")
            run.clear()

    for c in text:
        if ord(c) < 128:
            flush()
            out.append("''" if c == "'" else ("\\\\" if c == "\\" else c))
        else:
            run.append(c)
    flush()
    return "'" + "".join(out) + "'"


def step_header(header, filename, script, source_file, source_sha256, description):
    """Rewrite the source's Part 21 header for a derived file: description,
    name, time stamp and preprocessor say what wrote it and from what; the
    originating system stays the one that produced the geometry."""
    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    desc = (
        f"{description}; extracted by {generator(script)} from {os.path.basename(source_file)} "
        f"(sha256 {source_sha256}); {COPYRIGHT}"
    )
    header = re.sub(rb"(/\* description \*/ \()[^)]*(\))", lambda m: m.group(1) + _p21(desc).encode() + m.group(2), header, count=1)
    header = re.sub(rb"(/\* name \*/ )'[^']*'", lambda m: m.group(1) + _p21(filename).encode(), header, count=1)
    header = re.sub(rb"(/\* time_stamp \*/ )'[^']*'", lambda m: m.group(1) + _p21(now).encode(), header, count=1)
    header = re.sub(rb"(/\* preprocessor_version \*/ )'[^']*'", lambda m: m.group(1) + _p21(generator(script)).encode(), header, count=1)
    return header
